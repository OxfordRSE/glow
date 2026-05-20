#!/usr/bin/env bash
# deploy.sh — Idempotent deploy script for glow-core
# Usage: ./deploy.sh [version]
#   version: e.g. 0.1.0 or 0.1.0-beta2 (must match API version 0.1.0)
#            if omitted, you must set IMAGE_TAG env var.
#
# Requirements: aws, terraform, docker, curl, jq

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="${SCRIPT_DIR}/terraform"
APP_NAME="glow-core"
AWS_REGION="${AWS_REGION:-eu-west-2}"
S3_LOCKFILE_KEY="${APP_NAME}/lockfile.json"
LOCKFILE_LOCAL="${SCRIPT_DIR}/.deploy-lock.json"

# ─── Colour helpers ──────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RESET='\033[0m'
info()    { echo -e "${GREEN}[INFO]${RESET}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
confirm() {
  local prompt="$1"
  local answer
  read -r -p "${prompt} [y/N] " answer
  [[ "${answer,,}" == "y" ]]
}

# ─── 1. Required tools ───────────────────────────────────────────────────────
check_tools() {
  info "Checking required tools..."
  local missing=()
  for tool in aws terraform docker curl jq python3; do
    if ! command -v "$tool" &>/dev/null; then
      missing+=("$tool")
    fi
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    error "Missing required tools: ${missing[*]}"
    error "Please install them and re-run."
    exit 1
  fi
  info "All required tools are available."
}

# ─── 2. Version check ────────────────────────────────────────────────────────
check_version() {
  local deploy_version="$1"

  # Extract the base semver from deploy_version (strip pre-release suffix e.g. -beta2)
  local base_version
  base_version="$(echo "${deploy_version}" | sed 's/^\([0-9]*\.[0-9]*\.[0-9]*\).*/\1/')"

  # Read API version from pyproject.toml
  local api_version
  api_version="$(grep '^version' "${SCRIPT_DIR}/api/pyproject.toml" \
    | head -1 | sed 's/version *= *"\(.*\)"/\1/')"

  if [[ "${base_version}" != "${api_version}" ]]; then
    error "Version mismatch!"
    error "  Deploy version base: ${base_version}"
    error "  API version:         ${api_version}"
    error "The base semver of the deploy version must match the API version."
    error "  e.g. deploy version 0.1.0-beta2 matches API version 0.1.0"
    exit 1
  fi
  info "Version check passed: ${deploy_version} (API: ${api_version})"
}

# ─── 3. AWS SSO login ────────────────────────────────────────────────────────
aws_login() {
  info "Checking AWS credentials..."
  if ! aws sts get-caller-identity --region "${AWS_REGION}" &>/dev/null; then
    info "Not logged in. Running 'aws sso login'..."
    if ! aws sso login; then
      error "AWS SSO login failed."
      exit 1
    fi
  fi
  local account_id
  account_id="$(aws sts get-caller-identity --query Account --output text)"
  info "Authenticated as account ${account_id} in ${AWS_REGION}."
  echo "${account_id}"
}

# ─── 4. S3 lockfile ──────────────────────────────────────────────────────────
ensure_s3_bucket() {
  local bucket="$1"
  if ! aws s3api head-bucket --bucket "${bucket}" 2>/dev/null; then
    info "Creating S3 bucket: ${bucket}"
    if [[ "${AWS_REGION}" == "us-east-1" ]]; then
      aws s3api create-bucket --bucket "${bucket}" --region "${AWS_REGION}"
    else
      aws s3api create-bucket --bucket "${bucket}" --region "${AWS_REGION}" \
        --create-bucket-configuration LocationConstraint="${AWS_REGION}"
    fi
    aws s3api put-bucket-versioning --bucket "${bucket}" \
      --versioning-configuration Status=Enabled
    aws s3api put-public-access-block --bucket "${bucket}" \
      --public-access-block-configuration \
      "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
    info "Bucket created and configured."
  fi
}

check_lockfile() {
  local bucket="$1"
  local remote_lockfile="/tmp/glow-core-remote-lock.json"

  _lockfile_summary() {
    local f="$1"
    local label="$2"
    local size
    size="$(du -sh "${f}" 2>/dev/null | cut -f1)"
    local mtime
    mtime="$(date -r "${f}" '+%Y-%m-%d %H:%M:%S %Z' 2>/dev/null || stat -c '%y' "${f}" 2>/dev/null | cut -d. -f1)"
    echo "  ${label}: ${size}, last modified ${mtime}"
  }

  if aws s3 cp "s3://${bucket}/${S3_LOCKFILE_KEY}" "${remote_lockfile}" 2>/dev/null; then
    if [[ -f "${LOCKFILE_LOCAL}" ]]; then
      if ! diff -q "${LOCKFILE_LOCAL}" "${remote_lockfile}" &>/dev/null; then
        warn "Local lockfile differs from remote lockfile!"
        echo ""
        _lockfile_summary "${remote_lockfile}" "Remote (S3)"
        _lockfile_summary "${LOCKFILE_LOCAL}"  "Local      "
        echo ""
        echo "Which lockfile should be kept?"
        echo "  1) Keep remote (download from S3 to local)"
        echo "  2) Keep local  (upload local to S3)"
        local choice
        read -r -p "Enter 1 or 2: " choice
        case "${choice}" in
          1)
            cp "${remote_lockfile}" "${LOCKFILE_LOCAL}"
            info "Using remote lockfile."
            ;;
          2)
            aws s3 cp "${LOCKFILE_LOCAL}" "s3://${bucket}/${S3_LOCKFILE_KEY}"
            info "Uploaded local lockfile to S3."
            ;;
          *)
            error "Invalid choice. Aborting."
            exit 1
            ;;
        esac
      else
        info "Lockfile is consistent with remote."
      fi
    else
      info "No local lockfile found; downloading from S3."
      cp "${remote_lockfile}" "${LOCKFILE_LOCAL}"
    fi
  else
    info "No remote lockfile found; this appears to be a fresh deployment."
    if [[ ! -f "${LOCKFILE_LOCAL}" ]]; then
      echo '{"deployed_by":"'$(aws sts get-caller-identity --query Arn --output text)'","first_deploy":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"}' \
        | jq '.' > "${LOCKFILE_LOCAL}"
    fi
    aws s3 cp "${LOCKFILE_LOCAL}" "s3://${bucket}/${S3_LOCKFILE_KEY}"
    info "Lockfile uploaded to S3."
  fi
}

