"""Bootstrap pilot user accounts at container startup.

Runs before gunicorn. Idempotent — safe to run on every deploy. If a
username already exists, its password/role/status is refreshed from
env vars (so rotating a password only needs a redeploy, not a shell).

Enable with:  BOOTSTRAP_PILOT_USERS=true

Env vars (all optional — safe defaults for a pilot):
    ADMIN_PASSWORD   default "QMSAdmin@2026"
    QUALITY_PASSWORD default "QMSQuality@2026"
    DEMO_PASSWORD    default "QMSDemo@2026"
    REVIEWER_PASSWORD default "QMSReviewer@2026"

The four users created:
    admin     / <ADMIN_PASSWORD>     role=admin    (full access, approve/reject)
    quality   / <QUALITY_PASSWORD>   role=quality  (create CAPAs, no approvals)
    reviewer  / <REVIEWER_PASSWORD>  role=quality  (dedicated reviewer login)
    demo      / <DEMO_PASSWORD>      role=user     (read-only demo account)

Additional teammates raise an access request via the app's /register
page; admin approves via /admin/manage-users.
"""

from __future__ import annotations

import os
import sys

# Ensure repo root is importable when this is invoked as `python -m scripts.bootstrap_pilot_users`
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from werkzeug.security import generate_password_hash  # noqa: E402


def _bool(env: str, default: bool = False) -> bool:
    return os.getenv(env, str(default)).strip().lower() in ("1", "true", "yes", "on")


PILOT_USERS = [
    {
        "username":  "admin",
        "password_env": "ADMIN_PASSWORD",
        "password_default": "QMSAdmin@2026",
        "role":      "admin",
        "full_name": "QMS Admin",
        "email":     "qms-admin@example.com",
    },
    {
        "username":  "quality",
        "password_env": "QUALITY_PASSWORD",
        "password_default": "QMSQuality@2026",
        "role":      "quality",
        "full_name": "Quality Lead",
        "email":     "quality-lead@example.com",
    },
    {
        "username":  "reviewer",
        "password_env": "REVIEWER_PASSWORD",
        "password_default": "QMSReviewer@2026",
        "role":      "quality",
        "full_name": "Quality Reviewer",
        "email":     "reviewer@example.com",
    },
    {
        "username":  "demo",
        "password_env": "DEMO_PASSWORD",
        "password_default": "QMSDemo@2026",
        "role":      "user",
        "full_name": "Demo User",
        "email":     "demo@example.com",
    },
]


def bootstrap() -> None:
    """Create or update every pilot user. Prints a summary at the end."""
    if not _bool("BOOTSTRAP_PILOT_USERS", default=False):
        print("[bootstrap] BOOTSTRAP_PILOT_USERS not set — skipping.")
        return

    from database import SessionLocal, init_db
    from models import UserModel

    print("[bootstrap] BOOTSTRAP_PILOT_USERS=true — ensuring pilot accounts exist")
    init_db()

    created, refreshed = [], []
    with SessionLocal() as session:
        for spec in PILOT_USERS:
            pw = os.getenv(spec["password_env"], spec["password_default"])
            pw_hash = generate_password_hash(pw)

            existing = session.query(UserModel).filter_by(username=spec["username"]).one_or_none()
            if existing is None:
                session.add(UserModel(
                    username=spec["username"],
                    email=spec["email"],
                    password_hash=pw_hash,
                    role=spec["role"],
                    full_name=spec["full_name"],
                    status="approved",
                ))
                created.append(spec["username"])
            else:
                # Refresh password + role + status so a redeploy is enough
                # to rotate credentials without touching the DB.
                existing.password_hash  = pw_hash
                existing.role           = spec["role"]
                existing.status         = "approved"
                existing.full_name      = spec["full_name"]
                if not existing.email:
                    existing.email = spec["email"]
                refreshed.append(spec["username"])
        session.commit()

    print(f"[bootstrap] created:   {created}")
    print(f"[bootstrap] refreshed: {refreshed}")
    print("[bootstrap] done.")


def bootstrap_salesforce_tenant() -> None:
    """Create the Salesforce sandbox tenant using env-provided secrets.

    Enable with:  BOOTSTRAP_SF_TENANT=true

    Required env vars:
        SF_TENANT_ID       e.g. "sf-sandbox"
        SF_API_KEY         paste into Salesforce Named Credential Password
        SF_WEBHOOK_SECRET  paste into QmsSettings__c.Webhook_Secret__c
        SF_ORIGIN          your My Domain URL,
                           e.g. "https://qms-dev-ed.develop.my.salesforce.com"

    The whole point: the admin decides the API key + webhook secret up
    front (32+ random chars each), sets them as Render env vars, and
    the app materialises the tenant on boot -- so no shell command
    needed anywhere.
    """
    if not _bool("BOOTSTRAP_SF_TENANT", default=False):
        print("[bootstrap] BOOTSTRAP_SF_TENANT not set — skipping SF tenant.")
        return

    tenant_id      = os.getenv("SF_TENANT_ID", "sf-sandbox").strip()
    api_key        = os.getenv("SF_API_KEY", "").strip()
    webhook_secret = os.getenv("SF_WEBHOOK_SECRET", "").strip()
    origin         = os.getenv("SF_ORIGIN", "").strip()

    if not api_key or not webhook_secret or not origin:
        print("[bootstrap] SF_API_KEY / SF_WEBHOOK_SECRET / SF_ORIGIN must all be set — skipping SF tenant.")
        return

    try:
        from database import init_db
        init_db()
        from services import tenant_service

        existing = tenant_service.get_tenant(tenant_id) if hasattr(tenant_service, "get_tenant") else None
        if existing:
            print(f"[bootstrap] SF tenant '{tenant_id}' already exists — skipping create.")
            return

        # tenant_service.create_tenant returns (dict, raw_api_key). Because
        # we're providing our own api_key + webhook_secret via env, we
        # call the lower-level create that accepts overrides.
        record, _ = tenant_service.create_tenant(
            tenant_id=tenant_id,
            display_name=os.getenv("SF_TENANT_DISPLAY", "Salesforce Sandbox"),
            origin_allowlist=[origin],
            webhook_secret=webhook_secret,
            api_key_override=api_key,
        )
        print(f"[bootstrap] created SF tenant: {record.get('tenantId', tenant_id)} (origin={origin})")
    except Exception as exc:  # noqa: BLE001
        print(f"[bootstrap] SF tenant bootstrap FAILED: {exc}", file=sys.stderr)


if __name__ == "__main__":
    try:
        bootstrap()
        bootstrap_salesforce_tenant()
    except Exception as exc:  # noqa: BLE001
        # Never crash the container on bootstrap failure — log and continue
        # so gunicorn still starts. Root cause will be in the log.
        print(f"[bootstrap] ERROR: {exc}", file=sys.stderr)
