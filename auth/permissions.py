"""Capability-based RBAC for QMS GenAI Platform.

Four regulated roles map onto the existing coarse (admin | quality | user)
users via ``ROLE_CAPABILITIES``. Adding a new capability means editing this
file — routes reference capabilities by name via ``@requires_permission``,
not the role string.

Roles
-----
- QA_REVIEWER : reviews CAPAs, can approve/reject with e-signature
- QA_MANAGER  : QA_REVIEWER + close approved CAPAs + run batch jobs
- SITE_LEAD   : creates records, drafts CAPAs (no approval)
- ADMIN       : everything, including user + role management

The legacy ``admin`` role maps to ADMIN, ``quality`` to QA_MANAGER, and
``user`` to SITE_LEAD. This keeps every existing test + route working
while giving new code a proper capability model.
"""

from __future__ import annotations

from enum import Enum
from functools import wraps
from typing import Iterable

from flask import jsonify
from flask_login import current_user, login_required


class Permission(str, Enum):
    RECORD_CREATE       = "record:create"
    RECORD_UPLOAD       = "record:upload"
    RECORD_VIEW_ALL     = "record:view:all"
    RECORD_STATUS_CHANGE = "record:status:change"

    CAPA_DRAFT          = "capa:draft"
    CAPA_REVIEW         = "capa:review"    # approve or reject
    CAPA_CLOSE          = "capa:close"     # final close after effectiveness check
    CAPA_BATCH_RUN      = "capa:batch"

    AGENT_CONTROL       = "agent:control"  # kill switch, requeue DLQ
    USER_MANAGE         = "user:manage"
    METRICS_VIEW        = "metrics:view"


# ── Role → capabilities ───────────────────────────────────
ADMIN_CAPS = {p for p in Permission}
QA_MANAGER_CAPS = {
    Permission.RECORD_CREATE, Permission.RECORD_UPLOAD,
    Permission.RECORD_VIEW_ALL, Permission.RECORD_STATUS_CHANGE,
    Permission.CAPA_DRAFT, Permission.CAPA_REVIEW, Permission.CAPA_CLOSE,
    Permission.CAPA_BATCH_RUN, Permission.METRICS_VIEW,
}
QA_REVIEWER_CAPS = {
    Permission.RECORD_VIEW_ALL,
    Permission.CAPA_DRAFT, Permission.CAPA_REVIEW,
    Permission.METRICS_VIEW,
}
SITE_LEAD_CAPS = {
    Permission.RECORD_CREATE, Permission.RECORD_UPLOAD,
    Permission.CAPA_DRAFT,
}

# Legacy 3-role labels map onto the new 4-role capability sets.
ROLE_CAPABILITIES: dict[str, set[Permission]] = {
    "admin":       ADMIN_CAPS,
    "quality":     QA_MANAGER_CAPS,
    "qa_manager":  QA_MANAGER_CAPS,
    "qa_reviewer": QA_REVIEWER_CAPS,
    "site_lead":   SITE_LEAD_CAPS,
    "user":        SITE_LEAD_CAPS,
}


def has_permission(user, permission: Permission) -> bool:
    """True if the given Flask-Login user is authorised for ``permission``.

    Accepts either the ``Permission`` enum member or its string value so
    templates can call ``has_permission(user, 'capa:review')``.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    role = getattr(user, "role", "") or ""
    caps = ROLE_CAPABILITIES.get(role.lower(), set())
    if isinstance(permission, str):
        try:
            permission = Permission(permission)
        except ValueError:
            return False
    return permission in caps


def requires_permission(*permissions: Permission):
    """Route decorator: reject with 403 unless the current user has ALL
    of the listed permissions.
    """
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            missing = [p.value for p in permissions if not has_permission(current_user, p)]
            if missing:
                return jsonify({
                    "error": "Not authorised",
                    "missingPermissions": missing,
                    "userRole": getattr(current_user, "role", ""),
                }), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def requires_any_permission(*permissions: Permission):
    """Route decorator: 403 unless the user has AT LEAST ONE of the perms."""
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            if not any(has_permission(current_user, p) for p in permissions):
                return jsonify({
                    "error": "Not authorised",
                    "requiredAny": [p.value for p in permissions],
                    "userRole": getattr(current_user, "role", ""),
                }), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def user_capabilities(user) -> list[str]:
    """List of capability strings for the given user — used to gate UI."""
    role = getattr(user, "role", "") or ""
    return sorted(p.value for p in ROLE_CAPABILITIES.get(role.lower(), set()))
