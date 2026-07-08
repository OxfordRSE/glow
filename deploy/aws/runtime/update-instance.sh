#!/usr/bin/env bash
set -euo pipefail

exec > >(tee -a /var/log/glow-update.log) 2>&1

source /etc/glow-runner.env

WORK_DIR="/opt/glow"
STATE_DIR="/var/lib/glow"
TARGET_REF="${GIT_REF:?GIT_REF is required}"
DOMAIN_NAME="${DOMAIN_NAME:?DOMAIN_NAME is required}"

PREVIOUS_REF="$(git -C "${WORK_DIR}" rev-parse HEAD || true)"

echo "[PROGRESS] Updating to ${TARGET_REF}"

mkdir -p "${STATE_DIR}/.deploy/share"
if [[ ! -L "${WORK_DIR}/docker-mount-data" ]]; then
  rm -rf "${WORK_DIR}/docker-mount-data"
  ln -sfn "${STATE_DIR}" "${WORK_DIR}/docker-mount-data"
fi

git -C "${WORK_DIR}" fetch --tags --prune origin
git -C "${WORK_DIR}" checkout --force "${TARGET_REF}"

if [[ -x "${WORK_DIR}/deploy/update-instance.sh" ]]; then
  echo "[PROGRESS] Running repository update hook"
  PREVIOUS_REF="${PREVIOUS_REF}" TARGET_REF="${TARGET_REF}" \
    "${WORK_DIR}/deploy/update-instance.sh"
fi

echo "[PROGRESS] Stopping stack"
sudo bash "${WORK_DIR}/deploy/aws/runtime/stop-stack.sh" || true

echo "[PROGRESS] Activating stack"
DOMAIN_NAME="${DOMAIN_NAME}" sudo bash "${WORK_DIR}/deploy/aws/runtime/activate-stack.sh"

echo "[PROGRESS] Running healthcheck"
sudo /opt/glow-runner/healthcheck.sh

echo "[SUCCESS] Update complete"
