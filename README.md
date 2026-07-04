# APK Hoster

![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

A professional, self-hosted service for hosting and managing APK files. Featuring a dynamic web interface, an automated release system, and a secure upload API.

## 🚀 Features

-   **Dynamic Web Interface**: Automatically generated index page with a modern, responsive design.
-   **Tabbed Navigation**: Separate views for APK listings and Project Changelog.
-   **Automated Release Management**: Use the `./bup` tool for seamless version bumping, tagging, and deployment.
-   **Secure Upload API**: Integrated endpoint for programmatic uploads with password protection and IP whitelisting.
-   **Release Notes Support**: Display rich HTML release notes extracted from companion `.txt` files or Markdown.
-   **QR Code Integration**: Instantly download APKs to mobile devices by scanning generated QR codes.
-   **Multi-Database Support**: Flexible storage options using either SQLite (local) or MySQL (remote/Docker).
-   **Background Synchronization**: Automatically keeps the database in sync with the filesystem.
-   **Admin Dashboard**: Manage users, permissions, and APKs through a secure web-based interface.
-   **Granular Permissions**: Define view, download, upload, and delete permissions per user.
-   **APK Filtering**: Restrict user access to specific APK name prefixes.

## 🛠️ Quick Start

### Using Docker (Recommended)

1.  **Configure Environment**:
    ```bash
    cp .env.example .env
    # Edit .env with your desired configurations
    ```

2.  **Deploy**:
    ```bash
    ./bup patch  # Bumps version, builds image, and deploys
    ```

### Standalone Installation

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Run the Application**:
    ```bash
    python app.py
    ```

## ⚙️ Configuration

The application is configured via environment variables in the `.env` file:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `APP_NAME` | `ultrasonic` | The display name of your application. |
| `PORT` | `8275` | The port the service will listen on. |
| `DIST_DIR` | `./dist` | Directory where APK files are stored. |
| `ADMIN_PASS` | (empty) | Admin password for first-time setup. |
| `ALLOWED_IPS` | (empty) | Comma-separated list of IPs allowed for uploads. |
| `DB_TYPE` | `sqlite` | Database type: `sqlite` or `mysql`. |

*For full configuration options, see `.env.example`.*

## 📖 API Documentation

### Get Latest Version
`GET /api/version?apk=<name>`

**Response**:
```json
{
  "apk": "myapp",
  "versionName": "1.0.3",
  "versionCode": 3,
  "buildDate": "2023-10-27T10:00:00",
  "filename": "myapp-v1.0.3-3.apk",
  "size": 15728640,
  "url": "https://host.com/myapp-v1.0.3-3.apk",
  "releaseNotes": "Bug fixes and improvements"
}
```

### Upload APK
`POST /api/add-apk`

**Fields**:
- `apk`: The `.apk` file (Multipart).
- `release_notes`: (Optional) Plain text or basic Markdown.
- `password`: (Optional) Authorization password.

**Headers**:
- `X-Upload-Password`: Alternative to the `password` field.

## 🧪 Development and Quality

We strive for high code quality and maintainability.

### Running Tests
```bash
pip install -r requirements-dev.txt
pytest
```

### Code Style
The project follows PEP 8 standards and uses `pylint` for static analysis. Detailed docstrings and type hints are required for all new contributions.

## 📄 License

This project is licensed under the MIT License. See the `LICENSE` file for details.
