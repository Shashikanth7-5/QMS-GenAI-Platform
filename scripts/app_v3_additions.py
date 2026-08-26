# ══════════════════════════════════════════════════════════════
# app.py — ADDITIONS for Sprint 3
# Add these changes to your existing app.py
# ══════════════════════════════════════════════════════════════

# ── 1. Add this import alongside the other blueprint imports ──
from routes.api_v1 import api_v1_bp

# ── 2. Register it alongside the other app.register_blueprint calls ──
app.register_blueprint(api_v1_bp)

# ── 3. Add security headers (add this function inside create_app) ──
@app.after_request
def security_headers(response):
    # Prevent MIME sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # Prevent clickjacking
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    # XSS protection
    response.headers['X-XSS-Protection'] = '1; mode=block'
    # Remove server header
    response.headers.pop('Server', None)
    return response

# ── 4. Add file upload size limit (inside create_app) ──
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max upload

# ── 5. Add to .env (new variables) ──
# API_V1_KEY=your-secret-api-key-here          # share with Salesforce
# SF_WEBHOOK_SECRET=your-webhook-secret        # Salesforce webhook verification
# CORS_ORIGINS=https://*.salesforce.com,https://*.force.com

# ══════════════════════════════════════════════════════════════
# COMPLETE UPDATED create_app() function for reference:
# ══════════════════════════════════════════════════════════════
"""
def create_app() -> Flask:
    app = Flask(__name__,
                static_folder="static",
                template_folder="templates")
    app.config["SECRET_KEY"] = SECRET_KEY
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB upload limit

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view             = "auth.page_login"
    login_manager.login_message          = "Please log in to access QMS GenAI."
    login_manager.login_message_category = "info"

    @login_manager.user_loader
    def load_user(user_id):
        return get_user_by_id(user_id)

    from routes.auth      import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.capa      import capa_bp
    from routes.rca       import rca_bp
    from routes.decision  import decision_bp
    from routes.analytics import analytics_bp
    from routes.search    import search_bp
    from routes.rag       import rag_bp
    from routes.api_v1    import api_v1_bp       # ← NEW

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(capa_bp)
    app.register_blueprint(rca_bp)
    app.register_blueprint(decision_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(rag_bp)
    app.register_blueprint(api_v1_bp)            # ← NEW

    @app.after_request
    def security_headers(response):               # ← NEW
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers.pop('Server', None)
        return response

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Route not found", "status": 404}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"error": "Internal server error", "status": 500}), 500

    @app.errorhandler(413)
    def file_too_large(e):
        return jsonify({"error": "File too large. Maximum 16 MB.", "status": 413}), 413

    @app.template_filter("avatarcolor")
    def avatarcolor(n):
        colors = ["#4f7df3","#2dd98f","#f5a623","#a78bfa","#f472b6","#38bdf8"]
        return colors[int(n) % len(colors)]

    return app
"""
