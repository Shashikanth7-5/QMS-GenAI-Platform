# auth/users.py
# Three roles:
#   admin   — full system access
#   quality — can view all records, create CAPAs on any record, no approve/reject
#   user    — own records only, read-only ID lookup, own CAPAs only
#
# Seed credentials (admin/admin, shashi/admin, quality/admin) are loaded
# ONLY when SEED_BUILTIN_USERS=true (the default outside production).
# See config.SEED_BUILTIN_USERS.

import json
import os
import re
import time
from datetime import datetime
from threading import Lock
from typing import Optional

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from config import (
    LOGIN_LOCKOUT_ATTEMPTS,
    LOGIN_LOCKOUT_COOLDOWN_SECONDS,
    LOGIN_LOCKOUT_WINDOW_SECONDS,
    PASSWORD_MIN_LENGTH,
    PASSWORD_REQUIRE_COMPLEXITY,
    SEED_BUILTIN_USERS,
)
from services.logging_config import get_logger

log = get_logger(__name__)

_DATA_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "users_data.json")
)
_USERS_LOCK = Lock()

ROLES = ("admin", "quality", "user")
RESERVED_USERNAMES = {"admin", "quality", "system", "root", "shashi", "responsible-ai-agent"}


class User(UserMixin):
    def __init__(self, id, username, password, role,
                 full_name, status="approved", created_at=None,
                 reject_comment="", email="", _hashed=False):
        self.id = str(id)
        self.username = username.lower()
        self._pw_hash = password if _hashed else generate_password_hash(password)
        self.role = role
        self.full_name = full_name
        self.email = (email or _infer_email(username)).strip().lower()
        self.status = status
        self.created_at = created_at or datetime.now().strftime("%Y-%m-%d %H:%M")
        self.reject_comment = reject_comment

    # ── Password ──────────────────────────────────────────
    def check_password(self, password: str) -> bool:
        return check_password_hash(self._pw_hash, password)

    def set_password(self, new_password: str) -> None:
        self._pw_hash = generate_password_hash(new_password)

    # ── Flask-Login required ──────────────────────────────
    def is_active(self):
        return self.status == "approved"

    # ── Role helpers ──────────────────────────────────────
    def is_admin(self) -> bool:
        return self.role == "admin"

    def is_quality(self) -> bool:
        return self.role == "quality"

    def is_user(self) -> bool:
        return self.role == "user"

    def can_create_capa(self) -> bool:
        return self.role in ("admin", "quality")

    def can_approve_capa(self) -> bool:
        return self.role == "admin"

    def can_run_batch(self) -> bool:
        return self.role == "admin"

    def sees_all_records(self) -> bool:
        return self.role in ("admin", "quality")

    def sees_system_metrics(self) -> bool:
        return self.role in ("admin", "quality")

    # ── Serialisation ─────────────────────────────────────
    def to_dict(self):
        return {
            "id":               self.id,
            "username":         self.username,
            "email":            self.email,
            "full_name":        self.full_name,
            "role":             self.role,
            "status":           self.status,
            "created_at":       self.created_at,
            "is_admin":         self.is_admin(),
            "is_quality":       self.is_quality(),
            "can_create_capa":  self.can_create_capa(),
            "can_approve_capa": self.can_approve_capa(),
            "can_run_batch":    self.can_run_batch(),
            "sees_all_records": self.sees_all_records(),
            "reject_comment":   self.reject_comment,
        }

    def _to_json(self):
        return {
            "id":             self.id,
            "username":       self.username,
            "email":          self.email,
            "pw_hash":        self._pw_hash,
            "role":           self.role,
            "full_name":      self.full_name,
            "status":         self.status,
            "created_at":     self.created_at,
            "reject_comment": self.reject_comment,
        }


# ── Built-in accounts ─────────────────────────────────────
def _infer_email(username: str) -> str:
    value = (username or "").strip().lower()
    if "@" in value:
        return value
    domain = os.getenv("QMS_DEFAULT_EMAIL_DOMAIN", "example.com").strip() or "example.com"
    return f"{value}@{domain}" if value else ""


def _seed_users() -> list:
    """Seed accounts used for demos and CI. Never loaded in production unless SEED_BUILTIN_USERS=true."""
    if not SEED_BUILTIN_USERS:
        return []
    return [
        User("1", "admin",   "admin", "admin",   "Admin",         "approved", email=_infer_email("admin")),
        User("2", "shashi",  "admin", "user",    "Shashi",        "approved", email=_infer_email("shashi")),
        User("3", "quality", "admin", "quality", "Quality Lead",  "approved", email=_infer_email("quality")),
    ]


_BUILTIN = _seed_users()
if not SEED_BUILTIN_USERS:
    log.info("auth.seed.disabled", extra={"reason": "SEED_BUILTIN_USERS=false"})

_REGISTERED: list = []
_NEXT_ID = 10   # start above built-ins


