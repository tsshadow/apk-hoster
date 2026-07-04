#!/bin/bash
set -e

# Change to the directory where the script is located
cd "$(dirname "$0")"

# Check for docker permissions
if ! docker info >/dev/null 2>&1; then
    if [ -z "$DOCKER_GROUP_RETRY" ] && getent group docker | grep -q "\b$USER\b"; then
        export DOCKER_GROUP_RETRY=1
        echo "Detected 'docker' group membership but it's not active in this session."
        echo "Re-executing with 'sg docker'..."
        CMD=$(printf "%q " "$(readlink -f "$0")" "$@")
        exec sg docker -c "$CMD"
    fi
fi

echo "--- Starting Build and Publish ---"

# 0. Version Bump (if argument provided)
if [ "$1" == "major" ] || [ "$1" == "minor" ] || [ "$1" == "patch" ]; then
    source ./bump_version.sh "$1"
    VERSION_NAME="v$NEW_VERSION"
    
    cd ..
    git add .
    git commit -m "chore: release $VERSION_NAME"
    git tag -a "$VERSION_NAME" -m "Release $VERSION_NAME"
    git push origin main --tags || echo "Warning: git push failed, continuing..."
    cd scripts
else
    VERSION_NAME="latest"
fi

# Run build script (which also pushes the image)
VERSION_NAME=$VERSION_NAME ./build.sh

# Run deploy script
./deploy.sh

echo "--- Build and Publish completed successfully ---"
