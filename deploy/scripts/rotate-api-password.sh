#!/usr/bin/env bash
# rotate-api-password.sh — Rotate ODK API user password
#
# This script:
#   1. Generates a new password for the ODK API user (glow-api@<domain>)
#   2. Updates the password in ODK Central via CLI
#   3. Updates .env.runtime with the new password
#   4. Restarts the API container to pick up the new credentials
#
# Usage:
#   ./deploy/scripts/rotate-api-password.sh
#
# Prerequisites:
#   - Must be run on the EC2 instance
#   - Docker stack must be running
#   - deploy/.deploy/share/.env.runtime must exist

set -euo pipefail

# ─── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; RESET='\033[0m'
info()  { echo -e "${GREEN}[INFO]${RESET}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error() { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
step()  { echo -e "\n${BLUE}▶${RESET} $*\n"; }

WORK_DIR="/opt/glow"
DEPLOY_DIR="${WORK_DIR}/deploy"
RUNTIME_ENV="${DEPLOY_DIR}/.deploy/share/.env.runtime"

# ─── Validate environment ────────────────────────────────────────────────────
if [[ ! -f "${RUNTIME_ENV}" ]]; then
  error "Runtime environment not found: ${RUNTIME_ENV}"
  error "Have you run activate-stack.sh yet?"
  exit 1
fi

cd "${WORK_DIR}"

# ─── Rotate password ─────────────────────────────────────────────────────────
rotate_password() {
  step "Rotating ODK API user password"
  
  source "${RUNTIME_ENV}"
  
  local api_email="${ODK_API_EMAIL}"
  if [[ -z "${api_email}" ]]; then
    error "ODK_API_EMAIL not found in ${RUNTIME_ENV}"
    exit 1
  fi
  
  # Generate new password (24 bytes base64 ~ 32 chars)
  local new_password
  new_password="$(openssl rand -base64 24 | tr -d '\n')"
  
  info "Updating password for ${api_email} in ODK Central"
  
  # Update password using ODK CLI
  sudo docker compose --env-file "${RUNTIME_ENV}" --profile odk exec -T service \
    node /usr/odk/lib/bin/cli.js user-set-password "${api_email}" "${new_password}" || {
    error "Failed to update password in ODK Central"
    exit 1
  }
  
  info "Password updated in ODK Central"
  
  # Update .env.runtime file
  step "Updating ${RUNTIME_ENV}"
  
  # Create a temp file with updated password
  local tmp_file
  tmp_file="$(mktemp)"
  
  # Replace ODK_API_PASSWORD line
  sed "s|^ODK_API_PASSWORD=.*|ODK_API_PASSWORD=${new_password}|" "${RUNTIME_ENV}" > "${tmp_file}"
  
  # Replace original file
  mv "${tmp_file}" "${RUNTIME_ENV}"
  chmod 600 "${RUNTIME_ENV}"
  
  info "Updated ${RUNTIME_ENV}"
  
  # Restart API container
  step "Restarting API container"
  
  sudo docker compose --env-file "${RUNTIME_ENV}" up -d --force-recreate api
  
  info "API container restarted with new credentials"
}

# ─── Verify ──────────────────────────────────────────────────────────────────
verify() {
  step "Verifying API health"
  
  sleep 5
  
  if sudo docker compose --env-file "${RUNTIME_ENV}" exec -T api \
    curl -sf http://localhost:8000/health &>/dev/null; then
    info "✓ API health check passed"
  else
    warn "✗ API health check failed - check logs with: docker compose logs api"
    exit 1
  fi
}

# ─── Main ────────────────────────────────────────────────────────────────────
main() {
  info "Starting ODK API password rotation"
  
  rotate_password
  verify
  
  step "Password rotation complete!"
  echo ""
  info "New credentials stored in: ${RUNTIME_ENV}"
  info "API container has been restarted"
  echo ""
}

main "$@"
