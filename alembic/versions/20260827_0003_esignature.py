"""improvement-v1 additions — 21 CFR Part 11 ESignature table.

Revision ID: 20260827_0003
Revises: 20260826_0002
Create Date: 2026-08-27
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260827_0003"
down_revision: Union[str, None] = "20260826_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "qms_esignatures",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(80), index=True, nullable=True),
        sa.Column("entity_type", sa.String(30), nullable=False),
        sa.Column("entity_id", sa.String(80), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("meaning", sa.Text, nullable=False),
        sa.Column("signer_username", sa.String(80), nullable=False),
        sa.Column("signer_role", sa.String(30)),
        sa.Column("signer_full_name", sa.String(150)),
        sa.Column("signer_ip", sa.String(45)),
        sa.Column("signer_user_agent", sa.Text),
        sa.Column("reason_code", sa.String(50)),
        sa.Column("reason_text", sa.Text),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("prev_hash", sa.String(64)),
        sa.Column("row_hash", sa.String(64)),
        sa.Column("signed_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_esig_entity", "qms_esignatures", ["entity_type", "entity_id"])
    op.create_index("ix_esig_signer_time", "qms_esignatures", ["signer_username", "signed_at"])
    op.create_index("ix_qms_esignatures_entity_id", "qms_esignatures", ["entity_id"])
    op.create_index("ix_qms_esignatures_signed_at", "qms_esignatures", ["signed_at"])


def downgrade() -> None:
    op.drop_index("ix_qms_esignatures_signed_at", table_name="qms_esignatures")
    op.drop_index("ix_qms_esignatures_entity_id", table_name="qms_esignatures")
    op.drop_index("ix_esig_signer_time", table_name="qms_esignatures")
    op.drop_index("ix_esig_entity", table_name="qms_esignatures")
    op.drop_table("qms_esignatures")
