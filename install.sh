#!/bin/bash
set -e

# MuMaFi APK Hoster Install Script
# Standardized interface for building, publishing, and deploying.

# Get the project root
ROOT_DIR="$(dirname "$(readlink -f "$0")")"
cd "$ROOT_DIR"

# Application-specific configuration
PROJECT_NAME="APK Hoster"
AVAILABLE_APPS=("apk-hoster")
DEFAULT_APP="apk-hoster"

show_help() {
    echo "MuMaFi $PROJECT_NAME Install Script"
    echo "Usage: ./install.sh [options]"
    echo ""
    echo "Options:"
    echo "  --help          Show this help message"
    echo "  --app=<app>     Specify the application to install (default: $DEFAULT_APP)"
    echo "  --list          List available applications"
    echo ""
    echo "Examples:"
    echo "  ./install.sh"
}

list_apps() {
    for app in "${AVAILABLE_APPS[@]}"; do
        echo "$app"
    done
}

# Parse arguments
for i in "$@"; do
    case $i in
        --help)
            show_help
            exit 0
            ;;
        --list)
            list_apps
            exit 0
            ;;
    esac
done

./deployment/build_and_deploy.sh "$@"
