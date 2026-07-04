#!/bin/bash
set -e

# Configuration
APP_NAME="apk-hoster"
DOCKER_IMAGE="${DOCKER_IMAGE:-tsshadow/apk-hoster}"

SCRIPT_PATH=$(readlink -f "$0")
cd "$(dirname "$SCRIPT_PATH")/.."
ROOT_DIR=$(pwd)

# Load optional configuration from .env
if [ -f ".env" ]; then
    while IFS='=' read -r key value; do
        if [[ ! $key =~ ^# && -n $key ]]; then
            key=$(echo "$key" | xargs)
            value=$(echo "$value" | xargs)
            if [[ "$key" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
                export "$key=$value"
            fi
        fi
    done < .env
fi

# 1. Get Version Info (for tagging)
# Try to get version from environment, or default to latest
VERSION_NAME="${VERSION_NAME:-latest}"

# Check for docker permissions
if ! docker info >/dev/null 2>&1; then
    if [ -z "$DOCKER_GROUP_RETRY" ] && getent group docker | grep -q "\b$USER\b"; then
        export DOCKER_GROUP_RETRY=1
        echo "Detected 'docker' group membership but it's not active in this session."
        echo "Re-executing with 'sg docker'..."
        CMD=$(printf "%q " "$SCRIPT_PATH" "$@")
        exec sg docker -c "$CMD"
    fi
    echo "ERROR: Permission denied while trying to connect to the Docker daemon."
    exit 1
fi

echo "--- Building Docker Image: $DOCKER_IMAGE ---"
docker build -t "$DOCKER_IMAGE:latest" -t "$DOCKER_IMAGE:$VERSION_NAME" -f Dockerfile .

echo "--- Pushing Docker Image: $DOCKER_IMAGE ---"
docker push "$DOCKER_IMAGE:latest"
docker push "$DOCKER_IMAGE:$VERSION_NAME"

echo "--- $APP_NAME Docker build and push completed ---"
