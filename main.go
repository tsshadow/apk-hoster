package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"html/template"
	"io"
	"log"
	"mime"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"
	
	"github.com/dustin/go-humanize"
	_ "modernc.org/sqlite"
)

type VersionInfo struct {
	APK          string    `json:"apk"`
	VersionName  string    `json:"versionName"`
	VersionCode  string    `json:"versionCode"`
	BuildDate    time.Time `json:"buildDate"`
	Filename     string    `json:"filename"`
	Size         int64     `json:"size"`
	URL          string    `json:"url"`
	ReleaseNotes string    `json:"releaseNotes,omitempty"`
}

var apkRegex = regexp.MustCompile(`^(.+)-v(.+)-(\d+)(?:-unsigned)?\.apk$`)
var distDir string
var db *sql.DB

func initDB() {
	var err error
	dbPath := filepath.Join(getDistDir(), "apk-hoster.db")
	db, err = sql.Open("sqlite", dbPath)
	if err != nil {
		log.Fatalf("Failed to open database: %v", err)
	}

	query := `
	CREATE TABLE IF NOT EXISTS apks (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		apk_name TEXT,
		version_name TEXT,
		version_code TEXT,
		filename TEXT UNIQUE,
		size INTEGER,
		build_date DATETIME,
		release_notes TEXT,
		created_at DATETIME DEFAULT CURRENT_TIMESTAMP
	);`
	_, err = db.Exec(query)
	if err != nil {
		log.Fatalf("Failed to create table: %v", err)
	}
}

func getAppName() string {
	name := os.Getenv("APP_NAME")
	if name != "" {
		return name
	}
	return "ultrasonic"
}

func calculateTotalSize(versions []VersionInfo) int64 {
	var total int64
	for _, v := range versions {
		total += v.Size
	}
	return total
}

func syncDBWithFiles() {
	files, err := os.ReadDir(getDistDir())
	if err != nil {
		log.Printf("Sync error: %v", err)
		return
	}

	for _, f := range files {
		if f.IsDir() || !strings.HasSuffix(f.Name(), ".apk") {
			continue
		}

		// Check if already in DB
		var count int
		err := db.QueryRow("SELECT COUNT(*) FROM apks WHERE filename = ?", f.Name()).Scan(&count)
		if err == nil && count > 0 {
			continue
		}

		matches := apkRegex.FindStringSubmatch(f.Name())
		info, _ := f.Info()
		var apkName, versionName, versionCode string
		if len(matches) == 4 {
			apkName = matches[1]
			versionName = matches[2]
			versionCode = matches[3]
		} else {
			apkName = strings.TrimSuffix(f.Name(), ".apk")
			versionName = "unknown"
			versionCode = "0"
		}

		notesFile := strings.TrimSuffix(f.Name(), ".apk") + ".txt"
		notesPath := filepath.Join(getDistDir(), notesFile)
		var releaseNotes string
		if b, err := os.ReadFile(notesPath); err == nil {
			releaseNotes = string(b)
		}

		_, err = db.Exec(`INSERT INTO apks (apk_name, version_name, version_code, filename, size, build_date, release_notes) 
			VALUES (?, ?, ?, ?, ?, ?, ?)`,
			apkName, versionName, versionCode, f.Name(), info.Size(), info.ModTime(), releaseNotes)
		if err != nil {
			log.Printf("Failed to insert %s into DB: %v", f.Name(), err)
		} else {
			log.Printf("Synced %s to DB", f.Name())
		}
	}
}

func getAllVersions(r *http.Request) ([]VersionInfo, error) {
	rows, err := db.Query("SELECT apk_name, version_name, version_code, filename, size, build_date, release_notes FROM apks ORDER BY build_date DESC")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var versions []VersionInfo
	scheme := "http"
	if r.TLS != nil || r.Header.Get("X-Forwarded-Proto") == "https" {
		scheme = "https"
	}

	for rows.Next() {
		var v VersionInfo
		err := rows.Scan(&v.APK, &v.VersionName, &v.VersionCode, &v.Filename, &v.Size, &v.BuildDate, &v.ReleaseNotes)
		if err != nil {
			continue
		}
		v.URL = fmt.Sprintf("%s://%s/%s", scheme, r.Host, v.Filename)
		versions = append(versions, v)
	}

	return versions, nil
}

