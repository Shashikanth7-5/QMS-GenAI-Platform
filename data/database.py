# data/database.py
# Database engine — switches between PostgreSQL and JSON fallback.
# Set DATABASE_URL in .env to activate PostgreSQL:
#   DATABASE_URL=postgresql://user:password@localhost:5432/qms_db
# Leave blank to keep using JSON files (current behaviour).

import os
from contextlib import contextmanager

DATABASE_URL = os.getenv("DATABASE_URL", "")
USE_DB = bool(DATABASE_URL)

if USE_DB:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from data.models import Base

    engine = create_engine(
        DATABASE_URL,
        pool_size       = 10,
        max_overflow    = 20,
        pool_pre_ping   = True,    # reconnect if connection dropped
        pool_recycle    = 300,     # recycle connections every 5 min
        echo            = False,   # set True to log all SQL (debug only)
    )

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def init_db():
        """Create all tables and seed built-in users."""
        Base.metadata.create_all(bind=engine)
        _seed_builtin_users()
        _seed_builtin_records()
        print("[database] PostgreSQL tables ready")

    def _seed_builtin_users():
        from werkzeug.security import generate_password_hash
        from data.models import User
        with get_session() as session:
            if session.query(User).filter_by(is_builtin=True).count() > 0:
                return
            builtins = [
                ("admin",   "admin", "admin",   "Admin",        "approved"),
                ("quality", "admin", "quality", "Quality Lead", "approved"),
                ("shashi",  "admin", "user",    "Shashikanth",  "approved"),
            ]
            for uname, pwd, role, name, status in builtins:
                session.add(User(
                    username   = uname,
                    pw_hash    = generate_password_hash(pwd),
                    role       = role,
                    full_name  = name,
                    status     = status,
                    is_builtin = True,
                ))
            session.commit()
            print("[database] Built-in users seeded")

    def _seed_builtin_records():
        """Seed the 14 built-in quality records if table is empty."""
        from data.models import QualityRecord
        with get_session() as session:
            if session.query(QualityRecord).count() > 0:
                return
            # Import the seeded records from the JSON-based records module
            try:
                from data.records_json import _RECORDS as seeded
            except ImportError:
                return
            for r in seeded:
                rec = QualityRecord(
                    id             = r["id"],
                    type           = r["type"],
                    sector         = r["sector"],
                    title          = r["title"],
                    description    = r["description"],
                    priority       = r["priority"],
                    status         = r.get("status", "Draft Generated"),
                    site           = r.get("site", ""),
                    owner          = r.get("owner", ""),
                    detected_date  = r.get("detectedDate", ""),
                    product_family = r.get("productFamily", ""),
                    batch_lot      = r.get("batchLot", ""),
                    regulatory_ref = r.get("regulatoryRef", []),
                    age            = r.get("age", 0),
                    created_by     = "admin",
                    source         = "seeded",
                )
                session.add(rec)
            session.commit()
            print(f"[database] {len(seeded)} seeded records imported")

    @contextmanager
    def get_session():
        session = SessionLocal()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

else:
    # JSON fallback — existing behaviour, no changes needed
    engine       = None
    SessionLocal = None
    get_session  = None

    def init_db():
        print("[database] Using JSON file storage (set DATABASE_URL in .env for PostgreSQL)")
