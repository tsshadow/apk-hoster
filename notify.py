"""
Push notification when a new APK arrives, through ntfy.

Off unless NTFY_URL is set. A failed push is logged and never fails the
upload or the sync that found the file.
"""

import threading
import urllib.request
from typing import Optional

from config import NTFY_TOKEN, NTFY_TOPIC, NTFY_URL, logger


def build_request(
    apk_name: str, version_name: str, version_code: int, filename: str
) -> Optional[urllib.request.Request]:
    """
    Build the ntfy request for one new APK, or None when ntfy is not configured.
    """
    if not NTFY_URL or not NTFY_TOPIC:
        return None
    url = f"{NTFY_URL.rstrip('/')}/{NTFY_TOPIC}"
    body = f"{filename} is ready to install.".encode("utf-8")
    headers = {
        "Title": f"{apk_name} {version_name} ({version_code})",
        "Tags": "package",
    }
    if NTFY_TOKEN:
        headers["Authorization"] = f"Bearer {NTFY_TOKEN}"
    return urllib.request.Request(url, data=body, headers=headers, method="POST")


def _send(request: urllib.request.Request) -> None:
    """Send one request; log instead of raising."""
    try:
        with urllib.request.urlopen(request, timeout=10):
            pass
    except OSError as e:
        logger.warning("ntfy push failed: %s", e)


def notify_new_apk(
    apk_name: str, version_name: str, version_code: int, filename: str
) -> None:
    """
    Push a message for a new APK on a background thread, so a slow ntfy
    server does not hold up the upload response.
    """
    request = build_request(apk_name, version_name, version_code, filename)
    if request is None:
        return
    threading.Thread(target=_send, args=(request,), daemon=True).start()
