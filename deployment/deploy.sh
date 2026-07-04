#!/bin/bash
set -e

# Load configuration
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$SCRIPT_DIR/config.sh"

cd "$ROOT_DIR"

if [ -n "$REMOTE_HOST" ]; then
    echo "--- Starting remote deployment for stack: $DEPLOY_TARGET_NAME ---"

    # Create temporary .env from our .env for deployment
    TEMP_ENV=$(mktemp)
    echo "DOCKER_IMAGE=${DOCKER_IMAGE}" > "$TEMP_ENV"
    echo "REMOTE_DIST_PATH=${REMOTE_DIST_PATH}" >> "$TEMP_ENV"

    if [ -f ".env" ]; then
        grep -v '^#' .env | sed 's/ *= */=/g' >> "$TEMP_ENV"
    fi
    export LOCAL_ENV_FILE="$TEMP_ENV"
    export LOCAL_COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"
    export SERVICE_NAME="$SERVICE_NAME"

    # Use the generalized deployment script
    "$SCRIPT_DIR/deploy-stack.sh"

    rm -f "$TEMP_ENV"
    echo "--- $APP_NAME Deployment completed successfully ---"
else
    echo "Note: REMOTE_HOST not set, skipping remote deployment for $APP_NAME."
    exit 1
fi
