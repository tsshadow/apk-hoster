import os
import pytest
import sqlite3
from fastapi.testclient import TestClient
from app import app, db, DB_PATH, init_db

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    # Use a separate test database
    test_db_path = "test-apk-hoster.db"
    # Override global DB_PATH for tests
    import app as app_module
    original_db_path = app_module.DB_PATH
    app_module.DB_PATH = test_db_path
    app_module.db.type = "sqlite" # Force sqlite for tests
    
    # Initialize the test database
    init_db()
    
    yield
    
    # Cleanup
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    app_module.DB_PATH = original_db_path

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture
def admin_user():
    # Ensure admin user exists in test DB
    from app import hash_password
    db.execute("INSERT OR IGNORE INTO users (username, password, permissions) VALUES (?, ?, ?)",
               ("testadmin", hash_password("adminpass"), "admin"))
    return {"username": "testadmin", "password": "adminpass"}
