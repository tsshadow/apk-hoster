"""
Configuration module for APK Hoster.
Handles environment variables and global settings.
"""

import os
import re
import logging
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("apk-hoster")

# Application Configuration
APP_NAME = os.getenv("APP_NAME", "APK Hoster")
PORT = int(os.getenv("PORT", "8275"))
ADMIN_PASSWORD = os.getenv("ADMIN_PASS", "")

# A single non-admin account seeded on startup, for the build pipeline that
# uploads APKs and for the installed app that polls /api/version. Both the name
# and the password come from the environment, so nothing here is tied to one
# particular app.
DEFAULT_USER = os.getenv("DEFAULT_USER", "user")
DEFAULT_USER_PASSWORD = os.getenv("DEFAULT_USER_PASSWORD", "")
ALLOWED_IPS = os.getenv("ALLOWED_IPS", "")

# Push notification for a new APK (ntfy). Empty NTFY_URL turns it off.
NTFY_URL = os.getenv("NTFY_URL", "")
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "apk-hoster")
NTFY_TOKEN = os.getenv("NTFY_TOKEN", "")

# Database Config
DB_TYPE = os.getenv("DB_TYPE", "sqlite").lower()
MYSQL_HOST = os.getenv("MYSQL_HOST", "db")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "apk-hoster")
MYSQL_ROOT_PASSWORD = os.getenv("MYSQL_ROOT_PASSWORD", "")


def get_dist_dir() -> str:
    """
    Get the directory where APKs are stored.
    Priority: /mnt/apks > DIST_DIR env > ./dist
    """
    if os.path.exists("/mnt/apks"):
        return "/mnt/apks"

    dist_dir = os.getenv("DIST_DIR")
    if dist_dir:
        return dist_dir

    return "./dist"


DIST_DIR = get_dist_dir()
if not os.path.exists(DIST_DIR):
    os.makedirs(DIST_DIR, exist_ok=True)

DB_PATH = os.path.join(DIST_DIR, "apk-hoster.db")

# Regex for APK parsing: apkname-v1.2.3-123.apk
APK_REGEX = re.compile(r"^(.+)-v(.+)-(\d+)(?:-unsigned)?(?:-(debug))?\.apk$")


def _parse_apk_aliases(raw: str) -> dict:
    """
    Parse the APK_ALIASES environment variable into an {old: new} mapping.

    Format: "old=new,other=another" (whitespace around the parts is ignored).
    An APK series is identified only by the filename prefix of its uploads, so
    renaming an app's series strands every copy already installed: those keep
    asking /api/version for the old name and are told they are up to date. An
    alias makes the old name resolve to the new series until the last install
    has been replaced by one that asks for the new name itself.
    """
    aliases = {}
    for entry in raw.split(","):
        if "=" not in entry:
            continue
        old, new = entry.split("=", 1)
        old, new = old.strip(), new.strip()
        if old and new:
            aliases[old] = new
    return aliases


APK_ALIASES = _parse_apk_aliases(os.getenv("APK_ALIASES", ""))