func getLatestVersion(apkName string, r *http.Request) (*VersionInfo, error) {
	versions, err := getAllVersions(r)
	if err != nil {
		return nil, err
	}

	if apkName != "" {
		for _, v := range versions {
			if v.APK == apkName {
				return &v, nil
			}
		}
		return nil, fmt.Errorf("no versions found for %s", apkName)
	}

	if len(versions) == 0 {
		return nil, fmt.Errorf("no versions found")
	}

	return &versions[0], nil
}

func getClientIP(r *http.Request) string {
	ip := r.Header.Get("X-Forwarded-For")
	if ip == "" {
		ip = r.Header.Get("X-Real-IP")
	}
	if ip == "" {
		host, _, err := net.SplitHostPort(r.RemoteAddr)
		if err == nil {
			return host
		}
		return r.RemoteAddr
	}
	ips := strings.Split(ip, ",")
	return strings.TrimSpace(ips[0])
}

func checkIP(r *http.Request) bool {
	allowedIPs := os.Getenv("ALLOWED_IPS")
	if allowedIPs == "" {
		return true
	}

	clientIP := getClientIP(r)
	for _, ip := range strings.Split(allowedIPs, ",") {
		if strings.TrimSpace(ip) == clientIP {
			return true
		}
	}
	return false
}

func checkAuth(r *http.Request) bool {
	password := os.Getenv("UPLOAD_PASSWORD")
	if password == "" {
		return true
	}

	// Check header or form value
	if r.Header.Get("X-Upload-Password") == password {
		return true
	}
	if r.FormValue("password") == password {
		return true
	}
	return false
}

func uploadHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	if !checkIP(r) {
		log.Printf("Blocked upload attempt from unauthorized IP: %s", getClientIP(r))
		http.Error(w, "Forbidden: IP not allowed", http.StatusForbidden)
		return
	}

	if !checkAuth(r) {
		log.Printf("Unauthorized upload attempt from %s", getClientIP(r))
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	// 100MB limit
	err := r.ParseMultipartForm(100 << 20)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	file, header, err := r.FormFile("apk")
	if err != nil {
		http.Error(w, "APK file is required", http.StatusBadRequest)
		return
	}
	defer file.Close()

	if !strings.HasSuffix(header.Filename, ".apk") {
		http.Error(w, "Only .apk files are allowed", http.StatusBadRequest)
		return
	}

	dstPath := filepath.Join(getDistDir(), header.Filename)
	dst, err := os.Create(dstPath)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	defer dst.Close()

	_, err = io.Copy(dst, file)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	notes := r.FormValue("release_notes")
	if notes != "" {
		notesFile := strings.TrimSuffix(header.Filename, ".apk") + ".txt"
		os.WriteFile(filepath.Join(getDistDir(), notesFile), []byte(notes), 0644)
	}

	// Insert into DB
	matches := apkRegex.FindStringSubmatch(header.Filename)
	var apkName, versionName, versionCode string
	if len(matches) == 4 {
		apkName = matches[1]
		versionName = matches[2]
		versionCode = matches[3]
	} else {
		apkName = strings.TrimSuffix(header.Filename, ".apk")
		versionName = "unknown"
		versionCode = "0"
	}

	info, _ := os.Stat(dstPath)
	_, err = db.Exec(`INSERT OR REPLACE INTO apks (apk_name, version_name, version_code, filename, size, build_date, release_notes) 
		VALUES (?, ?, ?, ?, ?, ?, ?)`,
		apkName, versionName, versionCode, header.Filename, info.Size(), info.ModTime(), notes)
	if err != nil {
		log.Printf("Failed to insert %s into DB: %v", header.Filename, err)
	}

	log.Printf("Successfully uploaded %s from %s", header.Filename, getClientIP(r))
	w.WriteHeader(http.StatusCreated)
	fmt.Fprintf(w, "Successfully uploaded %s", header.Filename)
}

