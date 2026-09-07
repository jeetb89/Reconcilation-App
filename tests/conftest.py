import pytest

from app.factory import create_app
from app.models import db


@pytest.fixture
def app(tmp_path):
    app = create_app(db_path=str(tmp_path / "test.db"))
    app.config["TESTING"] = True
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
