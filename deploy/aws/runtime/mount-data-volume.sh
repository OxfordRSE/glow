#!/usr/bin/env bash
set -euo pipefail

DATA_DEVICE="/dev/xvdf"
DATA_MOUNT_POINT="/data"

info() { echo "[INFO] $*"; }
warn() { echo "[WARN] $*"; }
step() { echo "[PROGRESS] $*"; }
error() { echo "[ERROR] $*" >&2; }

resolve_path() {
  readlink -f "$1" 2>/dev/null || printf '%s\n' "$1"
}

main() {
  step "Mounting persistent data volume"

  local expected_device mounted_source mounted_options actual_source actual_options
  local data_uuid fstab_entry fs_file line retries tmp_fstab

  retries=30
  while [[ ! -e "${DATA_DEVICE}" && ${retries} -gt 0 ]]; do
    sleep 2
    retries=$((retries - 1))
  done

  if [[ ! -e "${DATA_DEVICE}" ]]; then
    error "Persistent data device not present: ${DATA_DEVICE}"
    exit 1
  fi

  if ! file -s "${DATA_DEVICE}" | grep -qiE 'filesystem|ext4'; then
    step "Formatting fresh data volume"
    mkfs.ext4 -F "${DATA_DEVICE}"
  fi

  mkdir -p "${DATA_MOUNT_POINT}"
  expected_device="$(resolve_path "${DATA_DEVICE}")"
  mounted_source="$(findmnt -n -o SOURCE --target "${DATA_MOUNT_POINT}" 2>/dev/null || true)"
  mounted_options="$(findmnt -n -o OPTIONS --target "${DATA_MOUNT_POINT}" 2>/dev/null || true)"
  if [[ -n "${mounted_source}" ]]; then
    mounted_source="$(resolve_path "${mounted_source}")"
  fi

  if [[ -z "${mounted_source}" ]]; then
    mount "${expected_device}" "${DATA_MOUNT_POINT}"
  elif [[ "${mounted_source}" == "${expected_device}" ]]; then
    :
  elif [[ ",${mounted_options}," == *,ro,* ]] || [[ ! -e "${mounted_source}" ]]; then
    warn "/data is mounted from unexpected source ${mounted_source} with options ${mounted_options}; replacing it with ${expected_device}"
    umount "${DATA_MOUNT_POINT}"
    mount "${expected_device}" "${DATA_MOUNT_POINT}"
  else
    error "/data is already mounted from unexpected writable source ${mounted_source}; expected ${expected_device}"
    exit 1
  fi

  actual_source="$(findmnt -n -o SOURCE --target "${DATA_MOUNT_POINT}" 2>/dev/null || true)"
  actual_options="$(findmnt -n -o OPTIONS --target "${DATA_MOUNT_POINT}" 2>/dev/null || true)"
  if [[ -z "${actual_source}" ]]; then
    error "${DATA_MOUNT_POINT} is not mounted after attempting to mount ${expected_device}"
    exit 1
  fi
  actual_source="$(resolve_path "${actual_source}")"
  if [[ "${actual_source}" != "${expected_device}" ]]; then
    error "${DATA_MOUNT_POINT} mounted from ${actual_source}, expected ${expected_device}"
    exit 1
  fi
  if [[ ",${actual_options}," == *,ro,* ]]; then
    error "${DATA_MOUNT_POINT} is mounted read-only from ${actual_source}; run fsck on the data volume"
    exit 1
  fi

  data_uuid="$(blkid -s UUID -o value "${expected_device}" 2>/dev/null || true)"
  if [[ -z "${data_uuid}" ]]; then
    error "Could not determine UUID for ${expected_device}"
    exit 1
  fi

  fstab_entry="UUID=${data_uuid} ${DATA_MOUNT_POINT} ext4 defaults,nofail 0 2"
  tmp_fstab="$(mktemp)"
  while IFS= read -r line || [[ -n "${line}" ]]; do
    if [[ "${line}" =~ ^[[:space:]]*# ]] || [[ -z "${line//[[:space:]]/}" ]]; then
      printf '%s\n' "${line}" >> "${tmp_fstab}"
      continue
    fi

    read -r _ fs_file _ <<< "${line}"
    if [[ "${fs_file:-}" == "${DATA_MOUNT_POINT}" ]]; then
      continue
    fi
    printf '%s\n' "${line}" >> "${tmp_fstab}"
  done < /etc/fstab
  printf '%s\n' "${fstab_entry}" >> "${tmp_fstab}"
  cat "${tmp_fstab}" > /etc/fstab
  rm -f "${tmp_fstab}"

  local probe="${DATA_MOUNT_POINT}/.glow-write-test"
  touch "${probe}" || {
    error "Mounted data volume at ${DATA_MOUNT_POINT} is not writable"
    exit 1
  }
  rm -f "${probe}"

  info "Persistent data volume is mounted and writable"
}

main "$@"
