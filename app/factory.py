import os

from flask import Flask

from app.models import db


def create_app(db_path=None):
    app = Flask(__name__)
    db_path = db_path or os.path.join(os.getcwd(), "reconciliation.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = "dev"  # take-home scope: no real auth/session security needed

    db.init_app(app)

    from app.api import bp
    app.register_blueprint(bp)

    # Dev-only: the frontend will run on its own dev server and call this
    # API directly, so it needs CORS.
    if app.config.get("ENV") != "production":
        from flask_cors import CORS
        CORS(app, resources={r"/api/*": {"origins": "*"}})

    with app.app_context():
        db.create_all()

    return app
