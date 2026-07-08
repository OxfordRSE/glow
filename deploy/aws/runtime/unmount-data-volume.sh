#!/usr/bin/env bash
set -euo pipefail

DATA_MOUNT_POINT="/data"

info() { echo "[INFO] $*"; }
step() { echo "[PROGRESS] $*"; }
error() { echo "[ERROR] $*" >&2; }

main() {
  step "Unmounting persistent data volume"

  if ! findmnt -n --target "${DATA_MOUNT_POINT}" >/dev/null 2>&1; then
    info "${DATA_MOUNT_POINT} is already unmounted"
    exit 0
  fi

  umount "${DATA_MOUNT_POINT}"

  if findmnt -n --target "${DATA_MOUNT_POINT}" >/dev/null 2>&1; then
    error "${DATA_MOUNT_POINT} is still mounted after unmount"
    exit 1
  fi

  info "Persistent data volume unmounted"
}

main "$@"
