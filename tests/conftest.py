"""
conftest.py — Shared pytest fixtures using in-memory SQLite.
"""

import io
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from PIL import Image

from database import Base, get_db
from main import app

TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session():
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def make_image_bytes(color=(200, 10, 10)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (224, 224), color).save(buf, format="JPEG")
    buf.seek(0)
    return buf.read()

@pytest.fixture
def red_image():  return make_image_bytes((200, 10, 10))
@pytest.fixture
def green_image(): return make_image_bytes((10, 200, 10))
