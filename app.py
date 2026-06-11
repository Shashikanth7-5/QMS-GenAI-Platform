"""
app.py · QMS GenAI — Sprint 2
"""

import sys
import os

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from flask import Flask, jsonify
from flask_login import LoginManager
from config import SECRET_KEY, PORT
from auth.users import get_user_by_id


def create_app() -> Flask:
    app = Flask(__name__,
                static_folder="static",
                template_folder="templates")
    app.config["SECRET_KEY"] = SECRET_KEY

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

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(capa_bp)
    app.register_blueprint(rca_bp)
    app.register_blueprint(decision_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(rag_bp)

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Route not found", "status": 404}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"error": "Internal server error", "status": 500}), 500

    @app.template_filter("avatarcolor")
    def avatarcolor(n):
        colors = ["#4f7df3","#2dd98f","#f5a623","#a78bfa","#f472b6","#38bdf8"]
        return colors[int(n) % len(colors)]

    return app

from database import init_db
init_db()   # creates qms_data.db automatically on first run

app = create_app()


if __name__ == "__main__":
    print("""
  ╔══════════════════════════════════════════════════╗
  ║   QMS GenAI  ·  Sprint 2                        ║
  ║   admin / admin  |  quality / admin             ║
  ╚══════════════════════════════════════════════════╝
    """)
    app.run(host="127.0.0.1", port=PORT, debug=os.getenv("FLASK_DEBUG") == "true")
