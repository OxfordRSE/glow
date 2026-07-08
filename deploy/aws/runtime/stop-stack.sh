#!/usr/bin/env bash
set -euo pipefail

WORK_DIR="/opt/glow"
STATE_DIR="/var/lib/glow"
RUNTIME_ENV="${STATE_DIR}/.deploy/share/.env.runtime"

if [[ ! -f "${RUNTIME_ENV}" ]]; then
  echo "[WARN] Runtime environment missing; nothing to stop"
  exit 0
fi

cd "${WORK_DIR}"
docker compose --profile odk --env-file "${RUNTIME_ENV}" -f "$WORK_DIR/compose.yml" down --remove-orphans
echo "[SUCCESS] Stack stopped"
