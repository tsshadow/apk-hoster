#!/bin/bash
set -e

# Configuration
APP_NAME="apk-hoster"

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

TARGET="${DEPLOY_TARGET_NAME:-APK Hoster}"
DOCKER_IMAGE="${DOCKER_IMAGE:-tsshadow/apk-hoster}"
REMOTE_DIST_PATH="${REMOTE_DIST_PATH:-/mnt/teun/ultrasonic-builds}"

if [ -n "$REMOTE_HOST" ]; then
    echo "--- Starting remote deployment for stack: $TARGET ---"
    
    # Create temporary .env from our .env for deployment
    TEMP_ENV=$(mktemp)
    echo "DOCKER_IMAGE=${DOCKER_IMAGE}" > "$TEMP_ENV"
    echo "REMOTE_DIST_PATH=${REMOTE_DIST_PATH}" >> "$TEMP_ENV"
    
    if [ -f ".env" ]; then
        grep -v '^#' .env | sed 's/ *= */=/g' >> "$TEMP_ENV"
    fi
    export LOCAL_ENV_FILE="$TEMP_ENV"
    
    # Use the generalized deployment script
    # Note: When standalone, ensure deploy-stack.sh is available or use a local version
    DEPLOY_STACK_SCRIPT="../scripts/deploy-stack.sh"
    [ ! -f "$DEPLOY_STACK_SCRIPT" ] && DEPLOY_STACK_SCRIPT="./scripts/deploy-stack.sh"
    
    "$DEPLOY_STACK_SCRIPT"
    
    rm -f "$TEMP_ENV"
    echo "--- $APP_NAME Deployment completed successfully ---"
else
    echo "Note: REMOTE_HOST not set, skipping remote deployment for $APP_NAME."
    exit 1
fi
