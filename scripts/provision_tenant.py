"""Provision an API tenant.

Usage:
    python -m scripts.provision_tenant \
        --tenant acme-prod \
        --display "Acme Pharma (prod)" \
        --origins https://acme.my.salesforce.com,https://tw.acme.com \
        [--webhook-secret RANDOM_HEX]

Prints the generated API key **once** to stdout. Store it in the tenant's
secret manager immediately — the DB only keeps the hash.
"""

from __future__ import annotations

import argparse
import secrets
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", required=True, help="tenant slug, e.g. acme-prod")
    parser.add_argument("--display", default="", help="human-friendly name")
    parser.add_argument("--origins", default="",
                        help="comma-separated CORS origins for this tenant")
    parser.add_argument("--webhook-secret", default="",
                        help="webhook signing secret (auto-generated if omitted)")
    parser.add_argument("--rate-limit", default="120 per minute; 2000 per hour")
    args = parser.parse_args()

    # Bootstrap the schema so this CLI works on a fresh checkout too.
    from database import init_db
    init_db()

    from services.tenant_service import create_tenant

    webhook = args.webhook_secret or secrets.token_urlsafe(32)
    origins = [o.strip() for o in (args.origins or "").split(",") if o.strip()]

    try:
        tenant, raw_key = create_tenant(
            args.tenant,
            display_name=args.display or args.tenant,
            origin_allowlist=origins,
            webhook_secret=webhook,
            rate_limit=args.rate_limit,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    print("=== Tenant provisioned ===")
    print(f"tenant_id:          {tenant['tenantId']}")
    print(f"display_name:       {tenant['displayName']}")
    print(f"status:             {tenant['status']}")
    print(f"origin_allowlist:   {tenant['originAllowlist']}")
    print(f"rate_limit:         {tenant['rateLimit']}")
    print()
    print("Hand these to the tenant (they are only shown once):")
    print(f"  X-Tenant-Id:      {tenant['tenantId']}")
    print(f"  X-API-Key:        {raw_key}")
    print(f"  webhook_secret:   {webhook}")
    print()
    print("Salesforce webhook signature scheme:")
    print("  sig = HMAC_SHA256(webhook_secret, f'{timestamp}.{nonce}.{raw_body}').hex()")
    print("  Headers: X-Salesforce-Timestamp, X-Salesforce-Nonce, X-Salesforce-Signature")


if __name__ == "__main__":
    main()
