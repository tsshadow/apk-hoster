# APK Hoster

A simple Go-based service to host APK files with dynamic index generation and an upload API.

## Features
- Dynamic index page listing all APKs in the `dist` directory.
- Release notes support (via accompanying `.txt` files).
- Secure upload API (`/api/add-apk`).
- IP whitelisting and password protection for uploads.
- Automatic APK mime-type handling.

## Setup

1.  **Configure Environment**:
    Copy `.env.example` to `.env` and fill in the values:
    ```bash
    cp .env.example .env
    ```

2.  **Build and Run (Docker)**:
    ```bash
    ./scripts/build.sh
    docker-compose up -d
    ```

3.  **Standalone Build**:
    ```bash
    go build -o apk-hoster main.go
    ./apk-hoster
    ```

## API

### `GET /api/version?apk=ultrasonic`
Returns JSON with the latest version information.

### `POST /api/add-apk`
Upload a new APK.
- **Fields**:
  - `apk`: The APK file.
  - `release_notes`: (Optional) Text for release notes.
  - `password`: (Optional) Upload password (if `UPLOAD_PASSWORD` is set).
- **Headers**:
  - `X-Upload-Password`: (Optional) Alternative to `password` field.

## Security
- `UPLOAD_PASSWORD`: If set, all uploads must provide this password.
- `ALLOWED_IPS`: Comma-separated list of IPs allowed to upload.
