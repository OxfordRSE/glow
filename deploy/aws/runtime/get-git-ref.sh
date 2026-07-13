#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="/etc/glow-runner.env"

if [[ ! -f "${ENV_FILE}" ]]; then
  printf 'missing environment file: %s\n' "${ENV_FILE}" >&2
  exit 1
fi

source "${ENV_FILE}"

case "${1:-}" in
--commit)
  printf "%s\n" "${GIT_COMMIT:-}"
  ;;
""|--ref)
  printf "%s\n" "${GIT_REF:-}"
  ;;
*)
  printf 'usage: %s [--ref|--commit]\n' "$0" >&2
  exit 1
  ;;
esac
