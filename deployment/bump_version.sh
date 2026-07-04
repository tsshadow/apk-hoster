#!/bin/bash
set -e

# Load configuration
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$SCRIPT_DIR/config.sh"

CHANGELOG_FILE="$ROOT_DIR/changelog.md"
RELEASE_NOTES_FILE="$ROOT_DIR/RELEASE_NOTES.md"

if [ ! -f "$VERSION_FILE" ]; then
    echo "0.0.0" > "$VERSION_FILE"
fi

CURRENT_VERSION=$(cat "$VERSION_FILE")

# Function to increment version
increment_version() {
    local version=$1
    local type=$2

    IFS='.' read -r major minor patch <<< "$version"

    case "$type" in
        major)
            major=$((major + 1))
            minor=0
            patch=0
            ;;
        minor)
            minor=$((minor + 1))
            patch=0
            ;;
        patch)
            patch=$((patch + 1))
            ;;
        *)
            echo "Invalid bump type: $type" >&2
            exit 1
            ;;
    esac

    echo "$major.$minor.$patch"
}

BUMP_TYPE=$1
if [ -z "$BUMP_TYPE" ]; then
    BUMP_TYPE="patch"
fi

NEW_VERSION=$(increment_version "$CURRENT_VERSION" "$BUMP_TYPE")
echo "$NEW_VERSION" > "$VERSION_FILE"

echo "Version bumped from $CURRENT_VERSION to $NEW_VERSION"

# Update changelog
DATE=$(date +%Y-%m-%d)
NOTES=""
if [ -f "$RELEASE_NOTES_FILE" ]; then
    NOTES=$(cat "$RELEASE_NOTES_FILE")
else
    NOTES="### Added\n- New release notes system\n- Changelog integration in UI"
fi

{
    echo "## [$NEW_VERSION] - $DATE"
    echo ""
    echo -e "$NOTES"
    echo ""
    echo ""
    [ -f "$CHANGELOG_FILE" ] && cat "$CHANGELOG_FILE"
} > "$ROOT_DIR/temp_changelog" && mv "$ROOT_DIR/temp_changelog" "$CHANGELOG_FILE"

export NEW_VERSION
