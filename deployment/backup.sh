#!/bin/bash
# deployment/backup.sh - Copy what a rebuild needs and git does not hold.
#
# Usage: ./deployment/backup.sh [TARGET_DIR]
#   TARGET_DIR  default: $BACKUP_DIR from .env, else /mnt/synology/backup/apk-hoster
#
# Writes TARGET_DIR/<timestamp>/ with:
#   apk-hoster.bundle  every branch and tag (git clone apk-hoster.bundle restores it)
#   env                the local .env, which deploy.sh ships to the server
#   apk-hoster.db      users and APK index, when BACKUP_DB names a readable file
# Keeps the newest $BACKUP_KEEP (default 10) and deletes older ones.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

env_value() {
    grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- | xargs || true
}

TARGET_DIR="${1:-${BACKUP_DIR:-$(env_value BACKUP_DIR)}}"
TARGET_DIR="${TARGET_DIR:-/mnt/synology/backup/apk-hoster}"
BACKUP_DB="${BACKUP_DB:-$(env_value BACKUP_DB)}"
KEEP="${BACKUP_KEEP:-10}"

if [ ! -d "$(dirname "$TARGET_DIR")" ]; then
    echo "ERROR: $(dirname "$TARGET_DIR") does not exist. Is the share mounted?"
    exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="$TARGET_DIR/$STAMP"
mkdir -p "$DEST"

git bundle create "$DEST/apk-hoster.bundle" --all
git bundle verify -q "$DEST/apk-hoster.bundle"
echo "Git bundle: $(git rev-parse --short HEAD) on $(git rev-parse --abbrev-ref HEAD)"

if [ -f .env ]; then
    install -m 600 .env "$DEST/env"
    echo ".env: copied"
else
    echo "WARNING: no .env to copy"
fi

if [ -n "$BACKUP_DB" ]; then
    if [ -r "$BACKUP_DB" ]; then
        cp "$BACKUP_DB" "$DEST/apk-hoster.db"
        echo "Database: copied from $BACKUP_DB"
    else
        echo "WARNING: BACKUP_DB=$BACKUP_DB is not readable, skipped"
    fi
fi

# Retention: timestamped folders only, newest first.
find "$TARGET_DIR" -mindepth 1 -maxdepth 1 -type d -name '20??????-??????' | sort -r \
    | tail -n +"$((KEEP + 1))" | while read -r old; do
    rm -rf -- "$old"
    echo "Removed old backup $(basename "$old")"
done

echo "Backup written to $DEST"