const indexTemplate = `
<!DOCTYPE html>
<html>
<head>
    <title>{{.AppName}} Downloads</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; padding: 20px; max-width: 900px; margin: 0 auto; background: #f0f2f5; color: #1c1e21; line-height: 1.5; }
        h1 { color: #1877f2; border-bottom: 2px solid #1877f2; padding-bottom: 10px; margin-bottom: 30px; font-weight: 800; }
        .apk-list { list-style: none; padding: 0; }
        .apk-item { margin-bottom: 20px; padding: 24px; border-radius: 16px; background: white; box-shadow: 0 1px 2px rgba(0,0,0,0.1); transition: all 0.3s cubic-bezier(.25,.8,.25,1); border: 1px solid #dddfe2; position: relative; overflow: hidden; }
        .apk-item:hover { transform: translateY(-4px); box-shadow: 0 10px 20px rgba(0,0,0,0.1); border-color: #1877f2; }
        .apk-link { font-weight: bold; font-size: 1.25em; text-decoration: none; color: #1877f2; display: block; word-break: break-all; margin-right: 120px; }
        .apk-info { color: #65676b; font-size: 0.9em; margin-top: 12px; display: flex; gap: 20px; align-items: center; flex-wrap: wrap; }
        .tag { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 0.75em; font-weight: bold; background: #e4e6eb; color: #4b4f56; text-transform: uppercase; letter-spacing: 0.5px; }
        .tag-latest { background: #31a24c; color: white; }
        .tag-version { background: #e7f3ff; color: #1877f2; }
        .release-notes { margin-top: 15px; background: #f7f8fa; border-radius: 8px; padding: 10px; border: 1px solid #ebedf0; }
        .release-notes summary { cursor: pointer; color: #65676b; font-weight: 600; font-size: 0.9em; outline: none; }
        .release-notes-content { margin-top: 10px; border-top: 1px solid #dddfe2; padding-top: 10px; font-size: 0.95em; }
        .admin-actions { margin-top: 20px; border-top: 1px solid #ebedf0; padding-top: 15px; display: flex; justify-content: flex-end; gap: 10px; }
        .btn { padding: 8px 16px; border-radius: 6px; cursor: pointer; text-decoration: none; font-size: 0.85em; font-weight: 600; transition: background 0.2s; border: none; }
        .btn-delete { background: #fa3e3e; color: white; }
        .btn-delete:hover { background: #d92121; }
        .admin-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
        .btn-login { color: #65676b; text-decoration: none; font-size: 0.85em; font-weight: 500; }
        .btn-login:hover { text-decoration: underline; }
        .qr-code { position: absolute; top: 24px; right: 24px; width: 80px; height: 80px; background: #eee; border-radius: 8px; display: flex; align-items: center; justify-content: center; cursor: pointer; border: 1px solid #dddfe2; }
        .qr-code img { max-width: 100%; height: auto; }
        .qr-code:hover::after { content: "Scan to download"; position: absolute; bottom: -20px; left: 50%; transform: translateX(-50%); font-size: 10px; white-space: nowrap; color: #65676b; }
        .search-box { width: 100%; padding: 12px 16px; border-radius: 8px; border: 1px solid #dddfe2; margin-bottom: 25px; box-sizing: border-box; font-size: 1em; }
        .search-box:focus { outline: none; border-color: #1877f2; box-shadow: 0 0 0 2px #e7f3ff; }
    </style>
</head>
<body>
    <div class="admin-header">
        <a href="/" style="text-decoration: none;"><h1>{{.AppName}}</h1></a>
        {{if .IsAdmin}}
            <a href="/logout" class="btn-login">Logout</a>
        {{else}}
            <a href="/login" class="btn-login">Admin Login</a>
        {{end}}
    </div>

    <input type="text" id="search" class="search-box" placeholder="Search APKs..." onkeyup="filterList()">

    <ul class="apk-list" id="apk-list">
        {{$isAdmin := .IsAdmin}}
        {{range $i, $v := .Versions}}
        <li class="apk-item" data-filename="{{$v.Filename}}">
            <div class="qr-code" onclick="showQR('{{$v.URL}}')">
                <img src="https://api.qrserver.com/v1/create-qr-code/?size=80x80&data={{$v.URL}}" alt="QR Code">
            </div>
            <a class="apk-link" href="{{$v.Filename}}" download>{{$v.Filename}} {{if eq $i 0}}<span class='tag tag-latest'>LATEST</span>{{end}}</a>
            <div class="apk-info">
                <span class="tag tag-version">v{{$v.VersionName}} ({{$v.VersionCode}})</span>
                <span>Size: {{formatSize $v.Size}}</span>
                <span>Built: {{$v.BuildDate.Format "2006-01-02 15:04"}}</span>
            </div>
            {{if $v.ReleaseNotes}}
            <details class="release-notes">
                <summary>Release Notes</summary>
                <div class="release-notes-content">
                    {{formatNotes $v.ReleaseNotes}}
                </div>
            </details>
            {{end}}
            {{if $isAdmin}}
            <div class="admin-actions">
                <form action="/api/delete-apk" method="POST" onsubmit="return confirm('Are you sure you want to delete this APK?')">
                    <input type="hidden" name="filename" value="{{$v.Filename}}">
                    <button type="submit" class="btn btn-delete">Delete</button>
                </form>
            </div>
            {{end}}
        </li>
        {{end}}
    </ul>
    
    <script>
        function filterList() {
            var input = document.getElementById('search');
            var filter = input.value.toLowerCase();
            var list = document.getElementById('apk-list');
            var items = list.getElementsByTagName('li');

            for (var i = 0; i < items.length; i++) {
                var filename = items[i].getAttribute('data-filename').toLowerCase();
                if (filename.indexOf(filter) > -1) {
                    items[i].style.display = "";
                } else {
                    items[i].style.display = "none";
                }
            }
        }

        function showQR(url) {
            // Future: show a modal with a larger QR code
            window.open("https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=" + encodeURIComponent(url), "_blank");
        }
    </script>

    <footer style="margin-top: 40px; text-align: center; color: #65676b; font-size: 0.85em;">
        <p>Served by apk-hoster &bull; Total APKs: {{len .Versions}} &bull; Total Size: {{formatSize .TotalSize}}</p>
    </footer>
</body>
</html>
`

