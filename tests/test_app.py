import os
import pytest
from app import hash_password, verify_password, is_hashed, APK_REGEX

def test_password_hashing():
    password = "securepassword123"
    hashed = hash_password(password)
    assert hashed != password
    assert is_hashed(hashed)
    assert verify_password(password, hashed)
    assert not verify_password("wrongpassword", hashed)

def test_apk_regex():
    filenames = [
        ("myapp-v1.0.0-1.apk", ("myapp", "1.0.0", "1", None)),
        ("another-app-v2.1.3-456-debug.apk", ("another-app", "2.1.3", "456", "debug")),
        ("simple-v1-2.apk", ("simple", "1", "2", None)),
    ]
    for filename, expected in filenames:
        match = APK_REGEX.match(filename)
        assert match is not None
        assert match.groups() == expected

def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.text == '"OK"'

def test_unauthorized_access(client):
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["location"] == "/login"

def test_login_success(client, admin_user):
    response = client.post("/login", data={
        "username": admin_user["username"],
        "password": admin_user["password"]
    })
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    # Check if cookie is set
    assert "session" in response.cookies

def test_api_version_unauthorized(client):
    response = client.get("/api/version")
    assert response.status_code == 401
