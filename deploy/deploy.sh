#!/bin/bash
# Deploy script for general-chatbot-api on server.
#
# Usage:
#   ./deploy.sh <env>                          # build & deploy using version from <env>/VERSION
#   ./deploy.sh <env> -v 1.2.3                 # build & deploy with explicit version
#   ./deploy.sh <env> [-v X] --no-cache        # force rebuild without docker layer cache
#   ./deploy.sh <env> rollback                 # rollback to previous image
#   ./deploy.sh <env> use <tag>                # switch to an existing image tag (no rebuild)
#   ./deploy.sh <env> down                     # stop & remove containers (no volume removal)
#   ./deploy.sh <env> down -v                  # stop, remove containers AND named volumes
#   ./deploy.sh <env> list                     # list all local image tags
#
# <env> is the environment subfolder under deploy/ (dev, stag, prod).
# Each environment has its own docker-compose.yml, .env, and VERSION file.
#
# Each build creates these tags:
#   chatbot-api-<env>:<version>             e.g. chatbot-api-dev:1.2.3
#   chatbot-api-<env>:<version>-<git_hash>  e.g. chatbot-api-dev:1.2.3-abc1234
#   chatbot-api-<env>:latest
# And re-tags :latest → :previous before tagging the new image as latest.
#
# Compose project name is locked via the `name:` field at the top of each
# environment's docker-compose.yml, so manual `docker-compose down` invocations
# from the env folder still target the same project as this script.

set -e

# Always run from this script's directory (deploy/)
cd "$(dirname "$0")"

# ── Parse environment argument ──────────────────────────────────
ENV_NAME="$1"
if [ -z "$ENV_NAME" ]; then
    echo "ERROR: missing environment argument."
    echo "Usage: ./deploy.sh <env> [command]"
    echo "Available environments:"
    ls -d */ 2>/dev/null | sed 's|/||' | sed 's/^/  /'
    exit 1
fi

ENV_DIR="$ENV_NAME"
if [ ! -d "$ENV_DIR" ]; then
    echo "ERROR: environment folder '$ENV_DIR' not found."
    exit 1
fi
if [ ! -f "$ENV_DIR/docker-compose.yml" ]; then
    echo "ERROR: $ENV_DIR/docker-compose.yml not found."
    exit 1
fi
if [ ! -f "$ENV_DIR/.env" ]; then
    echo "ERROR: $ENV_DIR/.env not found. Copy from $ENV_DIR/.env.example and fill in values."
    exit 1
fi

shift  # consume env arg, leaving the rest as subcommand/flags

IMAGE_NAME="chatbot-api-${ENV_NAME}"
VERSION_FILE="${ENV_DIR}/VERSION"
BRANCH_FILE="${ENV_DIR}/BRANCH"
COMPOSE="docker-compose -f ${ENV_DIR}/docker-compose.yml -p chatbot-api-${ENV_NAME}"

# Resolve branch from env folder, default to develop
if [ -f "$BRANCH_FILE" ]; then
    BRANCH=$(cat "$BRANCH_FILE" | tr -d '[:space:]')
else
    BRANCH="develop"
fi

# ── Helpers ─────────────────────────────────────────────────────
image_exists() {
    sudo docker image inspect "${IMAGE_NAME}:$1" >/dev/null 2>&1
}

list_tags() {
    sudo docker images ${IMAGE_NAME} --format "  {{.Tag}}\t{{.CreatedSince}}\t{{.Size}}"
}

switch_to_tag() {
    local tag="$1"
    if ! image_exists "$tag"; then
        echo "ERROR: image ${IMAGE_NAME}:${tag} not found locally"
        echo "Available tags:"
        list_tags
        exit 1
    fi
    if image_exists latest; then
        sudo docker tag ${IMAGE_NAME}:latest ${IMAGE_NAME}:previous
    fi
    sudo docker tag ${IMAGE_NAME}:${tag} ${IMAGE_NAME}:latest
    IMAGE_TAG=latest IMAGE_NAME=${IMAGE_NAME} sudo -E ${COMPOSE} up -d --no-build
    sudo ${COMPOSE} ps
}

