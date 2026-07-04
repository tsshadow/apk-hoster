#!/bin/bash
set -e

# Configuration
APP_NAME="apk-hoster"
DOCKER_IMAGE="${DOCKER_IMAGE:-tsshadow/apk-hoster}"

cd "$(dirname "$0")/.."
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

# 1. Extract Version Info from build.gradle (for tagging)
# Note: When standalone, this might need to be passed in or fetched differently
VERSION_NAME=$(grep "versionName" ../ultrasonic/build.gradle 2>/dev/null | head -n 1 | sed 's/.*"\(.*\)".*/\1/' || echo "latest")

# Check for docker permissions
if ! docker info >/dev/null 2>&1; then
    if [ -z "$DOCKER_GROUP_RETRY" ] && getent group docker | grep -q "\b$USER\b"; then
        export DOCKER_GROUP_RETRY=1
        echo "Detected 'docker' group membership but it's not active in this session."
        echo "Re-executing with 'sg docker'..."
        CMD=$(printf "%q " "$0" "$@")
        exec sg docker -c "$CMD"
    fi
    echo "ERROR: Permission denied while trying to connect to the Docker daemon."
    exit 1
fi

echo "--- Building Docker Image: $DOCKER_IMAGE ---"
docker build -t "$DOCKER_IMAGE:latest" -t "$DOCKER_IMAGE:$VERSION_NAME" -f apk-hoster/Dockerfile .

echo "--- Pushing Docker Image: $DOCKER_IMAGE ---"
docker push "$DOCKER_IMAGE:latest"
docker push "$DOCKER_IMAGE:$VERSION_NAME"

echo "--- $APP_NAME Docker build and push completed ---"
