# database.py
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from services.logging_config import get_logger

load_dotenv()

log = get_logger(__name__)

DATABASE_URL = (os.getenv("DATABASE_URL") or "sqlite:///qms_data.db").strip().strip('"').strip("'")
log.info("db.configured", extra={"url_scheme": DATABASE_URL.split(":", 1)[0]})

_is_sqlite = DATABASE_URL.startswith("sqlite")

_engine_kwargs = {"echo": False}
if _is_sqlite:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    _engine_kwargs["connect_args"] = {}
    _engine_kwargs["pool_size"]    = 5
    _engine_kwargs["max_overflow"] = 10
    _engine_kwargs["pool_pre_ping"]= True

engine = create_engine(DATABASE_URL, **_engine_kwargs)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(conn, _):
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def init_db():
    from models import AuditLog, CAPARecord, LLMCallLog, QualityRecord, UserModel  # noqa: F401
    Base.metadata.create_all(bind=engine)   # creates tables FIRST
    _apply_lightweight_migrations()
    log.info(
        "db.ready",
        extra={"engine": "sqlite" if _is_sqlite else "postgresql",
               "tables": list(Base.metadata.tables.keys())},
    )
    # seed AFTER tables exist
    from data.records import _seed_if_empty
    _seed_if_empty()


def _apply_lightweight_migrations():
    """Additive schema updates for local demo databases (SQLite only).

    Production uses Alembic — see alembic/ and the ``alembic upgrade head``
    step baked into the container entrypoint.
    """
    if not _is_sqlite:
        return
    with engine.begin() as conn:
        columns = {
            row[1] for row in conn.execute(text("PRAGMA table_info(capa_records)")).fetchall()
        }
        if "capa_metadata" not in columns:
            conn.execute(text("ALTER TABLE capa_records ADD COLUMN capa_metadata JSON"))
        user_columns = {
            row[1] for row in conn.execute(text("PRAGMA table_info(users)")).fetchall()
        }
        if "email" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(150) DEFAULT ''"))
        audit_columns = {
            row[1] for row in conn.execute(text("PRAGMA table_info(qms_audit_log)")).fetchall()
        }
        if audit_columns:
            if "payload" not in audit_columns:
                conn.execute(text("ALTER TABLE qms_audit_log ADD COLUMN payload JSON"))
            if "prev_hash" not in audit_columns:
                conn.execute(text("ALTER TABLE qms_audit_log ADD COLUMN prev_hash VARCHAR(64)"))
            if "row_hash" not in audit_columns:
                conn.execute(text("ALTER TABLE qms_audit_log ADD COLUMN row_hash VARCHAR(64)"))

def check_db_connection() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        log.exception("db.connection_failed")
        return False
