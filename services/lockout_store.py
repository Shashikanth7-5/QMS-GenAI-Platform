"""Login lockout store — Redis with in-memory fallback.

Multi-worker gunicorn made the previous in-memory lockout easy to bypass
(attackers rotated through workers). Everything here is keyed by username
and uses a small Redis hash so all workers share state.
"""

from __future__ import annotations

import json
import time
from threading import Lock
from typing import Optional

from services.logging_config import get_logger

log = get_logger(__name__)

_KEY_PREFIX = "qms:lockout:"

# In-memory fallback when Redis is unavailable (dev / tests).
_MEMORY: dict[str, dict] = {}
_MEMORY_LOCK = Lock()

_redis_client = None
_redis_probed = False


def _get_redis():
    """Lazy Redis client with graceful fallback."""
    global _redis_client, _redis_probed
    if _redis_probed:
        return _redis_client
    _redis_probed = True
    try:
        import os
        import redis  # type: ignore
        url = (os.getenv("RATE_LIMIT_STORAGE_URI") or os.getenv("REDIS_URL") or "").strip()
        if not url or not url.startswith("redis"):
            log.info("lockout.no_redis_configured_using_memory")
            return None
        client = redis.Redis.from_url(url, decode_responses=True, socket_timeout=1.0)
        client.ping()
        _redis_client = client
        return client
    except Exception:
        log.warning("lockout.redis_unavailable_using_memory", exc_info=True)
        _redis_client = None
        return None


def _now() -> int:
    return int(time.time())


def get_state(username: str) -> Optional[dict]:
    """Return {'failures': [...], 'locked_until': int} or None."""
    key = _KEY_PREFIX + username.lower()
    client = _get_redis()
    if client is not None:
        try:
            raw = client.get(key)
            return json.loads(raw) if raw else None
        except Exception:
            log.warning("lockout.redis_read_failed", exc_info=True)
    with _MEMORY_LOCK:
        state = _MEMORY.get(key)
        return dict(state) if state else None


def _write_state(key: str, state: dict, ttl_seconds: int) -> None:
    client = _get_redis()
    if client is not None:
        try:
            client.set(key, json.dumps(state), ex=max(60, ttl_seconds))
            return
        except Exception:
            log.warning("lockout.redis_write_failed_memory_fallback", exc_info=True)
    with _MEMORY_LOCK:
        _MEMORY[key] = state


def record_failure(username: str, *, window_seconds: int, threshold: int,
                   cooldown_seconds: int) -> dict:
    """Register a failed login. Returns the updated state."""
    key = _KEY_PREFIX + username.lower()
    now = _now()
    state = get_state(username) or {"failures": [], "locked_until": 0}
    # Trim failures outside the window.
    state["failures"] = [t for t in state["failures"] if now - int(t) <= window_seconds]
    state["failures"].append(now)
    if len(state["failures"]) >= threshold:
        state["locked_until"] = now + cooldown_seconds
        state["failures"] = []
    _write_state(key, state, cooldown_seconds + window_seconds)
    return state


def is_locked(username: str) -> tuple[bool, int]:
    """Return (locked, seconds_until_unlock)."""
    state = get_state(username)
    if not state:
        return False, 0
    remaining = int(state.get("locked_until", 0)) - _now()
    return (remaining > 0, max(0, remaining))


def clear(username: str) -> None:
    """Successful login — wipe the counter."""
    key = _KEY_PREFIX + username.lower()
    client = _get_redis()
    if client is not None:
        try:
            client.delete(key)
        except Exception:
            log.warning("lockout.redis_clear_failed", exc_info=True)
    with _MEMORY_LOCK:
        _MEMORY.pop(key, None)
