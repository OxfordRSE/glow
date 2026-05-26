#!/usr/bin/env bash
# update-stack.sh — Update existing GLOW deployment
#
# Expected to run on EC2 instance via SSM Run Command or manually
# Assumes:
#   - /opt/glow exists (git repo)
#   - docker-mount-data exists (symlink to /data or local dir)
#   - Previous deployment successful

set -euo pipefail

# ─── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; RESET='\033[0m'
info()  { echo -e "${GREEN}[INFO]${RESET}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error() { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
step()  { echo -e "\n${BLUE}▶${RESET} $*\n"; }

WORK_DIR="/opt/glow"
DATA_DIR="${WORK_DIR}/docker-mount-data"
RUNTIME_ENV="${DATA_DIR}/.deploy/share/.env.runtime"
GIT_REF="${GIT_REF:-}"  # Can be set via environment

cd "${WORK_DIR}"

step "Starting GLOW stack update"

# Validate runtime env exists
if [[ ! -f "${RUNTIME_ENV}" ]]; then
  error "No existing deployment found (${RUNTIME_ENV} missing)"
  error "This script is for updates only. Run activate-stack.sh for initial deployment."
  exit 1
fi

# Source validation functions from activate-stack.sh
source <(grep -A 50 "^# ─── Version Validation" deploy/scripts/activate-stack.sh | grep -B 50 "^# ─── Write Deployment Version")
source <(grep -A 20 "^# ─── Write Deployment Version" deploy/scripts/activate-stack.sh)

# Validate version upgrade path
validate_deployment_version

# Pull latest code
echo "[PROGRESS] Fetching latest changes from git"
git fetch --tags --prune

# Determine ref to checkout
if [ -z "$GIT_REF" ]; then
  # Find latest release tag
  GIT_REF=$(git describe --tags $(git rev-list --tags --max-count=1) 2>/dev/null || echo "main")
  info "Auto-detected ref: $GIT_REF"
else
  info "Using specified ref: $GIT_REF"
fi

# Checkout
if ! git rev-parse --verify "$GIT_REF" >/dev/null 2>&1; then
  error "Invalid git ref: $GIT_REF"
  exit 1
fi

echo "[PROGRESS] Checking out ${GIT_REF}"
git checkout "$GIT_REF"
info "Checked out: $(git rev-parse HEAD)"

# Rebuild and restart services
echo "[PROGRESS] Rebuilding services"
sudo docker compose --profile odk --env-file "${RUNTIME_ENV}" build

echo "[PROGRESS] Restarting services"
sudo docker compose --profile odk --env-file "${RUNTIME_ENV}" up -d

# Wait for services to be healthy
echo "[PROGRESS] Waiting for services to stabilize"
sleep 20

# Simple health check
info "Checking service health..."
if sudo docker compose --env-file "${RUNTIME_ENV}" ps | grep -q "unhealthy"; then
  warn "Some services appear unhealthy"
  sudo docker compose --env-file "${RUNTIME_ENV}" ps
else
  info "Services appear healthy"
fi

# Update version marker
write_deployment_version

echo "[SUCCESS] Update complete!"
info "New version: $(cat ${DATA_DIR}/.glow-deployment-version)"
