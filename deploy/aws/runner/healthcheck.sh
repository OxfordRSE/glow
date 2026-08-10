#!/usr/bin/env bash
set -euo pipefail

check() {
  local name="$1"
  local url="$2"
  echo "[PROGRESS] Checking ${name}: ${url}"
  curl -fsS "$url" >/dev/null
}

# ODK's nginx routes on Host and has no vhost for a bare 127.0.0.1 request,
# so it 421s any locally-curled request lacking the real domain's Host
# header. That 421 (like an unmatched-vhost 301) just proves nginx itself
# is up, so treat both as healthy rather than depending on the instance's
# domain config here.
check_odk() {
  local url="$1"
  echo "[PROGRESS] Checking ODK: ${url}"
  local status
  status=$(curl -s -o /dev/null -w '%{http_code}' "$url" || true)
  case "$status" in
    2[0-9][0-9]|301|421) return 0 ;;
    *) echo "ODK check got unexpected HTTP status ${status}" >&2; return 22 ;;
  esac
}

check "API" "http://127.0.0.1:8000/health"
check "Dashboard" "http://127.0.0.1:3000/en"
check_odk "http://127.0.0.1:8080/"

echo "[SUCCESS] Runner healthcheck passed"
