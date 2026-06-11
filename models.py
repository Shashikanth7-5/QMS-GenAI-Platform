# models.py
# ─────────────────────────────────────────────────────────
# SQLAlchemy models — replaces ALL JSON file persistence
# Works with SQLite (dev) and PostgreSQL (production)
# Drop-in replacement: same field names as the old JSON dicts
# ─────────────────────────────────────────────────────────

from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean,
    DateTime, Text, JSON, ForeignKey, Index
)
from sqlalchemy.orm import relationship
from database import Base


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
    regulatory_refs = Column(JSON,        default=list)       # ["21 CFR 820", "ISO 13485"]
    source          = Column(String(20),  default="manual")   # manual|uploaded

    # Timestamps
    created_at      = Column(DateTime,    default=datetime.utcnow)
    updated_at      = Column(DateTime,    default=datetime.utcnow, onupdate=datetime.utcnow)
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
    regulatory_refs     = Column(JSON, default=list)

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
    created_at          = Column(DateTime,    default=datetime.utcnow)
    updated_at          = Column(DateTime,    default=datetime.utcnow, onupdate=datetime.utcnow)

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
            "status":               self.status,
            "approved":             self.approved,
            "approvedBy":           self.approved_by or "",
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
    password_hash   = Column(String(256), nullable=False)
    role            = Column(String(30),  default="user")
    full_name       = Column(String(150))
    status          = Column(String(20),  default="pending")  # pending|approved|rejected
    reject_comment  = Column(Text,        default="")
    created_at      = Column(DateTime,    default=datetime.utcnow)
    last_login      = Column(DateTime)

    def to_dict(self) -> dict:
        return {
            "id":            self.id,
            "username":      self.username,
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
    __tablename__ = "qms_audit_log"

    id               = Column(Integer,     primary_key=True, autoincrement=True)
    timestamp        = Column(DateTime,    default=datetime.utcnow, nullable=False)
    record_id        = Column(String(50),  nullable=True)
    capa_id          = Column(String(50),  nullable=True)
    entity_type      = Column(String(50),  nullable=True)
    action           = Column(String(100), nullable=False)
    old_value        = Column(Text,        nullable=True)
    new_value        = Column(Text,        nullable=True)
    field_name       = Column(String(100), nullable=True)
    performed_by     = Column(String(100), nullable=False)
    performed_by_role= Column(String(50),  nullable=True)
    ip_address       = Column(String(45),  nullable=True)
    user_agent       = Column(Text,        nullable=True)
    notes            = Column(Text,        nullable=True)

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
        }
# ═════════════════════════════════════════════════════════
# LLM COST LOG  (new — shows interviewers you control costs)
# ═════════════════════════════════════════════════════════
class LLMCallLog(Base):
    __tablename__ = "llm_call_logs"

    id             = Column(Integer,     primary_key=True, autoincrement=True)
    timestamp      = Column(DateTime,    default=datetime.utcnow)
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
