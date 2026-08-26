# ══════════════════════════════════════════════════════════════
# ADD THIS TO routes/auth.py
# Paste this function anywhere inside auth.py
# It provides the credential verification for digital signatures
# ══════════════════════════════════════════════════════════════

from flask_login import login_required, current_user
from werkzeug.security import check_password_hash
from auth.users import get_user_by_username
from services.audit_service import log

@auth_bp.route("/api/auth/verify-signature", methods=["POST"])
@login_required
def verify_signature():
    """
    Verifies username + password for electronic signature.
    The signer must be an admin AND must provide their own credentials.
    21 CFR Part 11 §11.100(b) — at least two components for electronic sig.
    Returns: { "valid": true/false, "username": "...", "role": "..." }
    """
    body     = request.get_json(force=True) or {}
    username = body.get("username", "").strip()
    password = body.get("password", "")

    if not username or not password:
        return jsonify({"valid": False, "error": "Username and password required"}), 400

    # Must match the currently logged-in user (prevents signing as someone else)
    if username != current_user.username:
        # Audit log failed signature attempt
        log("signature_failed", current_user.username, current_user.role,
            entity_type="signature",
            notes=f"Attempted to sign as {username} while logged in as {current_user.username}",
            ip_address=request.remote_addr)
        return jsonify({"valid": False, "error": "Username must match your logged-in account"}), 400

    # Verify password
    user = get_user_by_username(username)
    if not user:
        return jsonify({"valid": False, "error": "User not found"}), 400

    if not check_password_hash(user.password_hash, password):
        log("signature_failed", current_user.username, current_user.role,
            entity_type="signature",
            notes=f"Invalid password for signature by {username}",
            ip_address=request.remote_addr)
        return jsonify({"valid": False, "error": "Invalid password"}), 401

    # Only admin can approve/reject
    if user.role != "admin":
        return jsonify({"valid": False, "error": "Only admin role can sign CAPA approvals"}), 403

    # Log successful verification
    log("signature_verified", current_user.username, current_user.role,
        entity_type="signature",
        notes=f"Electronic signature verified for {username}",
        ip_address=request.remote_addr)

    return jsonify({
        "valid":     True,
        "username":  username,
        "role":      user.role,
        "timestamp": __import__('datetime').datetime.utcnow().isoformat() + "Z",
    })
