# services/lock_service.py
# Prevents concurrent CAPA edits corrupting records.
# Uses PostgreSQL row locks when DB available, in-memory dict for JSON mode.
# Lock TTL: 5 minutes (300 seconds) — auto-expires if user navigates away.

import os
import threading
from datetime import datetime, timedelta
from typing import Optional, Tuple

LOCK_TTL_SECONDS = int(os.getenv("LOCK_TTL_SECONDS", "300"))

# ── In-memory lock store (JSON mode fallback) ──────────────
# { record_id: { "locked_by": username, "expires_at": datetime, "session_id": str } }
_locks: dict = {}
_lock_mutex = threading.Lock()


def acquire_lock(
    record_id:  str,
    username:   str,
    session_id: str = "",
) -> Tuple[bool, Optional[str]]:
    """
    Try to acquire an edit lock on a record.
    Returns (success, locked_by_username_if_failed).
    """
    from data.database import USE_DB
    if USE_DB:
        return _acquire_db(record_id, username, session_id)
    return _acquire_memory(record_id, username, session_id)


def release_lock(record_id: str, username: str) -> bool:
    """Release a lock. Only the lock holder can release it."""
    from data.database import USE_DB
    if USE_DB:
        return _release_db(record_id, username)
    return _release_memory(record_id, username)


def get_lock_status(record_id: str) -> Optional[dict]:
    """
    Returns lock info if record is locked, None if free.
    { locked_by, expires_at, minutes_remaining }
    """
    from data.database import USE_DB
    if USE_DB:
        return _status_db(record_id)
    return _status_memory(record_id)


def extend_lock(record_id: str, username: str) -> bool:
    """Extend lock TTL (called via heartbeat from frontend every 60s)."""
    from data.database import USE_DB
    if USE_DB:
        return _extend_db(record_id, username)
    return _extend_memory(record_id, username)


# ── In-memory implementation ───────────────────────────────
def _acquire_memory(record_id, username, session_id):
    with _lock_mutex:
        _expire_stale_locks_memory()
        existing = _locks.get(record_id)
        if existing:
            if existing["locked_by"] == username:
                # Re-entrant: same user refreshes their own lock
                existing["expires_at"] = datetime.utcnow() + timedelta(seconds=LOCK_TTL_SECONDS)
                return True, None
            return False, existing["locked_by"]
        _locks[record_id] = {
            "locked_by":  username,
            "expires_at": datetime.utcnow() + timedelta(seconds=LOCK_TTL_SECONDS),
            "session_id": session_id,
        }
        return True, None


def _release_memory(record_id, username):
    with _lock_mutex:
        lock = _locks.get(record_id)
        if lock and lock["locked_by"] == username:
            del _locks[record_id]
            return True
        return False


def _status_memory(record_id):
    with _lock_mutex:
        _expire_stale_locks_memory()
        lock = _locks.get(record_id)
        if not lock:
            return None
        return {
            "locked_by":        lock["locked_by"],
            "expires_at":       lock["expires_at"].isoformat(),
            "minutes_remaining": max(0, int((lock["expires_at"] - datetime.utcnow()).total_seconds() / 60)),
        }


def _extend_memory(record_id, username):
    with _lock_mutex:
        lock = _locks.get(record_id)
        if lock and lock["locked_by"] == username:
            lock["expires_at"] = datetime.utcnow() + timedelta(seconds=LOCK_TTL_SECONDS)
            return True
        return False


def _expire_stale_locks_memory():
    now = datetime.utcnow()
    expired = [rid for rid, lock in _locks.items() if lock["expires_at"] < now]
    for rid in expired:
        del _locks[rid]


# ── PostgreSQL implementation ──────────────────────────────
def _acquire_db(record_id, username, session_id):
    try:
        from data.database import get_session
        from data.models import RecordLock
        from sqlalchemy import and_
        with get_session() as session:
            # Clean up expired locks
            session.query(RecordLock).filter(
                RecordLock.expires_at < datetime.utcnow()
            ).delete()
            session.flush()

            existing = session.query(RecordLock).filter(
                and_(RecordLock.record_id == record_id,
                     RecordLock.expires_at >= datetime.utcnow())
            ).first()

            if existing:
                if existing.locked_by == username:
                    existing.expires_at = datetime.utcnow() + timedelta(seconds=LOCK_TTL_SECONDS)
                    session.commit()
                    return True, None
                return False, existing.locked_by

            session.add(RecordLock(
                record_id  = record_id,
                locked_by  = username,
                locked_at  = datetime.utcnow(),
                expires_at = datetime.utcnow() + timedelta(seconds=LOCK_TTL_SECONDS),
                session_id = session_id,
            ))
            session.commit()
            return True, None
    except Exception as e:
        print(f"[lock] DB acquire failed — using memory: {e}")
        return _acquire_memory(record_id, username, session_id)


def _release_db(record_id, username):
    try:
        from data.database import get_session
        from data.models import RecordLock
        with get_session() as session:
            deleted = session.query(RecordLock).filter(
                RecordLock.record_id == record_id,
                RecordLock.locked_by == username,
            ).delete()
            session.commit()
            return deleted > 0
    except Exception as e:
        print(f"[lock] DB release failed: {e}")
        return _release_memory(record_id, username)


def _status_db(record_id):
    try:
        from data.database import get_session
        from data.models import RecordLock
        with get_session() as session:
            lock = session.query(RecordLock).filter(
                RecordLock.record_id == record_id,
                RecordLock.expires_at >= datetime.utcnow(),
            ).first()
            if not lock:
                return None
            return {
                "locked_by":         lock.locked_by,
                "expires_at":        lock.expires_at.isoformat(),
                "minutes_remaining": max(0, int((lock.expires_at - datetime.utcnow()).total_seconds() / 60)),
            }
    except Exception as e:
        print(f"[lock] DB status failed: {e}")
        return _status_memory(record_id)


def _extend_db(record_id, username):
    try:
        from data.database import get_session
        from data.models import RecordLock
        with get_session() as session:
            lock = session.query(RecordLock).filter(
                RecordLock.record_id == record_id,
                RecordLock.locked_by == username,
            ).first()
            if lock:
                lock.expires_at = datetime.utcnow() + timedelta(seconds=LOCK_TTL_SECONDS)
                session.commit()
                return True
            return False
    except Exception as e:
        print(f"[lock] DB extend failed: {e}")
        return _extend_memory(record_id, username)
