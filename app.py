import os
import re
import sqlite3
import shutil
import urllib.parse
from datetime import datetime
from typing import List, Optional

import humanize
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException, Depends, Cookie, Header
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
import bcrypt

try:
    import mysql.connector
    from mysql.connector import errorcode
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False

load_dotenv()

import asyncio
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    sync_db_with_files()
    
    # Background sync task
    async def background_sync():
        while True:
            await asyncio.sleep(300) # 5 minutes
            try:
                sync_db_with_files()
            except Exception as e:
                print(f"Background_sync error: {e}")
                
    sync_task = asyncio.create_task(background_sync())
    
    yield
    
    # Shutdown
    sync_task.cancel()

app = FastAPI(lifespan=lifespan)

# Configuration
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

def hash_password(password: str):
    if not password:
        password = ""
    # Bcrypt has a 72-byte limit. Newer versions throw ValueError if exceeded.
    pwd_bytes = password.encode('utf-8')
    if len(pwd_bytes) > 72:
        pwd_bytes = pwd_bytes[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')

def verify_password(password: str, hashed: str):
    try:
        if not password or not hashed:
            return False
        pwd_bytes = password.encode('utf-8')
        if len(pwd_bytes) > 72:
            pwd_bytes = pwd_bytes[:72]
        return bcrypt.checkpw(pwd_bytes, hashed.encode('utf-8'))
    except Exception:
        return False

def is_hashed(password: str):
    if not password:
        return False
    # Support multiple bcrypt variants
    return any(password.startswith(p) for p in ["$2b$", "$2a$", "$2y$"])

def get_dist_dir():
    # Priority 1: Check for /mnt/apks (Docker volume)
    if os.path.exists("/mnt/apks"):
        return "/mnt/apks"
    
    # Priority 2: Environment variable
    dist_dir = os.getenv("DIST_DIR")
    if dist_dir:
        return dist_dir
        
    # Priority 3: Default local dist
    return "./dist"

DIST_DIR = get_dist_dir()
if not os.path.exists(DIST_DIR):
    os.makedirs(DIST_DIR, exist_ok=True)

DB_PATH = os.path.join(DIST_DIR, "apk-hoster.db")

# Regex for APK parsing: apkname-v1.2.3-123.apk
APK_REGEX = re.compile(r'^(.+)-v(.+)-(\d+)(?:-unsigned)?(?:-(debug))?\.apk$')

# Templates
templates = Jinja2Templates(directory="templates")

def format_notes(notes: str) -> str:
    import html
    h = html.escape(notes)
    lines = h.split("\n")
    result = []
    for line in lines:
        if line.startswith("## "):
            result.append(f'<h3 style="margin: 15px 0 10px 0; border-bottom: 1px solid #dddfe2;">{line[3:]}</h3>')
        elif line.startswith("### "):
            result.append(f'<h4 style="margin: 10px 0 5px 0;">{line[4:]}</h4>')
        elif line.startswith("- "):
            result.append(f'<li style="margin-left: 20px;">{line[2:]}</li>')
        else:
            result.append(f'{line}<br>')
    return "".join(result)

templates.env.filters["format_size"] = lambda s: humanize.naturalsize(s, binary=True).replace("i", "")
templates.env.filters["format_date"] = lambda d: d.strftime("%Y-%m-%d %H:%M") if isinstance(d, datetime) else d
templates.env.filters["format_notes"] = format_notes
templates.env.filters["urlencode"] = lambda s: urllib.parse.quote(s, safe='')

def get_changelog():
    changelog_path = os.path.join(os.path.dirname(__file__), "changelog.md")
    if os.path.exists(changelog_path):
        with open(changelog_path, "r") as f:
            return f.read()
    return ""

# Database
class Database:
    def __init__(self):
        self.type = DB_TYPE

    def _get_conn(self, database=None, use_root=False):
        if self.type == "mysql":
            if not MYSQL_AVAILABLE:
                raise ImportError("mysql-connector-python is not installed but DB_TYPE is set to mysql")
            
            user = "root" if use_root else MYSQL_USER
            password = MYSQL_ROOT_PASSWORD if use_root else MYSQL_PASSWORD
            
            config = {
                'host': MYSQL_HOST,
                'port': MYSQL_PORT,
                'user': user,
                'password': password,
                'auth_plugin': 'mysql_native_password'
            }
            if database:
                config['database'] = database
                
            return mysql.connector.connect(**config)
        else:
            conn = sqlite3.connect(DB_PATH, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            return conn

    def ensure_db_exists(self):
        if self.type == "mysql":
            try:
                # Try connecting without database first
                conn = self._get_conn(use_root=bool(MYSQL_ROOT_PASSWORD))
                cursor = conn.cursor()
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}`")
                
                # If we used root, ensure the app user exists and has permissions
                if MYSQL_ROOT_PASSWORD and MYSQL_USER:
                    cursor.execute(f"CREATE USER IF NOT EXISTS '{MYSQL_USER}'@'%' IDENTIFIED BY '{MYSQL_PASSWORD}'")
                    cursor.execute(f"GRANT ALL PRIVILEGES ON `{MYSQL_DATABASE}`.* TO '{MYSQL_USER}'@'%'")
                    cursor.execute("FLUSH PRIVILEGES")
                
                conn.commit()
                cursor.close()
                conn.close()
            except Exception as e:
                print(f"Warning: Could not ensure database exists: {e}", flush=True)

    def execute(self, query, params=()):
        conn = self._get_conn(database=MYSQL_DATABASE if self.type == "mysql" else None)
        try:
            if self.type == "mysql":
                query = query.replace("?", "%s")
                if "INSERT OR IGNORE" in query:
                    query = query.replace("INSERT OR IGNORE", "INSERT IGNORE")
                elif "INSERT OR REPLACE" in query:
                    query = query.replace("INSERT OR REPLACE", "REPLACE")
                
                cursor = conn.cursor(dictionary=True)
                cursor.execute(query, params)
                conn.commit()
                cursor.close()
            else:
                conn.execute(query, params)
                conn.commit()
        finally:
            conn.close()

    def fetchall(self, query, params=()):
        conn = self._get_conn(database=MYSQL_DATABASE if self.type == "mysql" else None)
        try:
            if self.type == "mysql":
                query = query.replace("?", "%s")
                cursor = conn.cursor(dictionary=True)
                cursor.execute(query, params)
                res = cursor.fetchall()
                cursor.close()
                return res
            else:
                return [dict(row) for row in conn.execute(query, params).fetchall()]
        finally:
            conn.close()

    def fetchone(self, query, params=()):
        conn = self._get_conn(database=MYSQL_DATABASE if self.type == "mysql" else None)
        try:
            if self.type == "mysql":
                query = query.replace("?", "%s")
                cursor = conn.cursor(dictionary=True)
                cursor.execute(query, params)
                res = cursor.fetchone()
                cursor.close()
                return res
            else:
                row = conn.execute(query, params).fetchone()
                return dict(row) if row else None
        finally:
            conn.close()

db = Database()

def migrate_sqlite_to_mysql():
    if db.type != "mysql":
        return
    
    try:
        # Check if mysql has users
        res = db.fetchone("SELECT COUNT(*) as count FROM users")
        if res and res['count'] > 0:
            return
    except:
        # Tables might not exist yet, which is fine, init_db will create them
        return
        
    if not os.path.exists(DB_PATH):
        return

    print("Migrating SQLite data to MySQL...", flush=True)
    try:
        sqlite_conn = sqlite3.connect(DB_PATH)
        sqlite_conn.row_factory = sqlite3.Row
        
        # Migrate users
        users = sqlite_conn.execute("SELECT * FROM users").fetchall()
        for u in users:
            db.execute("INSERT OR IGNORE INTO users (username, password, permissions) VALUES (?, ?, ?)",
                       (u['username'], u['password'], u['permissions']))
                    
        # Migrate apks
        apks = sqlite_conn.execute("SELECT * FROM apks").fetchall()
        for a in apks:
            db.execute("INSERT OR IGNORE INTO apks (apk_name, version_name, version_code, filename, size, build_date, release_notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (a['apk_name'], a['version_name'], a['version_code'], a['filename'], a['size'], a['build_date'], a['release_notes'], a['created_at']))
        
        sqlite_conn.close()
        print("Migration completed successfully.", flush=True)
    except Exception as e:
        print(f"Migration failed: {e}", flush=True)

def init_db():
    db.ensure_db_exists()
    
    if db.type == "mysql":
        db.execute('''
            CREATE TABLE IF NOT EXISTS apks (
                id INT AUTO_INCREMENT PRIMARY KEY,
                apk_name VARCHAR(255),
                version_name VARCHAR(50),
                version_code INT,
                filename VARCHAR(255) UNIQUE,
                size BIGINT,
                build_date DATETIME,
                release_notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(255) UNIQUE,
                password VARCHAR(255),
                permissions TEXT,
                apk_filter TEXT
            )
        ''')
    else:
        db.execute('''
            CREATE TABLE IF NOT EXISTS apks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                apk_name TEXT,
                version_name TEXT,
                version_code INTEGER,
                filename TEXT UNIQUE,
                size INTEGER,
                build_date DATETIME,
                release_notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password TEXT,
                permissions TEXT DEFAULT 'view',
                apk_filter TEXT
            )
        ''')
    
    # Run migration if needed
    migrate_sqlite_to_mysql()
    
    # Column migrations
    if db.type == "mysql":
        try:
            # Check if version_code is INT
            res = db.fetchall("SHOW COLUMNS FROM apks LIKE 'version_code'")
            if res and "int" not in res[0]['Type'].lower():
                db.execute("ALTER TABLE apks MODIFY COLUMN version_code INT")
            
            # Check if apk_filter exists in users
            res = db.fetchall("SHOW COLUMNS FROM users LIKE 'apk_filter'")
            if not res:
                db.execute("ALTER TABLE users ADD COLUMN apk_filter TEXT")
        except Exception as e:
            print(f"MySQL migration error: {e}", flush=True)
            
    if db.type == "sqlite":
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("PRAGMA table_info(apks)")
        columns = [row['name'] for row in cursor.fetchall()]
        if 'size' not in columns:
            conn.execute("ALTER TABLE apks ADD COLUMN size INTEGER DEFAULT 0")
        if 'release_notes' not in columns:
            conn.execute("ALTER TABLE apks ADD COLUMN release_notes TEXT")
        if 'build_date' not in columns:
            conn.execute("ALTER TABLE apks ADD COLUMN build_date DATETIME")
            
        cursor = conn.execute("PRAGMA table_info(users)")
        user_columns = [row['name'] for row in cursor.fetchall()]
        if 'permissions' not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN permissions TEXT DEFAULT 'view'")
        if 'apk_filter' not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN apk_filter TEXT")
        conn.commit()
        conn.close()

    # Hash existing passwords
    rows = db.fetchall("SELECT id, password FROM users")
    for row in rows:
        if not is_hashed(row['password']):
            hashed = hash_password(row['password'])
            db.execute("UPDATE users SET password = ? WHERE id = ?", (hashed, row['id']))
        
    # Inject ultrasonic user if it doesn't exist
    if ULTRASONIC_PASSWORD:
        hashed_pw = hash_password(ULTRASONIC_PASSWORD)
        db.execute("INSERT OR IGNORE INTO users (username, password, permissions) VALUES (?, ?, ?)", 
                     ("ultrasonic", hashed_pw, "view,download,upload"))
        # Ensure it has upload permission if it already existed
        db.execute("UPDATE users SET permissions = 'view,download,upload' WHERE username = 'ultrasonic'")
        
    # Inject admin user if it doesn't exist
    if ADMIN_PASSWORD:
        hashed_pw = hash_password(ADMIN_PASSWORD)
        db.execute("INSERT OR IGNORE INTO users (username, password, permissions) VALUES (?, ?, ?)", 
                     ("admin", hashed_pw, "admin"))

def sync_db_with_files():
    files = os.listdir(DIST_DIR)
    for filename in files:
        if not filename.endswith(".apk"):
            continue
        
        # Check if already in DB
        res = db.fetchone("SELECT * FROM apks WHERE filename = ?", (filename,))
        
        match = APK_REGEX.match(filename)
        path = os.path.join(DIST_DIR, filename)
        stat = os.stat(path)
        build_date = datetime.fromtimestamp(stat.st_mtime)
        
        if match:
            apk_name, version_name, version_code_str, suffix = match.groups()
            version_code = int(version_code_str)
            if suffix == "debug":
                apk_name = f"{apk_name}-debug"
        else:
            apk_name = filename.replace(".apk", "")
            version_name = "unknown"
            version_code = 0
            
        notes_file = filename.replace(".apk", ".txt")
        notes_path = os.path.join(DIST_DIR, notes_file)
        release_notes = ""
        if os.path.exists(notes_path):
            with open(notes_path, "r") as f:
                release_notes = f.read()
        
        if res:
            # Update if size is 0 or metadata is unknown or apk_name changed
            if res['size'] == 0 or res['version_name'] == 'unknown' or not res['release_notes'] or res['apk_name'] != apk_name:
                db.execute('''
                    UPDATE apks SET apk_name=?, version_name=?, version_code=?, size=?, build_date=?, release_notes=?
                    WHERE filename=?
                ''', (apk_name, version_name, version_code, stat.st_size, build_date, release_notes, filename))
                print(f"Updated {filename} in DB", flush=True)
            continue
                
        db.execute('''
            INSERT INTO apks (apk_name, version_name, version_code, filename, size, build_date, release_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (apk_name, version_name, version_code, filename, stat.st_size, build_date, release_notes))
        print(f"Synced {filename} to DB", flush=True)

# Security Helpers
def get_client_ip(request: Request):
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    return request.client.host

def check_ip(request: Request):
    if not ALLOWED_IPS:
        return True
    client_ip = get_client_ip(request)
    allowed = [ip.strip() for ip in ALLOWED_IPS.split(",")]
    return client_ip in allowed

def get_current_user(request: Request, session: Optional[str] = Cookie(None)):
    x_password = request.headers.get("X-Upload-Password")
    
    # Try header first (API/Ultrasonic)
    if x_password:
        users = db.fetchall("SELECT * FROM users")
        for user in users:
            if verify_password(x_password, user['password']):
                return user
    
    # Try session cookie
    if session:
        users = db.fetchall("SELECT * FROM users")
        for user in users:
            if verify_password(session, user['password']):
                return user
                
    # If no users exist, allow access (first setup)
    res = db.fetchone("SELECT COUNT(*) as count FROM users")
    if res and res['count'] == 0:
        return {"username": "anonymous", "permissions": "admin"}
        
    return None

def check_auth(user: Optional[dict] = Depends(get_current_user)):
    return user is not None

def is_admin(user: Optional[dict] = Depends(get_current_user)):
    if not user:
        return False
    perms = user.get('permissions', '').split(',')
    return 'admin' in perms

def check_permission(user: dict, permission: str, apk_name: Optional[str] = None):
    if not user:
        return False
    
    perms = user.get('permissions', '').split(',')
    if 'admin' in perms:
        return True
    
    if permission not in perms:
        return False
        
    if apk_name:
        apk_filter = user.get('apk_filter')
        if apk_filter:
            filters = [f.strip() for f in apk_filter.split(',')]
            # Check if apk_name starts with any of the filters
            if not any(apk_name.startswith(f) for f in filters):
                return False
                
    return True

def require_permission(permission: str):
    def dependency(user: Optional[dict] = Depends(get_current_user)):
        if not user:
            raise HTTPException(status_code=401, detail="Unauthorized")
        if not check_permission(user, permission):
            raise HTTPException(status_code=403, detail=f"Forbidden: Missing permission {permission}")
        return user
    return dependency

@app.get("/", response_class=HTMLResponse)
@app.get("/index.html", response_class=HTMLResponse)
async def index(request: Request, user: Optional[dict] = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    
    # Check view permission
    if not check_permission(user, 'view'):
        return HTMLResponse("Forbidden: No view permission", status_code=403)

    rows = db.fetchall("SELECT * FROM apks ORDER BY version_code DESC, build_date DESC")
    versions = []
    total_size = 0
    
    # Resolve absolute base URL for QR codes
    scheme = request.url.scheme
    if request.headers.get("X-Forwarded-Proto"):
        scheme = request.headers.get("X-Forwarded-Proto")
    host = request.headers.get("host", f"localhost:{PORT}")
    base_url = f"{scheme}://{host}"

    for row in rows:
        v = row
        # Apply APK filter
        if not check_permission(user, 'view', v['apk_name']):
            continue
            
        # Convert string date from SQLite to datetime object
        if isinstance(v['build_date'], str):
            try:
                v['build_date'] = datetime.fromisoformat(v['build_date'])
            except:
                pass
        v['url'] = f"{base_url}/{v['filename']}"
        versions.append(v)
        total_size += v['size']
    
    admin_status = 'admin' in user.get('permissions', '').split(',')
    perms = user.get('permissions', '').split(',')
    can_delete = 'admin' in perms or 'delete' in perms
    can_download = 'admin' in perms or 'download' in perms
    
    changelog = get_changelog()
    
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "app_name": APP_NAME,
            "versions": versions,
            "total_size": total_size,
            "is_admin": admin_status,
            "can_delete": can_delete,
            "can_download": can_download,
            "authenticated": True,
            "username": user.get('username'),
            "base_url": base_url,
            "changelog": changelog
        }
    )

@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={"app_name": APP_NAME})

@app.post("/login")
async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    # Check DB Users
    user = db.fetchone("SELECT * FROM users WHERE username = ?", (username,))
    
    if user and verify_password(password, user['password']):
        response = RedirectResponse(url="/", status_code=303)
        # Store password in cookie (for simple session, but we verify it every request)
        response.set_cookie(key="session", value=password, path="/")
        return response
        
    return templates.TemplateResponse(request=request, name="login.html", context={"app_name": APP_NAME, "error": "Invalid username or password"})

@app.get("/admin", response_class=HTMLResponse)
async def admin_get(request: Request, admin: bool = Depends(is_admin)):
    if not admin:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    users = db.fetchall("SELECT * FROM users")
    
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "app_name": APP_NAME,
            "users": users
        }
    )

@app.post("/admin/add-user")
async def add_user(
    request: Request, 
    username: str = Form(...), 
    password: str = Form(...), 
    permissions: List[str] = Form([]),
    apk_filter: Optional[str] = Form(None),
    admin: bool = Depends(is_admin)
):
    if not admin:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    perm_str = ",".join(permissions)
    hashed_pw = hash_password(password)
    
    db.execute("INSERT OR IGNORE INTO users (username, password, permissions, apk_filter) VALUES (?, ?, ?, ?)", 
                 (username, hashed_pw, perm_str, apk_filter))
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/delete-user")
async def delete_user(request: Request, username: str = Form(...), admin: bool = Depends(is_admin)):
    if not admin:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    if username == "ultrasonic":
        # Maybe don't allow deleting the system user? 
        # But user said "all other users will be done via the database", so maybe it's fine.
        pass

    db.execute("DELETE FROM users WHERE username = ?", (username,))
    return RedirectResponse(url="/admin", status_code=303)

@app.get("/admin/edit-user", response_class=HTMLResponse)
async def edit_user_get(request: Request, username: str, admin: bool = Depends(is_admin)):
    if not admin:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    user = db.fetchone("SELECT * FROM users WHERE username = ?", (username,))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return templates.TemplateResponse(
        request=request,
        name="edit_user.html",
        context={
            "app_name": APP_NAME,
            "user": user
        }
    )

@app.post("/admin/edit-user")
async def edit_user_post(
    request: Request, 
    username: str = Form(...), 
    new_username: str = Form(...),
    password: Optional[str] = Form(None), 
    permissions: List[str] = Form([]),
    apk_filter: Optional[str] = Form(None),
    admin: bool = Depends(is_admin)
):
    if not admin:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    perm_str = ",".join(permissions)
    
    if password and password.strip():
        hashed_pw = hash_password(password)
        db.execute(
            "UPDATE users SET username = ?, password = ?, permissions = ?, apk_filter = ? WHERE username = ?", 
            (new_username, hashed_pw, perm_str, apk_filter, username)
        )
    else:
        db.execute(
            "UPDATE users SET username = ?, permissions = ?, apk_filter = ? WHERE username = ?", 
            (new_username, perm_str, apk_filter, username)
        )
        
    return RedirectResponse(url="/admin", status_code=303)

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(key="session", path="/")
    return response

@app.get("/api/version")
@app.get("/get")
async def get_version(request: Request, apk: str = "ultrasonic", user: dict = Depends(require_permission("view"))):
    if not check_permission(user, 'view', apk):
        raise HTTPException(status_code=403, detail=f"Forbidden: No permission for APK {apk}")

    row = db.fetchone("SELECT * FROM apks WHERE apk_name = ? ORDER BY version_code DESC, build_date DESC LIMIT 1", (apk,))
    if not row:
        # fallback to latest any
        row = db.fetchone("SELECT * FROM apks ORDER BY version_code DESC, build_date DESC LIMIT 1")
    
    if not row:
        raise HTTPException(status_code=404, detail="No versions found")
    
    v = row
    scheme = request.url.scheme
    if request.headers.get("X-Forwarded-Proto"):
        scheme = request.headers.get("X-Forwarded-Proto")
    host = request.headers.get("host", f"localhost:{PORT}")
    
    version_info = {
        "apk": v['apk_name'],
        "versionName": v['version_name'],
        "versionCode": v['version_code'],
        "buildDate": v['build_date'].isoformat() if isinstance(v['build_date'], datetime) else v['build_date'],
        "filename": v['filename'],
        "size": v['size'],
        "url": f"{scheme}://{host}/{v['filename']}",
        "version_code": v['version_code'],  # Backward compatibility
        "releaseNotes": v['release_notes']
    }
    return JSONResponse(content=version_info, headers={"Access-Control-Allow-Origin": "*"})

@app.post("/api/add-apk")
async def add_apk(
    request: Request,
    apk: UploadFile = File(...),
    release_notes: Optional[str] = Form(None),
    password: Optional[str] = Form(None)
):
    if not check_ip(request):
        raise HTTPException(status_code=403, detail="Forbidden: IP not allowed")
    
    x_upload_password = request.headers.get("X-Upload-Password")
    effective_password = password or x_upload_password
    
    user = None
    if effective_password:
        users = db.fetchall("SELECT * FROM users")
        for u in users:
            if verify_password(effective_password, u['password']):
                user = u
                break
    
    if not user:
        res = db.fetchone("SELECT COUNT(*) as count FROM users")
        if res and res['count'] == 0:
            user = {"username": "anonymous", "permissions": "admin"}
            
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    perms = user.get('permissions', '').split(',')
    if 'admin' not in perms and 'upload' not in perms:
        raise HTTPException(status_code=403, detail="Forbidden: Missing upload permission")

    if not apk.filename.endswith(".apk"):
        raise HTTPException(status_code=400, detail="Only .apk files are allowed")

    dst_path = os.path.join(DIST_DIR, apk.filename)
    with open(dst_path, "wb") as buffer:
        shutil.copyfileobj(apk.file, buffer)

    if release_notes:
        notes_file = apk.filename.replace(".apk", ".txt")
        with open(os.path.join(DIST_DIR, notes_file), "w") as f:
            f.write(release_notes)

    # Update DB
    match = APK_REGEX.match(apk.filename)
    stat = os.stat(dst_path)
    build_date = datetime.fromtimestamp(stat.st_mtime)
    
    if match:
        apk_name, version_name, version_code_str, suffix = match.groups()
        version_code = int(version_code_str)
        if suffix == "debug":
            apk_name = f"{apk_name}-debug"
    else:
        apk_name = apk.filename.replace(".apk", "")
        version_name = "unknown"
        version_code = 0

    db.execute('''
        INSERT OR REPLACE INTO apks (apk_name, version_name, version_code, filename, size, build_date, release_notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (apk_name, version_name, version_code, apk.filename, stat.st_size, build_date, release_notes or ""))
    
    return f"Successfully uploaded {apk.filename}"

@app.post("/api/delete-apk")
async def delete_apk(request: Request, filename: str = Form(...), user: dict = Depends(require_permission("delete"))):
    base_name = os.path.basename(filename)
    full_path = os.path.join(DIST_DIR, base_name)
    
    db.execute("DELETE FROM apks WHERE filename = ?", (base_name,))
    
    if os.path.exists(full_path):
        os.remove(full_path)
    
    notes_file = base_name.replace(".apk", ".txt")
    notes_path = os.path.join(DIST_DIR, notes_file)
    if os.path.exists(notes_path):
        os.remove(notes_path)
        
    return RedirectResponse(url="/", status_code=303)

@app.get("/health")
async def health():
    return "OK"

# Serve static APK files
@app.get("/{filename}")
async def serve_file(filename: str, user: dict = Depends(require_permission("download"))):
    if filename == "apk-hoster.db":
        raise HTTPException(status_code=403, detail="Forbidden")

    base_name = os.path.basename(filename)
    
    # Check APK filter for download
    row = db.fetchone("SELECT apk_name FROM apks WHERE filename = ?", (base_name,))
    if row:
        if not check_permission(user, 'download', row['apk_name']):
            raise HTTPException(status_code=403, detail="Forbidden: No download permission for this APK")

    file_path = os.path.join(DIST_DIR, base_name)
    
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    
    raise HTTPException(status_code=404, detail="File not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
