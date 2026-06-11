# routes/auth.py

from flask import (Blueprint, render_template, request,
                   redirect, url_for, flash, jsonify)
from flask_login import (login_user, logout_user,
                         login_required, current_user)
from auth.users import (get_user_by_username, get_all_registered_users,
                        get_pending_users, register_user,
                        update_user_status, update_user_role, get_user_by_id)
from functools import wraps

auth_bp = Blueprint("auth", __name__)


def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin():
            return render_template("auth/not_authorised.html"), 403
        return fn(*args, **kwargs)
    return wrapper


# ── Login ──────────────────────────────────────────────────
@auth_bp.route("/login", methods=["GET","POST"])
def page_login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.page_dashboard"))
    error = None
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","").strip()
        remember = request.form.get("remember") == "on"
        user     = get_user_by_username(username)
        if not user:
            error = "Username not found."
        elif user.status == "pending":
            error = "Account pending admin approval."
        elif user.status == "rejected":
            error = "Account request not approved. Contact admin."
        elif not user.check_password(password):
            error = "Incorrect password."
        else:
            login_user(user, remember=remember)
            try:
                from services.audit_service import log, ACTION_USER_LOGIN
                log(ACTION_USER_LOGIN,
                    performed_by=user.username,
                    performed_by_role=user.role,
                    entity_type="user",
                    notes="User logged in",
                    ip_address=request.remote_addr,
                    )
            except Exception:
                pass
            return redirect(request.args.get("next") or url_for("dashboard.page_dashboard"))
    return render_template("auth/login.html", error=error)


# ── Logout ─────────────────────────────────────────────────
@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.page_login"))


# ── Register ───────────────────────────────────────────────
@auth_bp.route("/register", methods=["GET","POST"])
def page_register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.page_dashboard"))
    error   = None
    success = None
    if request.method == "POST":
        username  = request.form.get("username","").strip()
        password  = request.form.get("password","").strip()
        full_name = request.form.get("full_name","").strip()
        role      = request.form.get("role","user")
        user, err = register_user(username, password, full_name, role)
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
        pending  = [u for u in registered if u.status == "pending"],
        approved = [u for u in registered if u.status == "approved"],
        rejected = [u for u in registered if u.status == "rejected"],
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
    update_user_status(user_id, "rejected", comment=request.form.get("comment","").strip())
    flash("User rejected.", "error")
    return redirect(url_for("auth.page_manage_users"))


@auth_bp.route("/admin/users/<user_id>/role", methods=["POST"])
@admin_required
def change_role(user_id):
    new_role = request.form.get("role","user")
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
