# database.py
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

load_dotenv()

DATABASE_URL = (os.getenv("DATABASE_URL") or "sqlite:///qms_data.db").strip().strip('"').strip("'")
print(f"[DB] Using: {DATABASE_URL}")

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
    from models import QualityRecord, CAPARecord, UserModel, AuditLog, LLMCallLog
    Base.metadata.create_all(bind=engine)   # creates tables FIRST
    db_type = "SQLite" if _is_sqlite else "PostgreSQL"
    print(f"[DB] {db_type} ready")
    print(f"[DB] Tables: {list(Base.metadata.tables.keys())}")
    # seed AFTER tables exist
    from data.records import _seed_if_empty
    _seed_if_empty()

def check_db_connection() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        print(f"[DB] Connection failed: {e}")
        return False