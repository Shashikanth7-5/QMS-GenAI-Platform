# auth/users.py
# Three roles:
#   admin   — full system access
#   quality — can view all records, create CAPAs on any record, no approve/reject
#   user    — own records only, read-only ID lookup, own CAPAs only

import json
import os
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

_DATA_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "users_data.json")
)

ROLES = ("admin", "quality", "user")


class User(UserMixin):
    def __init__(self, id, username, password, role,
                 full_name, status="approved", created_at=None,
                 reject_comment="", _hashed=False):
        self.id             = str(id)
        self.username       = username.lower()
        self._pw_hash       = password if _hashed else generate_password_hash(password)
        self.role           = role
        self.full_name      = full_name
        self.status         = status
        self.created_at     = created_at or datetime.now().strftime("%Y-%m-%d %H:%M")
        self.reject_comment = reject_comment

    # ── Password ──────────────────────────────────────────
    def check_password(self, password: str) -> bool:
        return check_password_hash(self._pw_hash, password)

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
        """admin and quality can create CAPAs on ANY record."""
        return self.role in ("admin", "quality")

    def can_approve_capa(self) -> bool:
        """Only admin can approve / reject / close CAPAs."""
        return self.role == "admin"

    def can_run_batch(self) -> bool:
        """Only admin can run the batch agent."""
        return self.role == "admin"

    def sees_all_records(self) -> bool:
        """admin and quality see all records; user sees only their own."""
        return self.role in ("admin", "quality")

    def sees_system_metrics(self) -> bool:
        """admin and quality see system-wide metrics; user sees personal counts."""
        return self.role in ("admin", "quality")

    # ── Serialisation ─────────────────────────────────────
    def to_dict(self):
        return {
            "id":               self.id,
            "username":         self.username,
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
            "pw_hash":        self._pw_hash,
            "role":           self.role,
            "full_name":      self.full_name,
            "status":         self.status,
            "created_at":     self.created_at,
            "reject_comment": self.reject_comment,
        }


# ── Built-in accounts (never written to JSON) ──────────────
_BUILTIN = [
    User("1", "admin",   "admin", "admin",   "Admin",         "approved"),
    User("2", "shashi",  "admin", "user",    "Shashi",        "approved"),
    User("3", "quality", "admin", "quality", "Quality Lead",  "approved"),
]

_REGISTERED: list = []
_NEXT_ID = 10   # start above built-ins


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
                _hashed        = True,
            )
            for r in data.get("users", [])
        ]
        if _REGISTERED:
            _NEXT_ID = max(int(u.id) for u in _REGISTERED) + 1
    except Exception as e:
        print(f"[users] Warning: could not load {_DATA_FILE}: {e}")


def _save():
    try:
        with open(_DATA_FILE, "w") as f:
            json.dump({"users": [u._to_json() for u in _REGISTERED]}, f, indent=2)
    except Exception as e:
        print(f"[users] Warning: could not save {_DATA_FILE}: {e}")


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


def register_user(username: str, password: str, full_name: str, role: str = "user"):
    global _NEXT_ID
    uname = username.strip().lower()
    if uname in ("admin", "quality"):
        return None, f"Username '{uname}' is reserved."
    if username_exists(uname):
        return None, f"Username '{uname}' is already taken."
    if len(password) < 4:
        return None, "Password must be at least 4 characters."
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
    """Admin can change a registered user's role."""
    if new_role not in ROLES:
        return None
    user = next((u for u in _REGISTERED if u.id == str(user_id)), None)
    if user:
        user.role = new_role
        _save()
    return user