# ─── 5. Docker build & push ──────────────────────────────────────────────────
build_and_push() {
  local account_id="$1"
  local image_tag="$2"
  local ecr_base="${account_id}.dkr.ecr.${AWS_REGION}.amazonaws.com"

  info "Logging in to ECR..."
  aws ecr get-login-password --region "${AWS_REGION}" \
    | docker login --username AWS --password-stdin "${ecr_base}"

  local api_repo="${ecr_base}/${APP_NAME}-api"
  local dashboard_repo="${ecr_base}/${APP_NAME}-dashboard"

  # Check if tags already exist (ECR immutable tags — cannot overwrite)
  for repo_url in "${api_repo}" "${dashboard_repo}"; do
    local repo_name
    repo_name="$(basename "${repo_url}")"
    if aws ecr describe-images \
      --repository-name "${repo_name}" \
      --image-ids imageTag="${image_tag}" \
      --region "${AWS_REGION}" &>/dev/null; then
      warn "Image ${repo_url}:${image_tag} already exists in ECR (immutable tags)."
      warn "Skipping build for ${repo_name} — using existing image."
    else
      info "Building ${repo_name}:${image_tag}..."
      local context_dir
      context_dir="${SCRIPT_DIR}/$(echo "${repo_name}" | sed "s/${APP_NAME}-//")"
      docker build -t "${repo_url}:${image_tag}" "${context_dir}"
      docker push "${repo_url}:${image_tag}"
      info "Pushed ${repo_url}:${image_tag}"
    fi
  done
}

# ─── 6. Terraform apply ──────────────────────────────────────────────────────
terraform_apply() {
  local account_id="$1"
  local image_tag="$2"
  local tfstate_bucket="$3"

  info "Initialising Terraform..."
  terraform -chdir="${TERRAFORM_DIR}" init \
    -backend-config="bucket=${tfstate_bucket}" \
    -backend-config="region=${AWS_REGION}" \
    -reconfigure

  info "Applying Terraform changes (Terraform will prompt for confirmation)..."
  terraform -chdir="${TERRAFORM_DIR}" apply \
    -var="image_tag=${image_tag}" \
    -var="api_secret_key=${GLOW_SECRET_KEY:?GLOW_SECRET_KEY env var required}" \
    -var="aws_region=${AWS_REGION}"
  info "Terraform apply complete."
}

# ─── 7. Update lockfile ──────────────────────────────────────────────────────
update_lockfile() {
  local bucket="$1"
  local image_tag="$2"
  local account_id="$3"

  jq -n \
    --arg tag "${image_tag}" \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg arn "$(aws sts get-caller-identity --query Arn --output text)" \
    '{"last_deployed_tag":$tag,"last_deployed_at":$ts,"deployed_by":$arn}' \
    > "${LOCKFILE_LOCAL}"

  aws s3 cp "${LOCKFILE_LOCAL}" "s3://${bucket}/${S3_LOCKFILE_KEY}"
  info "Lockfile updated in S3."
}

# ─── Main ────────────────────────────────────────────────────────────────────
main() {
  local image_tag="${1:-}"

  # Determine image tag
  if [[ -z "${image_tag}" ]]; then
    if [[ -n "${IMAGE_TAG:-}" ]]; then
      image_tag="${IMAGE_TAG}"
    else
      error "No version specified. Usage: ./deploy.sh [version]"
      error "  e.g. ./deploy.sh 0.1.0  or  ./deploy.sh 0.1.0-beta2"
      error "  Or set IMAGE_TAG env var."
      exit 1
    fi
  fi

  check_tools
  check_version "${image_tag}"

  local account_id
  account_id="$(aws_login)"

  # S3 bucket for Terraform state + lockfile (must be globally unique)
  local tfstate_bucket="${APP_NAME}-tfstate-${account_id}"

  ensure_s3_bucket "${tfstate_bucket}"
  check_lockfile "${tfstate_bucket}"
  build_and_push "${account_id}" "${image_tag}"
  terraform_apply "${account_id}" "${image_tag}" "${tfstate_bucket}"
  update_lockfile "${tfstate_bucket}" "${image_tag}" "${account_id}"

  info "✅ Deployment of ${APP_NAME}:${image_tag} complete!"
  terraform -chdir="${TERRAFORM_DIR}" output
}

main "$@"