# ── Subcommands ─────────────────────────────────────────────────
case "$1" in
    rollback)
        if ! image_exists previous; then
            echo "ERROR: no previous image found (${IMAGE_NAME}:previous)"
            exit 1
        fi
        echo "==> Rolling back to ${IMAGE_NAME}:previous"
        sudo docker tag ${IMAGE_NAME}:previous ${IMAGE_NAME}:latest
        IMAGE_TAG=latest IMAGE_NAME=${IMAGE_NAME} sudo -E ${COMPOSE} up -d --no-build --force-recreate
        sudo ${COMPOSE} ps
        exit 0
        ;;
    use)
        if [ -z "$2" ]; then
            echo "Usage: ./deploy.sh ${ENV_NAME} use <tag>"
            exit 1
        fi
        switch_to_tag "$2"
        exit 0
        ;;
    list)
        echo "Local image tags for ${IMAGE_NAME}:"
        list_tags
        exit 0
        ;;
    down)
        # `down -v` also removes named volumes (DESTRUCTIVE — postgres/redis/minio data).
        DOWN_FLAGS=""
        if [ "$2" = "-v" ] || [ "$2" = "--volumes" ]; then
            echo "==> [${ENV_NAME}] Stopping containers AND removing named volumes (destructive)"
            DOWN_FLAGS="--volumes"
        else
            echo "==> [${ENV_NAME}] Stopping & removing containers (volumes preserved)"
        fi
        sudo ${COMPOSE} down ${DOWN_FLAGS}
        exit 0
        ;;
esac

# ── Parse build flags ───────────────────────────────────────────
# Recognized flags (order-independent after env): -v <ver>, --no-cache
VERSION=""
NO_CACHE=""
while [ $# -gt 0 ]; do
    case "$1" in
        -v)
            if [ -z "$2" ]; then
                echo "ERROR: -v requires a version argument"
                exit 1
            fi
            VERSION="$2"
            shift 2
            ;;
        --no-cache)
            NO_CACHE="--no-cache"
            shift
            ;;
        *)
            echo "ERROR: unknown argument '$1'"
            exit 1
            ;;
    esac
done

if [ -z "$VERSION" ] && [ -f "$VERSION_FILE" ]; then
    VERSION=$(cat "$VERSION_FILE" | tr -d '[:space:]')
fi

if [ -z "$VERSION" ]; then
    echo "ERROR: no version specified. Use -v <version> or create $VERSION_FILE."
    exit 1
fi

# ── Normal deploy ───────────────────────────────────────────────
echo "==> [${ENV_NAME}] Switching to branch $BRANCH"
git -C .. checkout $BRANCH

echo "==> Pulling latest code"
git -C .. pull origin $BRANCH

GIT_HASH=$(git -C .. rev-parse --short HEAD)
FULL_TAG="${VERSION}-${GIT_HASH}"

# Save current 'latest' as 'previous' for quick rollback
if image_exists latest; then
    echo "==> Saving current image as ${IMAGE_NAME}:previous"
    sudo docker tag ${IMAGE_NAME}:latest ${IMAGE_NAME}:previous
fi

echo "==> Building ${IMAGE_NAME}:${FULL_TAG}${NO_CACHE:+ (no cache)}"
# `--pull` always refreshes base images (e.g. python:3.12-slim) so security/runtime
# patches land. `--no-cache` (opt-in via flag) discards layer cache for a full rebuild.
IMAGE_TAG=${FULL_TAG} IMAGE_NAME=${IMAGE_NAME} sudo -E ${COMPOSE} build --pull ${NO_CACHE} chatbot-api

# Tag with both the short version and the full version-hash, plus latest
sudo docker tag ${IMAGE_NAME}:${FULL_TAG} ${IMAGE_NAME}:${VERSION}
sudo docker tag ${IMAGE_NAME}:${FULL_TAG} ${IMAGE_NAME}:latest

echo "==> Stopping containers"
sudo ${COMPOSE} down

echo "==> Starting containers"
# `--force-recreate` ensures the container is replaced even when the image tag
# string did not change (e.g. :latest re-pointed to a new image id).
IMAGE_TAG=latest IMAGE_NAME=${IMAGE_NAME} sudo -E ${COMPOSE} up -d --force-recreate

echo "==> Current status"
sudo ${COMPOSE} ps

echo ""
echo "==> Done."
echo "    Environment:    ${ENV_NAME}"
echo "    Version:        ${VERSION}"
echo "    Full tag:       ${FULL_TAG}"
echo "    Tail logs:      sudo ${COMPOSE} logs -f chatbot-api"
echo "    Rollback:       ./deploy.sh ${ENV_NAME} rollback"
echo "    Switch tag:     ./deploy.sh ${ENV_NAME} use <tag>"
echo "    List images:    ./deploy.sh ${ENV_NAME} list"
echo "    Stop:           ./deploy.sh ${ENV_NAME} down"
echo "    No-cache build: ./deploy.sh ${ENV_NAME} --no-cache"
