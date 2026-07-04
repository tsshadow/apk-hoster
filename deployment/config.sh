#!/bin/bash
# deployment/config.sh - Centralized configuration loader

# Helper function to load environment variables from a file
load_env() {
    local env_file="$1"
    if [ -f "$env_file" ]; then
        echo "Loading config from $env_file"
        # Extract variables, handle quotes, and export them
        while IFS='=' read -r key value; do
            # Skip comments and empty lines
            [[ $key =~ ^# ]] || [[ -z $key ]] && continue

            # Trim whitespace
            key=$(echo "$key" | xargs)
            value=$(echo "$value" | xargs)

            # Export the variable
            export "$key=$value"
        done < "$env_file"
    fi
}

# Determine project root (one level up from this script)
DEPLOY_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
export ROOT_DIR="$( cd "$DEPLOY_DIR/.." && pwd )"

# 1. Load Application Configuration
load_env "$ROOT_DIR/.env"

# 2. Load Deployment-specific Configuration
load_env "$ROOT_DIR/.deploy-env"

# 3. Set Defaults
export APP_NAME="${APP_NAME:-apk-hoster}"
export DOCKER_IMAGE="${DOCKER_IMAGE:-tsshadow/apk-hoster}"
export SERVICE_NAME="${SERVICE_NAME:-apk-hoster}"
export REMOTE_DIST_PATH="${REMOTE_DIST_PATH:-/mnt/teun/ultrasonic-builds}"
export DEPLOY_TARGET_NAME="${DEPLOY_TARGET_NAME:-APK Hoster}"

# 4. Version Info
export VERSION_FILE="$ROOT_DIR/VERSION"
if [ -f "$VERSION_FILE" ]; then
    export VERSION_NAME="${VERSION_NAME:-$(cat "$VERSION_FILE")}"
else
    export VERSION_NAME="${VERSION_NAME:-latest}"
fi

echo "Configuration loaded for $APP_NAME ($VERSION_NAME)"
