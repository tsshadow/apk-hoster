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
APP_NAME = os.getenv("APP_NAME", "ultrasonic")
PORT = int(os.getenv("PORT", 8275))
ADMIN_PASSWORD = os.getenv("ADMIN_PASS", "")
ULTRASONIC_PASSWORD = os.getenv("ULTRASONIC_PASSWORD", "")
ALLOWED_IPS = os.getenv("ALLOWED_IPS", "")

# Database Config
DB_TYPE = os.getenv("DB_TYPE", "sqlite").lower()
MYSQL_HOST = os.getenv("MYSQL_HOST", "db")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
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
APK_REGEX = re.compile(r'^(.+)-v(.+)-(\d+)(?:-unsigned)?(?:-(debug))?\.apk$')
