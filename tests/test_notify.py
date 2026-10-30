"""
Tests for the ntfy push on a new APK.
"""

import database
import notify
from database import db, sync_db_with_files


def test_no_request_without_url(monkeypatch):
    """Without NTFY_URL nothing is sent."""
    monkeypatch.setattr(notify, "NTFY_URL", "")
    assert notify.build_request("muma-mobile", "7.18.5", 370, "x.apk") is None


def test_request_names_the_version(monkeypatch):
    """The push goes to the topic and names the series and version."""
    monkeypatch.setattr(notify, "NTFY_URL", "https://ntfy.example.com/")
    monkeypatch.setattr(notify, "NTFY_TOPIC", "apk-hoster")
    monkeypatch.setattr(notify, "NTFY_TOKEN", "")
    request = notify.build_request(
        "muma-mobile", "7.18.5", 370, "muma-mobile-v7.18.5-370.apk"
    )
    assert request.full_url == "https://ntfy.example.com/apk-hoster"
    assert request.get_method() == "POST"
    assert request.get_header("Title") == "muma-mobile 7.18.5 (370)"
    assert b"muma-mobile-v7.18.5-370.apk" in request.data
    assert request.get_header("Authorization") is None


def test_token_is_sent_as_bearer(monkeypatch):
    """A configured token travels as a bearer header."""
    monkeypatch.setattr(notify, "NTFY_URL", "https://ntfy.example.com")
    monkeypatch.setattr(notify, "NTFY_TOKEN", "tk_test")
    request = notify.build_request("a", "1.0", 1, "a-v1.0-1.apk")
    assert request.get_header("Authorization") == "Bearer tk_test"


def _sync_into(tmp_path, monkeypatch):
    """Run a sync over tmp_path and return the APKs it announced."""
    sent = []
    monkeypatch.setattr(database, "DIST_DIR", str(tmp_path))
    monkeypatch.setattr(database, "notify_new_apk", lambda *args: sent.append(args))
    sync_db_with_files()
    return sent


def test_new_apk_is_announced(tmp_path, monkeypatch):
    """An APK that appears after the first sync is pushed once."""
    db.execute("DELETE FROM apks")
    (tmp_path / "app-v1.0-1.apk").write_bytes(b"x")
    assert not _sync_into(tmp_path, monkeypatch)

    (tmp_path / "app-v1.1-2.apk").write_bytes(b"y")
    assert _sync_into(tmp_path, monkeypatch) == [("app", "1.1", 2, "app-v1.1-2.apk")]

    # Seen once, never again.
    assert not _sync_into(tmp_path, monkeypatch)
    db.execute("DELETE FROM apks")


def test_first_start_announces_nothing(tmp_path, monkeypatch):
    """An empty database finding files on disk pushes nothing."""
    db.execute("DELETE FROM apks")
    for code in (1, 2, 3):
        (tmp_path / f"app-v1.{code}-{code}.apk").write_bytes(b"x")
    assert not _sync_into(tmp_path, monkeypatch)
    db.execute("DELETE FROM apks")
