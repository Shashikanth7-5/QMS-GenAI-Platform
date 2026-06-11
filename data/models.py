# data/models.py
# SQLAlchemy ORM models — PostgreSQL ready.
# Switch from JSON to DB by setting DATABASE_URL in .env
# All table names are snake_case, prefixed with qms_

from datetime import datetime
from sqlalchemy import (
    Column, String, Text, Integer, Boolean,
    DateTime, JSON, ForeignKey, Index
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class QualityRecord(Base):
    __tablename__ = "qms_records"

    id              = Column(String(50),  primary_key=True)
    type            = Column(String(20),  nullable=False, index=True)
    sector          = Column(String(50),  nullable=False, index=True)
    title           = Column(String(200), nullable=False)
    description     = Column(Text,        nullable=False)
    priority        = Column(String(20),  nullable=False, index=True)
    status          = Column(String(40),  nullable=False, index=True, default="Draft Generated")
    site            = Column(String(100))
    owner           = Column(String(100))
    detected_date   = Column(String(20))
    product_family  = Column(String(100))
    batch_lot       = Column(String(100))
    regulatory_ref  = Column(JSON,  default=list)
    age             = Column(Integer, default=0)
    created_by      = Column(String(50), nullable=False, index=True)
    created_by_name = Column(String(100))
    created_by_role = Column(String(20))
    source          = Column(String(20), default="seeded")   # seeded | uploaded
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    capas     = relationship("CapaRecord",  back_populates="record",     cascade="all, delete-orphan")
    audit_log = relationship("AuditLog",    back_populates="record",     cascade="all, delete-orphan")
    locks     = relationship("RecordLock",  back_populates="record",     cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_qms_records_type_status", "type", "status"),
        Index("ix_qms_records_priority_status", "priority", "status"),
    )

    def to_dict(self):
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
            "regulatoryRef": self.regulatory_ref or [],
            "age":           self.age or 0,
            "createdBy":     self.created_by,
            "createdByName": self.created_by_name or "",
            "createdByRole": self.created_by_role or "",
            "_source":       self.source,
            "createdAt":     self.created_at.isoformat() if self.created_at else "",
        }


class CapaRecord(Base):
    __tablename__ = "qms_capas"

    capa_id                = Column(String(50),  primary_key=True)
    source_record_id       = Column(String(50),  ForeignKey("qms_records.id"), index=True)
    source_record_type     = Column(String(50))
    source_record_title    = Column(String(200))
    sector                 = Column(String(50))
    priority               = Column(String(20),  index=True)
    site                   = Column(String(100))
    status                 = Column(String(40),  nullable=False, default="Under Review", index=True)
    root_cause             = Column(Text)
    immediate_action       = Column(Text)
    corrective_action      = Column(Text)
    preventive_action      = Column(Text)
    capa_owner             = Column(String(100))
    effectiveness_check    = Column(Text)
    risk_rating            = Column(String(20))
    regulatory_ref         = Column(JSON, default=list)
    estimated_closure_days = Column(Integer, default=30)
    target_closure_date    = Column(String(20))
    notes                  = Column(Text)
    confidence_score       = Column(Integer)     # 0-100, AI confidence
    created_by             = Column(String(100))
    created_by_username    = Column(String(50),  index=True)
    created_by_role        = Column(String(20))
    created_at             = Column(DateTime, default=datetime.utcnow)
    updated_at             = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    record    = relationship("QualityRecord", back_populates="capas")
    audit_log = relationship("AuditLog",      back_populates="capa", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_qms_capas_status_priority", "status", "priority"),
    )

    def to_dict(self):
        return {
            "capaId":               self.capa_id,
            "sourceRecordId":       self.source_record_id,
            "sourceRecordType":     self.source_record_type or "",
            "sourceRecordTitle":    self.source_record_title or "",
            "sector":               self.sector or "",
            "priority":             self.priority or "",
            "site":                 self.site or "",
            "status":               self.status,
            "rootCause":            self.root_cause or "",
            "immediateAction":      self.immediate_action or "",
            "correctiveAction":     self.corrective_action or "",
            "preventiveAction":     self.preventive_action or "",
            "capaOwner":            self.capa_owner or "",
            "effectivenessCheck":   self.effectiveness_check or "",
            "riskRating":           self.risk_rating or "",
            "regulatoryRef":        self.regulatory_ref or [],
            "estimatedClosureDays": self.estimated_closure_days or 30,
            "targetClosureDate":    self.target_closure_date or "",
            "notes":                self.notes or "",
            "confidenceScore":      self.confidence_score,
            "createdBy":            self.created_by or "",
            "createdByUsername":    self.created_by_username or "",
            "createdByRole":        self.created_by_role or "",
            "createdAt":            self.created_at.isoformat() if self.created_at else "",
            "updatedAt":            self.updated_at.isoformat() if self.updated_at else "",
        }


