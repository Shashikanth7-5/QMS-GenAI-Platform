"""Request- and Celery-safe correlation context.

Emits `run_id`, `tenant_id`, and `user` as top-level fields on every log
line + LLM call log row. Uses contextvars so async / thread-pool code
inherits the same context without threading it through every call.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional

_run_id_var: ContextVar[Optional[str]] = ContextVar("qms_run_id", default=None)
_tenant_var: ContextVar[Optional[str]] = ContextVar("qms_tenant_id", default=None)
_user_var: ContextVar[Optional[str]] = ContextVar("qms_user", default=None)


def new_run_id(prefix: str = "REQ") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


def get_run_id() -> Optional[str]:
    return _run_id_var.get()


def get_tenant_id() -> Optional[str]:
    return _tenant_var.get()


def get_user() -> Optional[str]:
    return _user_var.get()


def set_run_id(run_id: Optional[str]) -> None:
    _run_id_var.set(run_id)


def set_tenant_id(tenant_id: Optional[str]) -> None:
    _tenant_var.set(tenant_id)


def set_user(user: Optional[str]) -> None:
    _user_var.set(user)


@contextmanager
def run_scope(
    *,
    run_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    user: Optional[str] = None,
    prefix: str = "REQ",
):
    """Context manager that binds correlation IDs for the duration of a block."""
    tokens = []
    tokens.append(_run_id_var.set(run_id or new_run_id(prefix)))
    tokens.append(_tenant_var.set(tenant_id))
    tokens.append(_user_var.set(user))
    try:
        yield {
            "run_id": _run_id_var.get(),
            "tenant_id": _tenant_var.get(),
            "user": _user_var.get(),
        }
    finally:
        _run_id_var.reset(tokens[0])
        _tenant_var.reset(tokens[1])
        _user_var.reset(tokens[2])


def snapshot() -> dict:
    """Copy of the current run context as a dict — safe to put in `extra=`."""
    return {
        "run_id": _run_id_var.get(),
        "tenant_id": _tenant_var.get(),
        "user": _user_var.get(),
    }
