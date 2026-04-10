#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_FROM_SCRIPT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEFAULT_REPO_DIR="$HOME/apps/obsidian-bot"

if [[ -d "$REPO_FROM_SCRIPT/.git" ]]; then
  ROOT_DIR="${AUTO_UPDATE_ROOT_DIR:-$REPO_FROM_SCRIPT}"
else
  ROOT_DIR="${AUTO_UPDATE_ROOT_DIR:-$DEFAULT_REPO_DIR}"
fi

BRANCH="${AUTO_UPDATE_BRANCH:-codex/miniapp-migration}"
LOCK_FILE="${AUTO_UPDATE_LOCK_FILE:-/tmp/obsidian-bot-auto-update.lock}"
API_HEALTH_URL="${AUTO_UPDATE_API_HEALTH_URL:-http://127.0.0.1:8000/api/health}"
HEALTH_TIMEOUT="${AUTO_UPDATE_HEALTH_TIMEOUT:-10}"
SYNC_DB="${AUTO_UPDATE_SYNC_DB:-1}"
COMPOSE_SERVICES="${AUTO_UPDATE_COMPOSE_SERVICES:-api web bot}"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log "ERROR: required command not found: $1"
    exit 1
  fi
}

require_cmd git
require_cmd docker
require_cmd curl
require_cmd flock

if ! docker compose version >/dev/null 2>&1; then
  log "ERROR: docker compose plugin is not available"
  exit 1
fi

if [[ ! -d "$ROOT_DIR/.git" ]]; then
  log "ERROR: repo not found at $ROOT_DIR"
  exit 1
fi

mkdir -p "$(dirname "$LOCK_FILE")"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  log "SKIP: another auto-update process is already running"
  exit 0
fi

cd "$ROOT_DIR"

if [[ -n "$(git status --porcelain)" ]]; then
  log "SKIP: working tree is dirty; manual intervention required"
  exit 0
fi

current_branch="$(git branch --show-current)"
if [[ "$current_branch" != "$BRANCH" ]]; then
  log "Switching branch: $current_branch -> $BRANCH"
  git switch "$BRANCH"
fi

log "Fetching updates from origin/$BRANCH"
git fetch origin "$BRANCH"

if ! git show-ref --verify --quiet "refs/remotes/origin/$BRANCH"; then
  log "ERROR: remote branch origin/$BRANCH not found"
  exit 1
fi

local_sha="$(git rev-parse HEAD)"
remote_sha="$(git rev-parse "origin/$BRANCH")"

if [[ "$local_sha" == "$remote_sha" ]]; then
  log "No updates found"
  exit 0
fi

if ! git merge-base --is-ancestor "$local_sha" "$remote_sha"; then
  log "SKIP: local branch is ahead/diverged; refusing non-fast-forward update"
  exit 0
fi

log "Fast-forward update to $remote_sha"
git pull --ff-only origin "$BRANCH"

log "Rebuilding and restarting services: $COMPOSE_SERVICES"
docker compose up -d --build $COMPOSE_SERVICES

if [[ "$SYNC_DB" == "1" ]]; then
  log "Syncing database with vault"
  docker compose exec -T bot python - <<'PY'
import asyncio
from bot.database import engine
from bot.database.models import init_db
from bot.services.obsidian_service import sync_db_with_vault

async def main() -> None:
    await init_db(engine)
    await sync_db_with_vault()

asyncio.run(main())
PY
fi

if [[ -n "$API_HEALTH_URL" ]]; then
  log "Checking API health: $API_HEALTH_URL"
  health_body="$(curl -fsS --max-time "$HEALTH_TIMEOUT" "$API_HEALTH_URL")"
  log "Health OK: $health_body"
fi

log "Auto-update finished successfully"
