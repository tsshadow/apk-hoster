"""
Main FastAPI application for APK Hoster.
Provides web interface and API for APK management.
"""
# pylint: disable=too-many-arguments, too-many-positional-arguments, too-many-locals, too-many-branches
import os
import shutil
import urllib.parse
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from typing import List, Optional, Any, Dict

import humanize
from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException, Depends, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates

from config import (
    APP_NAME, PORT, ALLOWED_IPS, DIST_DIR, logger
)
from utils import hash_password, verify_password
from database import db, init_db, sync_db_with_files

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan events for the FastAPI application.
    Handles startup database initialization and background sync task.
    """
    logger.info("Initializing database and syncing files...")
    init_db()
    sync_db_with_files()

    async def background_sync():
        while True:
            await asyncio.sleep(300) # 5 minutes
            try:
                sync_db_with_files()
            except Exception as e:
                logger.error("Background_sync error: %s", e)

    sync_task = asyncio.create_task(background_sync())
    yield
    logger.info("Shutting down background tasks...")
    sync_task.cancel()

app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

def format_notes(notes: str) -> str:
    """
    Format release notes with simple markdown-like syntax to HTML.
    """
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

templates.env.filters["format_size"] = lambda s: \
    humanize.naturalsize(s, binary=True).replace("i", "")
templates.env.filters["format_date"] = lambda d: \
    d.strftime("%Y-%m-%d %H:%M") if isinstance(d, datetime) else d
templates.env.filters["format_notes"] = format_notes
templates.env.filters["urlencode"] = lambda s: urllib.parse.quote(s, safe='')

def get_changelog() -> str:
    """
    Read the project changelog file.
    """
    changelog_path = os.path.join(os.path.dirname(__file__), "changelog.md")
    if os.path.exists(changelog_path):
        with open(changelog_path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

# Security Helpers
def get_client_ip(request: Request) -> str:
    """
    Get the client IP address, handling proxy headers.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    return request.client.host

def check_ip(request: Request) -> bool:
    """
    Check if the client IP is allowed to perform restricted actions.
    """
    if not ALLOWED_IPS:
        return True
    client_ip = get_client_ip(request)
    allowed = [ip.strip() for ip in ALLOWED_IPS.split(",")]
    return client_ip in allowed

def get_current_user(request: Request,
                     session: Optional[str] = Cookie(None)) -> Optional[Dict[str, Any]]:
    """
    Authenticate the current user via header or session cookie.
    """
    x_password = request.headers.get("X-Upload-Password")

    if x_password:
        users = db.fetchall("SELECT * FROM users")
        for user in users:
            if verify_password(x_password, user['password']):
                return user

    if session:
        users = db.fetchall("SELECT * FROM users")
        for user in users:
            if verify_password(session, user['password']):
                return user

    res = db.fetchone("SELECT COUNT(*) as count FROM users")
    if res and res['count'] == 0:
        return {"username": "anonymous", "permissions": "admin"}

    return None

def is_admin(user: Optional[Dict[str, Any]] = Depends(get_current_user)) -> bool:
    """
    Check if the current user has admin permissions.
    """
    if not user:
        return False
    perms = user.get('permissions', '').split(',')
    return 'admin' in perms

def check_permission(user: Dict[str, Any], permission: str, apk_name: Optional[str] = None) -> bool:
    """
    Check if a user has a specific permission, optionally filtered by APK name.
    """
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
            if not any(apk_name.startswith(f) for f in filters):
                return False

    return True

def require_permission(permission: str):
    """
    Dependency to require a specific permission.
    """
    def dependency(user: Optional[Dict[str, Any]] = Depends(get_current_user)):
        if not user:
            raise HTTPException(status_code=401, detail="Unauthorized")
        if not check_permission(user, permission):
            raise HTTPException(status_code=403, detail=f"Forbidden: Missing permission {permission}")
        return user
    return dependency

@app.get("/", response_class=HTMLResponse)
@app.get("/index.html", response_class=HTMLResponse)
async def index(request: Request, user: Optional[Dict[str, Any]] = Depends(get_current_user)):
    """
    Main index page showing the list of available APKs.
    """
    if not user:
        return RedirectResponse(url="/login")

    if not check_permission(user, 'view'):
        return HTMLResponse("Forbidden: No view permission", status_code=403)

    rows = db.fetchall("SELECT * FROM apks ORDER BY version_code DESC, build_date DESC")
    versions = []
    total_size = 0

    scheme = request.url.scheme
    if request.headers.get("X-Forwarded-Proto"):
        scheme = request.headers.get("X-Forwarded-Proto")
    host = request.headers.get("host", f"localhost:{PORT}")
    base_url = f"{scheme}://{host}"

    for row in rows:
        v = row
        if not check_permission(user, 'view', v['apk_name']):
            continue

        if isinstance(v['build_date'], str):
            try:
                v['build_date'] = datetime.fromisoformat(v['build_date'])
            except ValueError:
                pass
        v['url'] = f"{base_url}/{v['filename']}"
        versions.append(v)
        total_size += v['size']

    perms = user.get('permissions', '').split(',')
    admin_status = 'admin' in perms
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
    """
    Render the login page.
    """
    return templates.TemplateResponse(request=request, name="login.html", context={"app_name": APP_NAME})