func formatNotes(notes string) template.HTML {
	// Simple formatting similar to publish.sh
	h := template.HTMLEscapeString(notes)
	lines := strings.Split(h, "\n")
	var result strings.Builder
	for _, line := range lines {
		if strings.HasPrefix(line, "### ") {
			result.WriteString("<h4 style=\"margin: 10px 0 5px 0;\">")
			result.WriteString(strings.TrimPrefix(line, "### "))
			result.WriteString("</h4>")
		} else if strings.HasPrefix(line, "- ") {
			result.WriteString("<li style=\"margin-left: 20px;\">")
			result.WriteString(strings.TrimPrefix(line, "- "))
			result.WriteString("</li>")
		} else {
			result.WriteString(line)
			result.WriteString("<br>")
		}
	}
	return template.HTML(result.String())
}

func loginHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodGet {
		w.Header().Set("Content-Type", "text/html")
		fmt.Fprintf(w, `
			<!DOCTYPE html>
			<html>
			<head>
				<title>Admin Login</title>
				<meta name="viewport" content="width=device-width, initial-scale=1">
				<style>
					body { font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #f4f7f9; }
					form { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
					input { display: block; width: 100%%; margin-bottom: 10px; padding: 8px; box-sizing: border-box; }
					input[type="submit"] { background: #3498db; color: white; border: none; cursor: pointer; }
				</style>
			</head>
			<body>
				<form method="POST">
					<h2>Admin Login</h2>
					<input type="password" name="password" placeholder="Password" required autofocus>
					<input type="submit" value="Login">
				</form>
			</body>
			</html>
		`)
		return
	}

	password := os.Getenv("UPLOAD_PASSWORD")
	if password != "" && r.FormValue("password") == password {
		http.SetCookie(w, &http.Cookie{
			Name:  "session",
			Value: password,
			Path:  "/",
		})
		http.Redirect(w, r, "/", http.StatusFound)
	} else {
		http.Error(w, "Invalid password", http.StatusUnauthorized)
	}
}

func logoutHandler(w http.ResponseWriter, r *http.Request) {
	http.SetCookie(w, &http.Cookie{
		Name:   "session",
		Value:  "",
		Path:   "/",
		MaxAge: -1,
	})
	http.Redirect(w, r, "/", http.StatusFound)
}

