import os

# Must be set before app.db is imported, so the engine points at the test DB.
os.environ["DATABASE_URL"] = (
    "postgresql+psycopg://bike:bike@localhost:5432/bike_tracker_test"
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402


@pytest.fixture(autouse=True)
def clean_db():
    with engine.begin() as conn:
        conn.execute(
            text("TRUNCATE rides, components, bikes, users RESTART IDENTITY CASCADE")
        )
    yield


@pytest.fixture
def client():
    return TestClient(app)


def _create_user(email: str) -> int:
    with SessionLocal() as session:
        user = User(email=email)
        session.add(user)
        session.commit()
        return user.id


@pytest.fixture
def alice_id():
    return _create_user("alice@example.com")


@pytest.fixture
def bob_id():
    return _create_user("bob@example.com")
