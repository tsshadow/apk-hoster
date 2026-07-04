import os
import sqlite3
from datetime import datetime
from typing import List, Optional, Any, Dict
from config import (
    DB_TYPE, MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, 
    MYSQL_DATABASE, MYSQL_ROOT_PASSWORD, DB_PATH, DIST_DIR, APK_REGEX, 
    ADMIN_PASSWORD, ULTRASONIC_PASSWORD, logger
)
from utils import hash_password

try:
    import mysql.connector
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False

class Database:
    """
    Unified database interface for SQLite and MySQL.
    """
    def __init__(self):
        self.type = DB_TYPE

    def _get_conn(self, database: Optional[str] = None, use_root: bool = False):
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
                conn = self._get_conn(use_root=bool(MYSQL_ROOT_PASSWORD))
                cursor = conn.cursor()
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}`")
                
                if MYSQL_ROOT_PASSWORD and MYSQL_USER:
                    cursor.execute(f"CREATE USER IF NOT EXISTS '{MYSQL_USER}'@'%' IDENTIFIED BY '{MYSQL_PASSWORD}'")
                    cursor.execute(f"GRANT ALL PRIVILEGES ON `{MYSQL_DATABASE}`.* TO '{MYSQL_USER}'@'%'")
                    cursor.execute("FLUSH PRIVILEGES")
                
                conn.commit()
                cursor.close()
                conn.close()
            except Exception as e:
                logger.warning(f"Could not ensure database exists: {e}")

    def execute(self, query: str, params: tuple = ()):
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

    def fetchall(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        conn = self._get_conn(database=MYSQL_DATABASE if self.type == "mysql" else None)
        try:
            if self.type == "mysql":
                query = query.replace("?", "%s")
                cursor = conn.cursor(dictionary=True)
                cursor.execute(query, params)
                res = cursor.fetchall()
                cursor.close()
                return res or []
            else:
                return [dict(row) for row in conn.execute(query, params).fetchall()]
        finally:
            conn.close()

    def fetchone(self, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
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
        res = db.fetchone("SELECT COUNT(*) as count FROM users")
        if res and res['count'] > 0:
            return
    except Exception:
        return
        
    if not os.path.exists(DB_PATH):
        return

    logger.info("Migrating SQLite data to MySQL...")
    try:
        sqlite_conn = sqlite3.connect(DB_PATH)
        sqlite_conn.row_factory = sqlite3.Row
        
        users = sqlite_conn.execute("SELECT * FROM users").fetchall()
        for u in users:
            db.execute("INSERT OR IGNORE INTO users (username, password, permissions) VALUES (?, ?, ?)",
                       (u['username'], u['password'], u['permissions']))
                    
        apks = sqlite_conn.execute("SELECT * FROM apks").fetchall()
        for a in apks:
            db.execute("INSERT OR IGNORE INTO apks (apk_name, version_name, version_code, filename, size, build_date, release_notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (a['apk_name'], a['version_name'], a['version_code'], a['filename'], a['size'], a['build_date'], a['release_notes'], a['created_at']))
        
        sqlite_conn.close()
        logger.info("Migration completed successfully.")
    except Exception as e:
        logger.error(f"Migration failed: {e}")

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
    
    migrate_sqlite_to_mysql()
    
    if db.type == "mysql":
        try:
            res = db.fetchall("SHOW COLUMNS FROM apks LIKE 'version_code'")
            if res and "int" not in res[0]['Type'].lower():
                db.execute("ALTER TABLE apks MODIFY COLUMN version_code INT")
            
            res = db.fetchall("SHOW COLUMNS FROM users LIKE 'apk_filter'")
            if not res:
                db.execute("ALTER TABLE users ADD COLUMN apk_filter TEXT")
        except Exception as e:
            logger.error(f"MySQL migration error: {e}")
            
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

    if ULTRASONIC_PASSWORD:
        hashed_pw = hash_password(ULTRASONIC_PASSWORD)
        db.execute("INSERT OR IGNORE INTO users (username, password, permissions) VALUES (?, ?, ?)", 
                     ("ultrasonic", hashed_pw, "view,download,upload"))
        db.execute("UPDATE users SET permissions = 'view,download,upload' WHERE username = 'ultrasonic'")
        
    if ADMIN_PASSWORD:
        hashed_pw = hash_password(ADMIN_PASSWORD)
        db.execute("INSERT OR IGNORE INTO users (username, password, permissions) VALUES (?, ?, ?)", 
                     ("admin", hashed_pw, "admin"))

def sync_db_with_files():
    files = os.listdir(DIST_DIR)
    for filename in files:
        if not filename.endswith(".apk"):
            continue
        
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
            with open(notes_path, "r", encoding="utf-8") as f:
                release_notes = f.read()
        
        if res:
            if res['size'] == 0 or res['version_name'] == 'unknown' or not res['release_notes'] or res['apk_name'] != apk_name:
                db.execute('''
                    UPDATE apks SET apk_name=?, version_name=?, version_code=?, size=?, build_date=?, release_notes=?
                    WHERE filename=?
                ''', (apk_name, version_name, version_code, stat.st_size, build_date, release_notes, filename))
                logger.info(f"Updated {filename} in DB")
            continue
                
        db.execute('''
            INSERT INTO apks (apk_name, version_name, version_code, filename, size, build_date, release_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (apk_name, version_name, version_code, filename, stat.st_size, build_date, release_notes))
        logger.info(f"Synced {filename} to DB")