func isAdmin(r *http.Request) bool {
	cookie, err := r.Cookie("session")
	if err != nil {
		return false
	}
	password := os.Getenv("UPLOAD_PASSWORD")
	return password != "" && cookie.Value == password
}

func deleteHandler(w http.ResponseWriter, r *http.Request) {
	if !isAdmin(r) {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	var filename string
	if r.Method == http.MethodPost {
		filename = r.FormValue("filename")
	} else {
		filename = r.URL.Query().Get("filename")
	}
	
	if filename == "" {
		http.Error(w, "Filename required", http.StatusBadRequest)
		return
	}

	// Safety check: only allow files from distDir
	baseName := filepath.Base(filename)
	fullPath := filepath.Join(getDistDir(), baseName)

	// Delete from DB
	_, err := db.Exec("DELETE FROM apks WHERE filename = ?", baseName)
	if err != nil {
		log.Printf("DB Delete error: %v", err)
	}

	// Delete from FS
	os.Remove(fullPath)
	os.Remove(strings.TrimSuffix(fullPath, ".apk") + ".txt")

	log.Printf("Deleted %s (requested by admin from %s)", baseName, getClientIP(r))
	http.Redirect(w, r, "/", http.StatusFound)
}

func serveIndex(w http.ResponseWriter, r *http.Request) {
	versions, err := getAllVersions(r)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	funcMap := template.FuncMap{
		"formatNotes": formatNotes,
		"formatSize": func(s int64) string {
			return humanize.Bytes(uint64(s))
		},
	}

	tmpl, err := template.New("index").Funcs(funcMap).Parse(indexTemplate)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	data := struct {
		AppName   string
		Versions  []VersionInfo
		TotalSize int64
		IsAdmin   bool
	}{
		AppName:   getAppName(),
		Versions:  versions,
		TotalSize: calculateTotalSize(versions),
		IsAdmin:   isAdmin(r),
	}

	w.Header().Set("Content-Type", "text/html")
	tmpl.Execute(w, data)
}

func main() {
	// Register APK mime type to prevent browsers from downloading it as ZIP
	mime.AddExtensionType(".apk", "application/vnd.android.package-archive")

	distDir = getDistDir()
	if _, err := os.Stat(distDir); os.IsNotExist(err) {
		fmt.Printf("Warning: %s directory does not exist, creating it.\n", distDir)
		os.MkdirAll(distDir, 0755)
	}

	initDB()
	syncDBWithFiles()

	// Background sync every 5 minutes
	go func() {
		ticker := time.NewTicker(5 * time.Minute)
		for range ticker.C {
			syncDBWithFiles()
		}
	}()

	// Health check
	http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("OK"))
	})

	// Auth and Admin
	http.HandleFunc("/login", loginHandler)
	http.HandleFunc("/logout", logoutHandler)
	http.HandleFunc("/api/delete-apk", deleteHandler)

	// Version API
	versionHandler := func(w http.ResponseWriter, r *http.Request) {
		apkName := r.URL.Query().Get("apk")
		if apkName == "" {
			apkName = "ultrasonic" // Default
		}
		version, err := getLatestVersion(apkName, r)
		if err != nil {
			http.Error(w, err.Error(), http.StatusNotFound)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Access-Control-Allow-Origin", "*")
		json.NewEncoder(w).Encode(version)
	}

	http.HandleFunc("/api/version", versionHandler)
	http.HandleFunc("/get", versionHandler)
	http.HandleFunc("/api/add-apk", uploadHandler)

	// Static files (APKs)
	fs := http.FileServer(http.Dir(distDir))
	
	// Wrapped handler to add logging and handle index
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		log.Printf("%s %s %s", getClientIP(r), r.Method, r.URL.Path)
		
		// If requesting root or index.html, serve dynamic index
		if r.URL.Path == "/" || r.URL.Path == "/index.html" {
			serveIndex(w, r)
			return
		}
		
		fs.ServeHTTP(w, r)
	})
	
	http.Handle("/", handler)

	port := os.Getenv("PORT")
	if port == "" {
		port = "8275" // Nice port referencing APK (275 on phone keypad)
	}

	fmt.Printf("Starting apk-hoster on port %s...\n", port)
	log.Fatal(http.ListenAndServe(":"+port, nil))
}
