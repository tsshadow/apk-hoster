"""
Test configuration and fixtures for APK Hoster.
"""

import os
import pytest
from fastapi.testclient import TestClient
from app import app, init_db
from database import db


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """
    Sets up a temporary SQLite database for the duration of the test session.
    Overrides the production database path.
    """
    # Use a separate test database
    test_db_path = "test-apk-hoster.db"
    # Override global DB_PATH for tests
    import config
    import database

    original_db_path = config.DB_PATH
    config.DB_PATH = test_db_path
    database.DB_PATH = test_db_path
    db.type = "sqlite"  # Force sqlite for tests

    # Initialize the test database
    init_db()

    yield

    # Cleanup
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    config.DB_PATH = original_db_path


@pytest.fixture
def client():
    """
    Fixture that provides a TestClient for the FastAPI app.
    """
    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin_user():
    """
    Fixture that ensures an admin user exists and returns its credentials.
    """
    # Ensure admin user exists in test DB
    from utils import hash_password

    db.execute(
        "INSERT OR IGNORE INTO users (username, password, permissions) VALUES (?, ?, ?)",
        ("testadmin", hash_password("adminpass"), "admin"),
    )
    return {"username": "testadmin", "password": "adminpass"}
