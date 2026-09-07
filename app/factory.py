import os

from flask import Flask, send_from_directory

from app.models import db

STATIC_FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "static_frontend")


def create_app(db_path=None):
    app = Flask(__name__)
    db_path = db_path or os.path.join(os.getcwd(), "reconciliation.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = "dev"  # take-home scope: no real auth/session security needed
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # reject oversized uploads before they're read into memory

    db.init_app(app)

    from app.api import bp
    app.register_blueprint(bp)

    # Dev-only: React runs on its own Vite server (localhost:5173) and calls
    # this API directly, so it needs CORS. Not needed once the frontend is
    # built (`npm run build`) and served as static files from this same
    # origin by the route below.
    if app.config.get("ENV") != "production":
        from flask_cors import CORS
        CORS(app, resources={r"/api/*": {"origins": "*"}})

    if os.path.isdir(STATIC_FRONTEND_DIR):
        @app.route("/", defaults={"path": ""})
        @app.route("/<path:path>")
        def serve_frontend(path):
            full_path = os.path.join(STATIC_FRONTEND_DIR, path)
            if path and os.path.isfile(full_path):
                return send_from_directory(STATIC_FRONTEND_DIR, path)
            return send_from_directory(STATIC_FRONTEND_DIR, "index.html")

    with app.app_context():
        db.create_all()

    return app
