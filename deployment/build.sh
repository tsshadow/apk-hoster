#!/bin/bash
set -e

# Load configuration
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$SCRIPT_DIR/config.sh"

cd "$ROOT_DIR"

# Check for docker permissions
if ! docker info >/dev/null 2>&1; then
    if [ -z "$DOCKER_GROUP_RETRY" ] && getent group docker | grep -q "\b$USER\b"; then
        export DOCKER_GROUP_RETRY=1
        echo "Detected 'docker' group membership but it's not active in this session."
        echo "Re-executing with 'sg docker'..."
        CMD=$(printf "%q " "$(readlink -f "$0")" "$@")
        exec sg docker -c "$CMD"
    fi
    echo "ERROR: Permission denied while trying to connect to the Docker daemon."
    exit 1
fi

echo "--- Building Docker Image: $DOCKER_IMAGE ---"
docker build -t "$DOCKER_IMAGE:latest" -t "$DOCKER_IMAGE:$VERSION_NAME" -f Dockerfile .

echo "--- $APP_NAME Docker build completed ---"