# ── Password policy ───────────────────────────────────────
def _validate_password(password: str) -> Optional[str]:
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"Password must be at least {PASSWORD_MIN_LENGTH} characters."
    if PASSWORD_REQUIRE_COMPLEXITY:
        if not re.search(r"[A-Z]", password):
            return "Password must contain at least one uppercase letter."
        if not re.search(r"[a-z]", password):
            return "Password must contain at least one lowercase letter."
        if not re.search(r"\d", password):
            return "Password must contain at least one digit."
        if not re.search(r"[^A-Za-z0-9]", password):
            return "Password must contain at least one symbol."
    return None


# ── Persistence ────────────────────────────────────────────
def _load():
    global _REGISTERED, _NEXT_ID
    if not os.path.exists(_DATA_FILE):
        return
    try:
        with open(_DATA_FILE, "r") as f:
            data = json.load(f)
        _REGISTERED = [
            User(
                id             = r["id"],
                username       = r["username"],
                password       = r["pw_hash"],
                role           = r.get("role", "user"),
                full_name      = r["full_name"],
                status         = r["status"],
                created_at     = r["created_at"],
                reject_comment = r.get("reject_comment", ""),
                email          = r.get("email", ""),
                _hashed        = True,
            )
            for r in data.get("users", [])
        ]
        if _REGISTERED:
            _NEXT_ID = max(int(u.id) for u in _REGISTERED) + 1
    except Exception:
        log.exception("auth.users.load_failed", extra={"path": _DATA_FILE})


def _save():
    tmp = f"{_DATA_FILE}.tmp"
    try:
        with _USERS_LOCK:
            with open(tmp, "w") as f:
                json.dump({"users": [u._to_json() for u in _REGISTERED]}, f, indent=2)
            os.replace(tmp, _DATA_FILE)
    except Exception:
        log.exception("auth.users.save_failed", extra={"path": _DATA_FILE})


_load()


def _all_users():
    return _BUILTIN + _REGISTERED


# ── Public API ─────────────────────────────────────────────
def get_user_by_id(user_id: str):
    return next((u for u in _all_users() if u.id == str(user_id)), None)


def get_user_by_username(username: str):
    return next(
        (u for u in _all_users() if u.username == username.strip().lower()), None
    )


def get_all_registered_users():
    return list(_REGISTERED)


def get_pending_users():
    return [u for u in _REGISTERED if u.status == "pending"]


def username_exists(username: str) -> bool:
    return get_user_by_username(username) is not None


def register_user(username: str, password: str, full_name: str, role: str = "user", email: str = ""):
    global _NEXT_ID
    uname = username.strip().lower()
    if uname in RESERVED_USERNAMES:
        return None, f"Username '{uname}' is reserved."
    if username_exists(uname):
        return None, f"Username '{uname}' is already taken."
    policy_error = _validate_password(password)
    if policy_error:
        return None, policy_error
    if not full_name.strip():
        return None, "Full name is required."
    if role not in ROLES:
        role = "user"
    user = User(
        id         = str(_NEXT_ID),
        username   = uname,
        password   = password,
        role       = role,
        full_name  = full_name.strip(),
        status     = "pending",
        email      = email.strip().lower() or _infer_email(uname),
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    _NEXT_ID += 1
    _REGISTERED.append(user)
    _save()
    return user, None


def update_user_status(user_id: str, new_status: str, comment: str = ""):
    user = next((u for u in _REGISTERED if u.id == str(user_id)), None)
    if user:
        user.status = new_status
        if new_status == "rejected":
            user.reject_comment = comment
        elif new_status == "approved":
            user.reject_comment = ""
        _save()
    return user


def update_user_role(user_id: str, new_role: str):
    if new_role not in ROLES:
        return None
    user = next((u for u in _REGISTERED if u.id == str(user_id)), None)
    if user:
        user.role = new_role
        _save()
    return user


# ── Login lockout tracking ─────────────────────────────────
_lockout_state: dict[str, dict] = {}
_lockout_lock = Lock()


def _lockout_key(username: str, ip: str) -> str:
    return f"{(username or '').lower()}|{ip or 'unknown'}"


def is_locked_out(username: str, ip: str) -> tuple[bool, int]:
    """Return (locked, seconds_remaining)."""
    key = _lockout_key(username, ip)
    with _lockout_lock:
        state = _lockout_state.get(key)
        if not state:
            return False, 0
        if state.get("locked_until", 0) > time.time():
            return True, int(state["locked_until"] - time.time())
        return False, 0


def record_login_failure(username: str, ip: str) -> None:
    key = _lockout_key(username, ip)
    now = time.time()
    with _lockout_lock:
        state = _lockout_state.get(key, {"failures": [], "locked_until": 0})
        cutoff = now - LOGIN_LOCKOUT_WINDOW_SECONDS
        state["failures"] = [t for t in state.get("failures", []) if t > cutoff]
        state["failures"].append(now)
        if len(state["failures"]) >= LOGIN_LOCKOUT_ATTEMPTS:
            state["locked_until"] = now + LOGIN_LOCKOUT_COOLDOWN_SECONDS
        _lockout_state[key] = state
    log.warning(
        "auth.login.failure",
        extra={"username": username, "ip": ip, "failures": len(state["failures"])},
    )


def record_login_success(username: str, ip: str) -> None:
    key = _lockout_key(username, ip)
    with _lockout_lock:
        _lockout_state.pop(key, None)
