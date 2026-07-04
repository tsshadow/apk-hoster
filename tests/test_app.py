"""
Integration tests for the APK Hoster FastAPI application.
"""

from utils import hash_password, verify_password, is_hashed
from config import APK_REGEX


def test_password_hashing():
    """
    Test that passwords are correctly hashed and verified.
    """
    password = "securepassword123"
    hashed = hash_password(password)
    assert hashed != password
    assert is_hashed(hashed)
    assert verify_password(password, hashed)
    assert not verify_password("wrongpassword", hashed)


def test_apk_regex():
    """
    Test that the APK filename regex correctly parses components.
    """
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
    """
    Test the health check endpoint.
    """
    response = client.get("/health")
    assert response.status_code == 200
    assert response.text == '"OK"'


def test_unauthorized_access(client):
    """
    Test that unauthorized access to the index is redirected to login.
    """
    response = client.get("/", follow_redirects=False)
    # FastAPI/Starlette uses 307 for some redirects, or 302/303
    assert response.status_code in [302, 303, 307]


def test_login_success(client, admin_user):
    """
    Test successful login with valid credentials.
    """
    response = client.post(
        "/login",
        data={"username": admin_user["username"], "password": admin_user["password"]},
        follow_redirects=False,
    )
    assert response.status_code == 303
    # Check if cookie is set
    assert "session" in response.cookies


def test_api_version_unauthorized(client):
    """
    Test that the version API requires authorization.
    """
    response = client.get("/api/version")
    assert response.status_code == 401
