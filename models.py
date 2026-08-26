# models.py
# ─────────────────────────────────────────────────────────
# SQLAlchemy models — replaces ALL JSON file persistence
# Works with SQLite (dev) and PostgreSQL (production)
# Drop-in replacement: same field names as the old JSON dicts
# ─────────────────────────────────────────────────────────

from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, Boolean,
    DateTime, Text, JSON, ForeignKey, Index
)
from sqlalchemy.orm import relationship
from database import Base


def _utcnow() -> datetime:
    """
    Naive UTC now — datetime.utcnow() is deprecated in 3.12+ but the DB
    columns in this project use naive DateTime (not DateTime(timezone=True)),
    and lock_service compares them against wall-clock naive UTC everywhere.
    So we produce a tz-aware datetime and strip the tzinfo, keeping storage
    semantics identical while dropping the deprecation warning.
    Version@3 backlog: migrate DateTime columns to timezone=True.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ═════════════════════════════════════════════════════════
# QUALITY RECORDS  (was: uploaded_records.json)
# ═════════════════════════════════════════════════════════
class QualityRecord(Base):
    __tablename__ = "quality_records"

    # Primary key
    id              = Column(String(50),  primary_key=True)   # e.g. QR-2024-0001

    # Core fields — exact same names as your JSON dicts
    type            = Column(String(20),  nullable=False)     # complaint|deviation|cc|nc|audit
    sector          = Column(String(50),  nullable=False)     # Medical Device|BioPharma
    title           = Column(String(200), nullable=False)
    description     = Column(Text,        nullable=False)
    priority        = Column(String(20),  nullable=False)     # Critical|High|Medium|Low
    status          = Column(String(50),  default="Draft Generated")
    site            = Column(String(100))
    owner           = Column(String(100))
    detected_date   = Column(String(20))                      # YYYY-MM-DD
    product_family  = Column(String(100), default="")
    batch_lot       = Column(String(100), default="")
    regulatory_refs = Column(JSON,        default=lambda: [])       # ["21 CFR 820", "ISO 13485"]
    source          = Column(String(20),  default="manual")   # manual|uploaded

    # Timestamps
    created_at      = Column(DateTime,    default=_utcnow)
    updated_at      = Column(DateTime,    default=_utcnow, onupdate=_utcnow)
    age_days        = Column(Integer,     default=0)

    # Relationships
    capas           = relationship("CAPARecord", back_populates="record",
                                   cascade="all, delete-orphan")


    # Indexes for fast queries
    __table_args__ = (
        Index("ix_records_type",     "type"),
        Index("ix_records_status",   "status"),
        Index("ix_records_priority", "priority"),
        Index("ix_records_sector",   "sector"),
    )

    def to_dict(self) -> dict:
        """Returns a dict matching the old JSON format exactly — no route changes needed."""
        return {
            "id":            self.id,
            "type":          self.type,
            "sector":        self.sector,
            "title":         self.title,
            "description":   self.description,
            "priority":      self.priority,
            "status":        self.status,
            "site":          self.site or "",
            "owner":         self.owner or "",
            "detectedDate":  self.detected_date or "",
            "productFamily": self.product_family or "",
            "batchLot":      self.batch_lot or "",
            "regulatoryRef": self.regulatory_refs or [],
            "_source":       self.source,
            "age":           self.age_days,
        }

    def __repr__(self):
        return f"<QualityRecord {self.id} [{self.type}] {self.priority}>"


# ═════════════════════════════════════════════════════════
# CAPA RECORDS  (was: capa_store.json)
# ═════════════════════════════════════════════════════════
class CAPARecord(Base):
    __tablename__ = "capa_records"

    id                  = Column(Integer,     primary_key=True, autoincrement=True)
    capa_id             = Column(String(50),  unique=True, nullable=False)  # CAPA-2024-0001
    record_id           = Column(String(50),  ForeignKey("quality_records.id"), nullable=False)

    # AI-generated fields — exact same names as old JSON
    root_cause          = Column(Text)
    immediate_action    = Column(Text)
    corrective_action   = Column(Text)
    preventive_action   = Column(Text)
    proposed_owner      = Column(String(100))
    effectiveness_check = Column(Text)
    estimated_closure_days = Column(Integer, default=90)
    risk_rating         = Column(String(20))                  # Critical|High|Medium|Low
    regulatory_refs     = Column(JSON, default=lambda: [])
    capa_metadata       = Column(JSON, default=lambda: {})

    # Workflow
    status              = Column(String(30),  default="Draft Generated")
    approved            = Column(Boolean,     default=False)
    approved_by         = Column(String(100))
    approved_at         = Column(DateTime)
    rejected_by         = Column(String(100))
    rejected_at         = Column(DateTime)
    rejection_comment   = Column(Text)

    # Metadata
    created_by_username = Column(String(100))
    created_at          = Column(DateTime,    default=_utcnow)
    updated_at          = Column(DateTime,    default=_utcnow, onupdate=_utcnow)

    # AI generation metadata
    ai_provider         = Column(String(30))                  # anthropic|openai|azure|mock
    ai_model            = Column(String(80))
    generation_time_ms  = Column(Integer)
    rca_quality_score   = Column(Float)

    # Relationship
    record              = relationship("QualityRecord", back_populates="capas")

    __table_args__ = (
        Index("ix_capa_record_id", "record_id"),
        Index("ix_capa_status",    "status"),
    )

    def to_dict(self) -> dict:
        return {
            "capaId":               self.capa_id,
            "recordId":             self.record_id,
            "rootCause":            self.root_cause or "",
            "immediateAction":      self.immediate_action or "",
            "correctiveAction":     self.corrective_action or "",
            "preventiveAction":     self.preventive_action or "",
            "proposedOwner":        self.proposed_owner or "",
            "effectivenessCheck":   self.effectiveness_check or "",
            "estimatedClosureDays": self.estimated_closure_days,
            "riskRating":           self.risk_rating or "",
            "regulatoryRef":        self.regulatory_refs or [],
            "capaMetadata":         self.capa_metadata or {},
            "status":               self.status,
            "approved":             self.approved,
            "approvedBy":           self.approved_by or "",
            "rejectedBy":           self.rejected_by or "",
            "rejectedAt":           self.rejected_at.isoformat() if self.rejected_at else "",
            "rejectionComment":     self.rejection_comment or "",
            "createdByUsername":    self.created_by_username or "",
            "createdAt":            self.created_at.isoformat() if self.created_at else "",
            "aiProvider":           self.ai_provider or "",
            "rcaQualityScore":      self.rca_quality_score,
        }

    def __repr__(self):
        return f"<CAPARecord {self.capa_id} [{self.status}]>"


# ═════════════════════════════════════════════════════════
# USERS  (was: users_data.json)
# ═════════════════════════════════════════════════════════
class UserModel(Base):
    __tablename__ = "users"

    id              = Column(Integer,     primary_key=True, autoincrement=True)
    username        = Column(String(80),  unique=True, nullable=False)
    email           = Column(String(150), default="")
    password_hash   = Column(String(256), nullable=False)
    role            = Column(String(30),  default="user")
    full_name       = Column(String(150))
    status          = Column(String(20),  default="pending")  # pending|approved|rejected
    reject_comment  = Column(Text,        default="")
    created_at      = Column(DateTime,    default=_utcnow)
    last_login      = Column(DateTime)

    def to_dict(self) -> dict:
        return {
            "id":            self.id,
            "username":      self.username,
            "email":         self.email or "",
            "role":          self.role,
            "full_name":     self.full_name or "",
            "status":        self.status,
            "reject_comment":self.reject_comment or "",
            "created_at":    self.created_at.isoformat() if self.created_at else "",
        }


# ═════════════════════════════════════════════════════════
# AUDIT LOG  (new — this is what interviewers ask about)
# Logs every significant action for regulatory compliance
# ═════════════════════════════════════════════════════════
class AuditLog(Base):
    """21 CFR Part 11 audit trail — append-only, hash-chained.

    Every row commits to the previous row's SHA-256 digest via ``prev_hash``
    and stores its own digest in ``row_hash``. A single altered entry
    invalidates every subsequent row, giving tamper-evidence without
    relying on filesystem or DB access controls alone.

    ``entity_type`` covers regulated entities (record, capa, user) AND the
    operational agent trail (agent) so we have one auditable stream.
    """
    __tablename__ = "qms_audit_log"

    id                = Column(Integer,     primary_key=True, autoincrement=True)
    timestamp         = Column(DateTime,    default=_utcnow, nullable=False)
    record_id         = Column(String(50),  nullable=True)
    capa_id           = Column(String(50),  nullable=True)
    entity_type       = Column(String(50),  nullable=True)   # record | capa | user | agent
    action            = Column(String(100), nullable=False)
    old_value         = Column(Text,        nullable=True)
    new_value         = Column(Text,        nullable=True)
    field_name        = Column(String(100), nullable=True)
    performed_by      = Column(String(100), nullable=False)
    performed_by_role = Column(String(50),  nullable=True)
    ip_address        = Column(String(45),  nullable=True)
    user_agent        = Column(Text,        nullable=True)
    notes             = Column(Text,        nullable=True)
    # Agent + structured payloads live here so agents and CAPA share one table.
    payload           = Column(JSON,        nullable=True, default=lambda: {})
    # Hash chain — never null after v2.
    prev_hash         = Column(String(64),  nullable=True)
    row_hash          = Column(String(64),  nullable=True)

    __table_args__ = (
        Index("ix_audit_timestamp",    "timestamp"),
        Index("ix_audit_entity",       "entity_type", "timestamp"),
        Index("ix_audit_record",       "record_id"),
        Index("ix_audit_capa",         "capa_id"),
        Index("ix_audit_performed_by", "performed_by", "timestamp"),
    )

    def to_dict(self):
        return {
            "id":             self.id,
            "timestamp":      self.timestamp.isoformat() if self.timestamp else "",
            "recordId":       self.record_id or "",
            "capaId":         self.capa_id or "",
            "entityType":     self.entity_type or "",
            "action":         self.action,
            "oldValue":       self.old_value or "",
            "newValue":       self.new_value or "",
            "fieldName":      self.field_name or "",
            "performedBy":    self.performed_by,
            "performedByRole":self.performed_by_role or "",
            "ipAddress":      self.ip_address or "",
            "notes":          self.notes or "",
            "payload":        self.payload or {},
            "prevHash":       self.prev_hash or "",
            "rowHash":        self.row_hash or "",
        }
# ═════════════════════════════════════════════════════════
# LLM COST LOG  (new — shows interviewers you control costs)
# ═════════════════════════════════════════════════════════
class LLMCallLog(Base):
    __tablename__ = "llm_call_logs"

    id             = Column(Integer,     primary_key=True, autoincrement=True)
    timestamp      = Column(DateTime,    default=_utcnow)
    username       = Column(String(80))
    provider       = Column(String(30))                  # anthropic|openai|azure|bedrock
    model          = Column(String(80))
    task           = Column(String(50))                  # capa_gen|rca_gen|extraction
    input_tokens   = Column(Integer,     default=0)
    output_tokens  = Column(Integer,     default=0)
    latency_ms     = Column(Integer,     default=0)
    cost_usd       = Column(Float,       default=0.0)
    success        = Column(Boolean,     default=True)
    error_message  = Column(Text)
    cached         = Column(Boolean,     default=False)  # True = no LLM call made

    __table_args__ = (
        Index("ix_llm_timestamp", "timestamp"),
        Index("ix_llm_provider",  "provider"),
    )


# ═════════════════════════════════════════════════════════
# AGENT DEAD-LETTER QUEUE (persistent)
# Replaces the in-memory list in services/agents/supervisor.py
# so ops can inspect + requeue after worker restart.
# ═════════════════════════════════════════════════════════
class AgentDeadLetter(Base):
    __tablename__ = "qms_agent_deadletter"

    id          = Column(Integer,   primary_key=True, autoincrement=True)
    record_id   = Column(String(50), nullable=False, index=True)
    run_id      = Column(String(50))
    attempts    = Column(Integer,   default=0)
    last_error  = Column(Text)
    parked_at   = Column(DateTime,  default=_utcnow, nullable=False, index=True)
    requeued_at = Column(DateTime)
    requeued_by = Column(String(80))
    tenant_id   = Column(String(80), index=True)   # multi-tenant scoping

    def to_dict(self) -> dict:
        return {
            "recordId":  self.record_id,
            "attempts":  self.attempts or 0,
            "lastError": self.last_error or "",
            "parkedAt":  self.parked_at.isoformat() + "Z" if self.parked_at else "",
            "runId":     self.run_id or "",
            "tenantId":  self.tenant_id or "",
        }


# ═════════════════════════════════════════════════════════
# RAG EXTRACTION STORE (persistent)
# Replaces the in-memory _EXTRACTION_STORE list in routes/rag.py
# so /api/rag/ask works across worker processes.
# ═════════════════════════════════════════════════════════
class RagExtraction(Base):
    __tablename__ = "qms_rag_extractions"

    id            = Column(String(60), primary_key=True)   # EXT-YYYYmmddHHMMSS-XXXX
    filename      = Column(String(255), nullable=False)
    file_type     = Column(String(20))
    file_size     = Column(Integer,     default=0)
    extracted_at  = Column(DateTime,    default=_utcnow, nullable=False, index=True)
    extracted_by  = Column(String(80),  nullable=False, index=True)
    is_image      = Column(Boolean,     default=False)
    text_preview  = Column(Text)
    record_json   = Column(JSON,        default=lambda: {})
    tenant_id     = Column(String(80),  index=True)

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "filename":    self.filename,
            "fileType":    self.file_type or "",
            "fileSize":    self.file_size or 0,
            "extractedAt": self.extracted_at.isoformat() if self.extracted_at else "",
            "extractedBy": self.extracted_by,
            "isImage":     bool(self.is_image),
            "textPreview": self.text_preview or "",
            "record":      self.record_json or {},
            "tenantId":    self.tenant_id or "",
        }


# ═════════════════════════════════════════════════════════
# API TENANT — per-tenant API keys for TrackWise / Salesforce
# integrations (replaces single global API_V1_KEY).
# ═════════════════════════════════════════════════════════
class ApiTenant(Base):
    __tablename__ = "qms_api_tenants"

    id             = Column(Integer,     primary_key=True, autoincrement=True)
    tenant_id      = Column(String(80),  unique=True, nullable=False, index=True)
    display_name   = Column(String(200))
    # API-key HMAC digest (never store the raw key). See services/security.py.
    api_key_hash   = Column(String(128), nullable=False)
    webhook_secret = Column(String(128))   # per-tenant SF webhook signing secret
    origin_allowlist = Column(JSON,      default=lambda: [])  # CORS origins for this tenant
    status         = Column(String(20),  default="active")    # active|revoked
    created_at     = Column(DateTime,    default=_utcnow)
    revoked_at     = Column(DateTime)
    last_used_at   = Column(DateTime)
    rate_limit     = Column(String(80),  default="120 per minute; 2000 per hour")

    def to_dict(self) -> dict:
        return {
            "tenantId":     self.tenant_id,
            "displayName":  self.display_name or "",
            "status":       self.status,
            "createdAt":    self.created_at.isoformat() if self.created_at else "",
            "lastUsedAt":   self.last_used_at.isoformat() if self.last_used_at else "",
            "rateLimit":    self.rate_limit or "",
            "originAllowlist": self.origin_allowlist or [],
        }


# ═════════════════════════════════════════════════════════
# IDEMPOTENCY KEY — retries of the same POST return the same
# response instead of duplicating CAPAs / records.
# ═════════════════════════════════════════════════════════
class IdempotencyKey(Base):
    __tablename__ = "qms_idempotency_keys"

    id         = Column(Integer,     primary_key=True, autoincrement=True)
    tenant_id  = Column(String(80),  nullable=False, index=True)
    key        = Column(String(120), nullable=False, index=True)
    method     = Column(String(10))
    path       = Column(String(200))
    request_hash = Column(String(64))   # sha256 of body — mismatch = 409
    status_code  = Column(Integer)
    response_json = Column(JSON,     default=lambda: {})
    created_at  = Column(DateTime,   default=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_idempotency_tenant_key", "tenant_id", "key", unique=True),
    )


# ═════════════════════════════════════════════════════════
# WEBHOOK NONCE — replay-protection for Salesforce webhook.
# Signature + timestamp must be inside a 5-minute window, and
# the (tenant, nonce) pair may only appear once.
# ═════════════════════════════════════════════════════════
class WebhookNonce(Base):
    __tablename__ = "qms_webhook_nonces"

    id         = Column(Integer,    primary_key=True, autoincrement=True)
    tenant_id  = Column(String(80), nullable=False, index=True)
    nonce      = Column(String(80), nullable=False)
    seen_at    = Column(DateTime,   default=_utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("ix_nonce_tenant_nonce", "tenant_id", "nonce", unique=True),
    )