class AuditLog(Base):
    """
    21 CFR Part 11 compliant audit trail.
    Every status change, CAPA approval, role change is logged here.
    Immutable — no UPDATE or DELETE operations on this table.
    """
    __tablename__ = "qms_audit_log"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    record_id    = Column(String(50), ForeignKey("qms_records.id"), nullable=True, index=True)
    capa_id      = Column(String(50), ForeignKey("qms_capas.capa_id"), nullable=True, index=True)
    entity_type  = Column(String(20), nullable=False)   # record | capa | user | system
    action       = Column(String(50), nullable=False)   # status_change | capa_generated | capa_approved | etc.
    old_value    = Column(Text)
    new_value    = Column(Text)
    field_name   = Column(String(50))
    performed_by = Column(String(50), nullable=False)   # username
    performed_by_role = Column(String(20))
    ip_address   = Column(String(45))
    user_agent   = Column(String(200))
    timestamp    = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    notes        = Column(Text)

    record = relationship("QualityRecord", back_populates="audit_log")
    capa   = relationship("CapaRecord",    back_populates="audit_log")

    __table_args__ = (
        Index("ix_audit_log_entity_timestamp", "entity_type", "timestamp"),
        Index("ix_audit_log_performed_by", "performed_by", "timestamp"),
    )

    def to_dict(self):
        return {
            "id":             self.id,
            "recordId":       self.record_id,
            "capaId":         self.capa_id,
            "entityType":     self.entity_type,
            "action":         self.action,
            "oldValue":       self.old_value,
            "newValue":       self.new_value,
            "fieldName":      self.field_name,
            "performedBy":    self.performed_by,
            "performedByRole":self.performed_by_role,
            "timestamp":      self.timestamp.isoformat() if self.timestamp else "",
            "notes":          self.notes or "",
        }


class RecordLock(Base):
    """
    Optimistic locking for concurrent CAPA edits.
    A record is locked when a user opens the CAPA creation page.
    Lock expires after LOCK_TTL_SECONDS (default 300).
    """
    __tablename__ = "qms_record_locks"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    record_id  = Column(String(50), ForeignKey("qms_records.id"), nullable=False, index=True)
    locked_by  = Column(String(50), nullable=False)
    locked_at  = Column(DateTime,   default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime,   nullable=False)
    session_id = Column(String(100))

    record = relationship("QualityRecord", back_populates="locks")


class User(Base):
    """
    Production user table — replaces users_data.json.
    Built-in users (admin, quality, shashi) are seeded on first run.
    """
    __tablename__ = "qms_users"

    id             = Column(Integer,    primary_key=True, autoincrement=True)
    username       = Column(String(50), unique=True, nullable=False, index=True)
    pw_hash        = Column(String(256), nullable=False)
    role           = Column(String(20),  nullable=False, default="user")
    full_name      = Column(String(100), nullable=False)
    status         = Column(String(20),  nullable=False, default="pending")
    reject_comment = Column(Text)
    created_at     = Column(DateTime, default=datetime.utcnow)
    last_login     = Column(DateTime)
    is_builtin     = Column(Boolean, default=False)
