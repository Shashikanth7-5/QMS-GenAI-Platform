"""Version@3 additions — persistent DLQ, RAG store, API tenants, idempotency, nonce.

Revision ID: 20260826_0002
Revises: 20260804_0001
Create Date: 2026-08-26

Adds five new tables introduced in Version@3:
    - qms_agent_deadletter
    - qms_rag_extractions
    - qms_api_tenants
    - qms_idempotency_keys
    - qms_webhook_nonces

Each table has explicit column definitions so we do NOT rely on
create_all — this migration must run cleanly on a Postgres tenant
that already has the Version@2 baseline in place.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260826_0002"
down_revision: Union[str, None] = "20260804_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "qms_agent_deadletter",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("record_id", sa.String(50), nullable=False),
        sa.Column("run_id", sa.String(50)),
        sa.Column("attempts", sa.Integer(), server_default="0"),
        sa.Column("last_error", sa.Text()),
        sa.Column("parked_at", sa.DateTime(), nullable=False),
        sa.Column("requeued_at", sa.DateTime()),
        sa.Column("requeued_by", sa.String(80)),
        sa.Column("tenant_id", sa.String(80)),
    )
    op.create_index("ix_qms_agent_deadletter_record_id",
                    "qms_agent_deadletter", ["record_id"])
    op.create_index("ix_qms_agent_deadletter_parked_at",
                    "qms_agent_deadletter", ["parked_at"])
    op.create_index("ix_qms_agent_deadletter_tenant_id",
                    "qms_agent_deadletter", ["tenant_id"])

    op.create_table(
        "qms_rag_extractions",
        sa.Column("id", sa.String(60), primary_key=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(20)),
        sa.Column("file_size", sa.Integer(), server_default="0"),
        sa.Column("extracted_at", sa.DateTime(), nullable=False),
        sa.Column("extracted_by", sa.String(80), nullable=False),
        sa.Column("is_image", sa.Boolean(), server_default=sa.false()),
        sa.Column("text_preview", sa.Text()),
        sa.Column("record_json", sa.JSON()),
        sa.Column("tenant_id", sa.String(80)),
    )
    op.create_index("ix_qms_rag_extractions_extracted_at",
                    "qms_rag_extractions", ["extracted_at"])
    op.create_index("ix_qms_rag_extractions_extracted_by",
                    "qms_rag_extractions", ["extracted_by"])
    op.create_index("ix_qms_rag_extractions_tenant_id",
                    "qms_rag_extractions", ["tenant_id"])

    op.create_table(
        "qms_api_tenants",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(80), nullable=False, unique=True),
        sa.Column("display_name", sa.String(200)),
        sa.Column("api_key_hash", sa.String(128), nullable=False),
        sa.Column("webhook_secret", sa.String(128)),
        sa.Column("origin_allowlist", sa.JSON()),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("revoked_at", sa.DateTime()),
        sa.Column("last_used_at", sa.DateTime()),
        sa.Column("rate_limit", sa.String(80), server_default="120 per minute; 2000 per hour"),
    )
    op.create_index("ix_qms_api_tenants_tenant_id",
                    "qms_api_tenants", ["tenant_id"], unique=True)

    op.create_table(
        "qms_idempotency_keys",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(80), nullable=False),
        sa.Column("key", sa.String(120), nullable=False),
        sa.Column("method", sa.String(10)),
        sa.Column("path", sa.String(200)),
        sa.Column("request_hash", sa.String(64)),
        sa.Column("status_code", sa.Integer()),
        sa.Column("response_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_idempotency_tenant_key",
                    "qms_idempotency_keys", ["tenant_id", "key"], unique=True)

    op.create_table(
        "qms_webhook_nonces",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(80), nullable=False),
        sa.Column("nonce", sa.String(80), nullable=False),
        sa.Column("seen_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_nonce_tenant_nonce",
                    "qms_webhook_nonces", ["tenant_id", "nonce"], unique=True)
    op.create_index("ix_qms_webhook_nonces_seen_at",
                    "qms_webhook_nonces", ["seen_at"])


def downgrade() -> None:
    op.drop_table("qms_webhook_nonces")
    op.drop_table("qms_idempotency_keys")
    op.drop_table("qms_api_tenants")
    op.drop_table("qms_rag_extractions")
    op.drop_table("qms_agent_deadletter")
