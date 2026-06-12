#!/usr/bin/env bash
set -euo pipefail

check() {
  local name="$1"
  local url="$2"
  echo "[PROGRESS] Checking ${name}: ${url}"
  curl -fsS "$url" >/dev/null
}

check "API" "http://127.0.0.1:8000/health"
check "Dashboard" "http://127.0.0.1:3000/en"
check "ODK" "http://127.0.0.1:8080/"

echo "[SUCCESS] Runner healthcheck passed"