@app.post("/login")
async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    """
    Handle login form submission.
    """
    user = db.fetchone("SELECT * FROM users WHERE username = ?", (username,))

    if user and verify_password(password, user['password']):
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(key="session", value=password, path="/")
        return response

    return templates.TemplateResponse(request=request, name="login.html", context={"app_name": APP_NAME, "error": "Invalid username or password"})

@app.get("/admin", response_class=HTMLResponse)
async def admin_get(request: Request, admin: bool = Depends(is_admin)):
    """
    Render the admin dashboard.
    """
    if not admin:
        raise HTTPException(status_code=403, detail="Forbidden")

    users = db.fetchall("SELECT * FROM users")
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={"app_name": APP_NAME, "users": users}
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
    """
    Admin: Add a new user.
    """
    if not admin:
        raise HTTPException(status_code=403, detail="Forbidden")

    perm_str = ",".join(permissions)
    hashed_pw = hash_password(password)
    db.execute("INSERT OR IGNORE INTO users (username, password, permissions, apk_filter) VALUES (?, ?, ?, ?)",
                 (username, hashed_pw, perm_str, apk_filter))
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/delete-user")
async def delete_user(request: Request, username: str = Form(...), admin: bool = Depends(is_admin)):
    """
    Admin: Delete a user.
    """
    if not admin:
        raise HTTPException(status_code=403, detail="Forbidden")

    if username in ["admin", "ultrasonic"]:
        logger.warning("Attempt to delete protected user: %s", username)
        return RedirectResponse(url="/admin", status_code=303)

    db.execute("DELETE FROM users WHERE username = ?", (username,))
    return RedirectResponse(url="/admin", status_code=303)

@app.get("/admin/edit-user", response_class=HTMLResponse)
async def edit_user_get(request: Request, username: str, admin: bool = Depends(is_admin)):
    """
    Admin: Render the edit user page.
    """
    if not admin:
        raise HTTPException(status_code=403, detail="Forbidden")

    user = db.fetchone("SELECT * FROM users WHERE username = ?", (username,))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return templates.TemplateResponse(
        request=request,
        name="edit_user.html",
        context={"app_name": APP_NAME, "user": user}
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
    """
    Admin: Update user information.
    """
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
    """
    Log out the current user by clearing the session cookie.
    """
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(key="session", path="/")
    return response

@app.get("/api/version")
@app.get("/get")
async def get_version(request: Request, apk: str = "ultrasonic", user: Dict[str, Any] = Depends(require_permission("view"))):
    """
    API endpoint to get the latest version info for an APK.
    """
    if not check_permission(user, 'view', apk):
        raise HTTPException(status_code=403, detail=f"Forbidden: No permission for APK {apk}")

    row = db.fetchone("SELECT * FROM apks WHERE apk_name = ? ORDER BY version_code DESC, build_date DESC LIMIT 1", (apk,))
    if not row:
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
        "version_code": v['version_code'],
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
    """
    API endpoint to upload a new APK.
    """
    if not check_ip(request):
        raise HTTPException(status_code=403, detail="Forbidden: IP not allowed")

    effective_password = password or request.headers.get("X-Upload-Password")
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
        with open(os.path.join(DIST_DIR, notes_file), "w", encoding="utf-8") as f:
            f.write(release_notes)

    sync_db_with_files()
    return f"Successfully uploaded {apk.filename}"

@app.post("/api/delete-apk")
async def delete_apk(request: Request, filename: str = Form(...), user: Dict[str, Any] = Depends(require_permission("delete"))):
    """
    API endpoint to delete an APK and its associated metadata.
    """
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
    """
    Health check endpoint.
    """
    return "OK"

@app.get("/{filename}")
async def serve_file(filename: str, user: Dict[str, Any] = Depends(require_permission("download"))):
    """
    Serve an APK file for download, checking permissions.
    """
    if filename in ["apk-hoster.db", "config.py", "app.py", "database.py", "utils.py"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    base_name = os.path.basename(filename)
    row = db.fetchone("SELECT apk_name FROM apks WHERE filename = ?", (base_name,))
    if row and not check_permission(user, 'download', row['apk_name']):
        raise HTTPException(status_code=403, detail="Forbidden: No download permission for this APK")

    file_path = os.path.join(DIST_DIR, base_name)
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="File not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
