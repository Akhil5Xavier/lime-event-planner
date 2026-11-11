import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["TICKETMASTER_API_KEY"] = ""
os.environ["PREDICTHQ_TOKEN"] = ""
# Environment variables win over backend/.env, so a developer's local .env can't leak into tests.
os.environ["ENVIRONMENT"] = "development"
os.environ["ALERT_WEBHOOK_URL"] = ""
os.environ["SENTRY_DSN"] = ""
os.environ["LOG_FORMAT"] = "text"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.seed.venues import seed_venues  # noqa: E402

PASSWORD = "correct-horse"
# bcrypt is slow on purpose (~0.3 s per hash); hash once instead of twice per test.
PASSWORD_HASH = hash_password(PASSWORD)


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        seed_venues(db)
        db.add_all([
            User(email="admin@lime-ops.de", role="admin", password_hash=PASSWORD_HASH),
            User(email="manager@lime-ops.de", role="manager", password_hash=PASSWORD_HASH),
        ])
        db.commit()
    yield factory
    engine.dispose()


@pytest.fixture
def db(session_factory):
    with session_factory() as session:
        yield session


@pytest.fixture
def client(session_factory):
    def _get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _login(client, email):
    resp = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def manager_headers(client):
    return _login(client, "manager@lime-ops.de")


@pytest.fixture
def admin_headers(client):
    return _login(client, "admin@lime-ops.de")
