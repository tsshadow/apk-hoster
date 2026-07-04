package main

import (
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
	"sort"
	"strings"
	"time"
)

type VersionInfo struct {
	APK          string    `json:"apk"`
	VersionName  string    `json:"versionName"`
	VersionCode  string    `json:"versionCode"`
	BuildDate    time.Time `json:"buildDate"`
	Filename     string    `json:"filename"`
	URL          string    `json:"url"`
	ReleaseNotes string    `json:"releaseNotes,omitempty"`
}

var apkRegex = regexp.MustCompile(`^(.+)-v(.+)-(\d+)(?:-unsigned)?\.apk$`)
var distDir string

func getDistDir() string {
	if distDir != "" {
		return distDir
	}
	d := os.Getenv("DIST_DIR")
	if d == "" {
		return "dist"
	}
	return d
}

func getAllVersions(r *http.Request) ([]VersionInfo, error) {
	files, err := os.ReadDir(getDistDir())
	if err != nil {
		return nil, err
	}

	var versions []VersionInfo
	for _, f := range files {
		if f.IsDir() || !strings.HasSuffix(f.Name(), ".apk") {
			continue
		}

		matches := apkRegex.FindStringSubmatch(f.Name())
		if len(matches) == 4 {
			info, _ := f.Info()
			scheme := "http"
			if r.TLS != nil || r.Header.Get("X-Forwarded-Proto") == "https" {
				scheme = "https"
			}

			// Try to read release notes from accompanying .txt file
			notesFile := strings.TrimSuffix(f.Name(), ".apk") + ".txt"
			notesPath := filepath.Join(getDistDir(), notesFile)
			var releaseNotes string
			if b, err := os.ReadFile(notesPath); err == nil {
				releaseNotes = string(b)
			}

			versions = append(versions, VersionInfo{
				APK:          matches[1],
				VersionName:  matches[2],
				VersionCode:  matches[3],
				BuildDate:    info.ModTime(),
				Filename:     f.Name(),
				URL:          fmt.Sprintf("%s://%s/%s", scheme, r.Host, f.Name()),
				ReleaseNotes: releaseNotes,
			})
		}
	}

	// Sort by BuildDate descending
	sort.Slice(versions, func(i, j int) bool {
		return versions[i].BuildDate.After(versions[j].BuildDate)
	})

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
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; padding: 20px; max-width: 800px; margin: 0 auto; background: #f4f7f9; color: #333; }
        h1 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; margin-bottom: 30px; }
        .apk-list { list-style: none; padding: 0; }
        .apk-item { margin-bottom: 15px; padding: 20px; border-radius: 12px; background: white; box-shadow: 0 4px 6px rgba(0,0,0,0.05); transition: transform 0.2s; border-left: 5px solid #3498db; }
        .apk-item:hover { transform: translateY(-2px); box-shadow: 0 6px 12px rgba(0,0,0,0.1); }
        .apk-link { font-weight: bold; font-size: 1.1em; text-decoration: none; color: #2980b9; display: block; word-break: break-all; }
        .apk-info { color: #7f8c8d; font-size: 0.85em; margin-top: 8px; display: flex; justify-content: space-between; }
        .tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.8em; font-weight: bold; background: #e0e0e0; margin-left: 10px; }
        .tag-latest { background: #27ae60; color: white; }
        .release-notes { margin-top: 10px; font-size: 0.9em; color: #444; }
        .release-notes summary { cursor: pointer; color: #3498db; }
        .release-notes-content { margin-top: 8px; border-top: 1px solid #eee; padding-top: 8px; }
    </style>
</head>
<body>
    <h1>{{.AppName}} Downloads</h1>
    <ul class="apk-list">
        {{range $i, $v := .Versions}}
        <li class="apk-item">
            <a class="apk-link" href="{{$v.Filename}}" download>{{$v.Filename}} {{if eq $i 0}}<span class='tag tag-latest'>LATEST</span>{{end}}</a>
            <div class="apk-info">
                <span>Built: {{$v.BuildDate.Format "2006-01-02 15:04"}}</span>
                <span class="tag">APK</span>
            </div>
            {{if $v.ReleaseNotes}}
            <details class="release-notes">
                <summary>Release Notes</summary>
                <div class="release-notes-content">
                    {{formatNotes $v.ReleaseNotes}}
                </div>
            </details>
            {{end}}
        </li>
        {{end}}
    </ul>
    <footer style="margin-top: 40px; text-align: center; color: #95a5a6; font-size: 0.8em;">
        <p>Served by apk-hoster</p>
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

func serveIndex(w http.ResponseWriter, r *http.Request) {
	versions, err := getAllVersions(r)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	funcMap := template.FuncMap{
		"formatNotes": formatNotes,
	}

	tmpl, err := template.New("index").Funcs(funcMap).Parse(indexTemplate)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	data := struct {
		AppName  string
		Versions []VersionInfo
	}{
		AppName:  "ultrasonic", // Could be configurable
		Versions: versions,
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

	// Health check
	http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("OK"))
	})

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
