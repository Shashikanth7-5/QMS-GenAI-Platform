# routes/auth.py

from functools import wraps
from urllib.parse import urljoin, urlparse

from flask import (Blueprint, current_app, flash, jsonify,
                   redirect, render_template, request, url_for)
from flask_login import (current_user, login_required, login_user, logout_user)

from auth.users import (get_all_registered_users, get_pending_users,
                        get_user_by_username, is_locked_out,
                        record_login_failure, record_login_success,
                        register_user, update_user_role, update_user_status)
from config import RATE_LIMIT_LOGIN
from services.logging_config import get_logger

log = get_logger(__name__)

auth_bp = Blueprint("auth", __name__)


def _limiter():
    return current_app.extensions.get("qms_limiter") if current_app else None


def _is_safe_redirect(target: str) -> bool:
    """Only allow same-host relative redirects to defeat next= open-redirect."""
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return (
        test_url.scheme in ("http", "https")
        and ref_url.netloc == test_url.netloc
    )


def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin():
            return render_template("auth/not_authorised.html"), 403
        return fn(*args, **kwargs)
    return wrapper


# ── Login ──────────────────────────────────────────────────
@auth_bp.route("/login", methods=["GET", "POST"])
def page_login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.page_dashboard"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        remember = request.form.get("remember") == "on"
        client_ip = request.remote_addr or ""

        locked, retry_after = is_locked_out(username, client_ip)
        if locked:
            error = f"Too many failed attempts. Try again in {retry_after} seconds."
            log.warning("auth.login.locked",
                        extra={"username": username, "ip": client_ip, "retry_after": retry_after})
            return render_template("auth/login.html", error=error), 429

        user = get_user_by_username(username)
        if not user:
            error = "Username not found."
        elif user.status == "pending":
            error = "Account pending admin approval."
        elif user.status == "rejected":
            error = "Account request not approved. Contact admin."
        elif not user.check_password(password):
            error = "Incorrect password."
        else:
            record_login_success(username, client_ip)
            login_user(user, remember=remember)
            try:
                from services.audit_service import ACTION_USER_LOGIN, log as audit_log
                audit_log(
                    ACTION_USER_LOGIN,
                    performed_by=user.username,
                    performed_by_role=user.role,
                    entity_type="user",
                    notes="User logged in",
                    ip_address=client_ip,
                )
            except Exception:
                log.exception("auth.login.audit_failed", extra={"username": user.username})

            next_url = request.args.get("next") or ""
            if next_url and _is_safe_redirect(next_url):
                return redirect(next_url)
            return redirect(url_for("dashboard.page_dashboard"))

        record_login_failure(username, client_ip)
    return render_template("auth/login.html", error=error)


def _apply_login_limit():
    limiter = _limiter()
    if not limiter:
        return
    try:
        limiter.limit(RATE_LIMIT_LOGIN)(page_login)
    except Exception:
        log.exception("auth.login.rate_limit_attach_failed")


# ── Logout ─────────────────────────────────────────────────
@auth_bp.route("/logout")
@login_required
def logout():
    username = current_user.username
    logout_user()
    log.info("auth.logout", extra={"username": username})
    return redirect(url_for("auth.page_login"))


# ── Register ───────────────────────────────────────────────
@auth_bp.route("/register", methods=["GET", "POST"])
def page_register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.page_dashboard"))
    error = None
    success = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        full_name = request.form.get("full_name", "").strip()
        role = request.form.get("role", "user")
        user, err = register_user(username, password, full_name, role, email)
        if err:
            error = err
        else:
            success = f"Account request submitted for '{user.username}'. An admin will review it."
    return render_template("auth/register.html", error=error, success=success)


# ── Admin: manage users ────────────────────────────────────
@auth_bp.route("/admin/users")
@admin_required
def page_manage_users():
    registered = get_all_registered_users()
    return render_template("auth/manage_users.html",
        pending=[u for u in registered if u.status == "pending"],
        approved=[u for u in registered if u.status == "approved"],
        rejected=[u for u in registered if u.status == "rejected"],
    )


@auth_bp.route("/admin/users/<user_id>/approve", methods=["POST"])
@admin_required
def approve_user(user_id):
    update_user_status(user_id, "approved")
    flash("User approved.", "success")
    return redirect(url_for("auth.page_manage_users"))


@auth_bp.route("/admin/users/<user_id>/reject", methods=["POST"])
@admin_required
def reject_user(user_id):
    update_user_status(user_id, "rejected", comment=request.form.get("comment", "").strip())
    flash("User rejected.", "error")
    return redirect(url_for("auth.page_manage_users"))


@auth_bp.route("/admin/users/<user_id>/role", methods=["POST"])
@admin_required
def change_role(user_id):
    new_role = request.form.get("role", "user")
    update_user_role(user_id, new_role)
    flash(f"Role updated to '{new_role}'.", "success")
    return redirect(url_for("auth.page_manage_users"))


# ── API ─────────────────────────────────────────────────────
@auth_bp.route("/api/auth/me")
@login_required
def api_me():
    return jsonify(current_user.to_dict())


@auth_bp.route("/api/auth/pending-count")
@login_required
def api_pending_count():
    if not current_user.is_admin():
        return jsonify({"count": 0})
    return jsonify({"count": len(get_pending_users())})


# Register the login rate limit once the blueprint is imported.
@auth_bp.record_once
def _on_blueprint_registered(setup_state):
    with setup_state.app.app_context():
        _apply_login_limit()
