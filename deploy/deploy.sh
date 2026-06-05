#!/usr/bin/env bash
# deploy.sh — Single-command deployment for Glow infrastructure
# Usage: ./deploy/deploy.sh
#
# Prerequisites:
#   - aws CLI configured
#   - terraform installed
#
# This script:
#   1. Runs terraform init + apply
#   2. Detects deployment state (initial vs update)
#   3. Monitors activation via CloudWatch logs
#   4. Handles failures with destroy/recreate option

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "${SCRIPT_DIR}")"
TERRAFORM_DIR="${SCRIPT_DIR}/terraform"
APP_NAME="glow-core"
AWS_REGION="${AWS_REGION:-eu-west-2}"

REPLACE=false
# Terraform address of the EC2 instance to recreate when
# --recreate-ec2 is specified.
REPLACE_RESOURCE=""
DEFAULT_REPLACE_RESOURCE="aws_instance.main"

# ─── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; RESET='\033[0m'
info()  { echo -e "${GREEN}[INFO]${RESET}  $*" >&2; }
warn()  { echo -e "${YELLOW}[WARN]${RESET}  $*" >&2; }
error() { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
step()  { echo -e "\n${BLUE}▶${RESET} $*\n" >&2; }

usage() {
  cat <<EOF
Usage:
  $(basename "$0") [options]

Options:
  --replace [resource.address]
      Force Terraform to destroy and recreate a resource during this deployment.
      If no resource address is provided, defaults to:
        ${DEFAULT_REPLACE_RESOURCE}

  -h, --help
      Show this help text.

Examples:
  ./deploy/deploy.sh
  ./deploy/deploy.sh --replace
  ./deploy/deploy.sh --replace aws_instance.main
  ./deploy/deploy.sh --replace module.compute.aws_instance.main

Notes:
  This is implemented using Terraform's -replace option on both plan and apply.
EOF
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --replace)
        REPLACE=true
        shift
        if [[ $# -gt 0 && "${1#-}" == "$1" ]]; then
          REPLACE_RESOURCE="$1"
          shift
        else
          REPLACE_RESOURCE="${DEFAULT_REPLACE_RESOURCE}"
        fi
        ;;
      --replace=*)
        REPLACE=true
        REPLACE_RESOURCE="${1#*=}"
        if [[ -z "${REPLACE_RESOURCE}" ]]; then
          REPLACE_RESOURCE="${DEFAULT_REPLACE_RESOURCE}"
        fi
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        error "Unknown argument: $1"
        echo ""
        usage
        exit 1
        ;;
    esac
  done
}

# ─── Check tools ─────────────────────────────────────────────────────────────
check_tools() {
  local missing=()
  for tool in aws terraform; do
    if ! command -v "$tool" &>/dev/null; then
      missing+=("$tool")
    fi
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    error "Missing required tools: ${missing[*]}"
    exit 1
  fi
}

# ─── AWS authentication ──────────────────────────────────────────────────────
check_aws_auth() {
  info "Checking AWS credentials..."
  if ! aws sts get-caller-identity --region "${AWS_REGION}" &>/dev/null; then
    error "AWS credentials not configured or expired."
    error "Set profile with export AWS_PROFILE=<profile_name>"
    error "Then run: aws configure  (or aws sso login)"
    exit 1
  fi
  local account_id
  account_id="$(aws sts get-caller-identity --query Account --output text)"
  info "Authenticated as account ${account_id} in region ${AWS_REGION}"
  echo "${account_id}"
}

# ─── Get domain name from terraform.tfvars ───────────────────────────────────
get_domain_from_tfvars() {
  local tfvars="${TERRAFORM_DIR}/terraform.tfvars"
  
  if [[ ! -f "$tfvars" ]]; then
    error "terraform.tfvars not found at: ${tfvars}"
    error "Please create terraform.tfvars from terraform.tfvars.example"
    exit 1
  fi
  
  # Extract domain_name value from tfvars (handle quotes and comments)
  local domain
  domain=$(grep -E '^\s*domain_name\s*=' "$tfvars" | \
    sed 's/.*=\s*"\([^"]*\)".*/\1/' | \
    head -1)
  
  if [[ -z "$domain" ]]; then
    error "domain_name not found in terraform.tfvars"
    error "Please set domain_name in terraform.tfvars"
    exit 1
  fi
  
  echo "$domain"
}

# ─── Get override bucket name from terraform.tfvars ──────────────────────────
get_override_bucket_from_tfvars() {
  local tfvars="${TERRAFORM_DIR}/terraform.tfvars"
  
  if [[ ! -f "$tfvars" ]]; then
    echo ""
    return
  fi
  
  # Extract tfstate_bucket_name value from tfvars (handle quotes and comments)
  local bucket
  bucket=$(grep -E '^\s*tfstate_bucket_name\s*=' "$tfvars" | \
    sed 's/.*=\s*"\([^"]*\)".*/\1/' | \
    head -1)
  
  echo "$bucket"
}

# ─── Generate S3 bucket name from domain ─────────────────────────────────────
generate_bucket_name() {
  local domain="$1"
  
  # Sanitize domain for S3 bucket name:
  # - Convert to lowercase
  # - Replace dots with hyphens
  # - Remove any invalid characters
  local sanitized
  sanitized=$(echo "$domain" | tr '[:upper:]' '[:lower:]' | tr '.' '-' | sed 's/[^a-z0-9-]//g')
  
  # S3 bucket names must be 3-63 characters
  # Format: <sanitized-domain>-tfstate
  local bucket="${sanitized}-tfstate"
  
  # Ensure not too long (S3 limit is 63 chars)
  if [[ ${#bucket} -gt 63 ]]; then
    # Truncate domain part but keep -tfstate suffix
    local max_domain_len=$((63 - 8))  # 8 chars for "-tfstate"
    sanitized="${sanitized:0:$max_domain_len}"
    bucket="${sanitized}-tfstate"
  fi
  
  echo "$bucket"
}

# ─── Ensure S3 backend bucket ────────────────────────────────────────────────
ensure_backend_bucket() {
  local bucket="$1"
  
  if aws s3api head-bucket --bucket "${bucket}" 2>/dev/null; then
    info "S3 backend bucket exists: ${bucket}"
    return
  fi
  
  info "Creating S3 bucket for Terraform state: ${bucket}"
  if [[ "${AWS_REGION}" == "us-east-1" ]]; then
    aws s3api create-bucket --bucket "${bucket}" --region "${AWS_REGION}"
  else
    aws s3api create-bucket \
      --bucket "${bucket}" \
      --region "${AWS_REGION}" \
      --create-bucket-configuration LocationConstraint="${AWS_REGION}"
  fi
  
  # Enable versioning
  aws s3api put-bucket-versioning \
    --bucket "${bucket}" \
    --versioning-configuration Status=Enabled
  
  # Block public access
  aws s3api put-public-access-block \
    --bucket "${bucket}" \
    --public-access-block-configuration \
      "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
  
  info "S3 bucket created and secured"
}

# ─── Terraform init & apply ──────────────────────────────────────────────────
run_terraform() {
  local bucket="$1"
  local -a tf_plan_args=()
  local -a tf_apply_args=(-auto-approve)

  if [[ "${REPLACE}" == "true" ]]; then
    info "Terraform replace requested for: ${REPLACE_RESOURCE}"
    tf_plan_args+=("-replace=${REPLACE_RESOURCE}")
    tf_apply_args+=("-replace=${REPLACE_RESOURCE}")
  fi

  step "Initializing Terraform"
  terraform -chdir="${TERRAFORM_DIR}" init \
    -backend-config="bucket=${bucket}" \
    -backend-config="region=${AWS_REGION}" \
    -reconfigure

  step "Running Terraform plan"
  terraform -chdir="${TERRAFORM_DIR}" plan "${tf_plan_args[@]}"

  echo ""
  read -p "Apply these changes? [y/N] " -n 1 -r
  echo ""
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    warn "Deployment cancelled"
    exit 0
  fi

  step "Applying Terraform configuration"
  terraform -chdir="${TERRAFORM_DIR}" apply "${tf_apply_args[@]}"
}

# ─── Detect deployment state ─────────────────────────────────────────────────
get_deployment_state() {
  local instance_id="$1"
  
  info "Detecting deployment state..."
  
  # Check if instance is newly created (< 5 minutes old)
  local launch_time
  launch_time=$(aws ec2 describe-instances \
    --instance-ids "${instance_id}" \
    --query 'Reservations[0].Instances[0].LaunchTime' \
    --output text \
    --region "${AWS_REGION}")
  
  local now
  now=$(date -u +%s)
  local launch_epoch
  # Handle both GNU date and macOS date
  launch_epoch=$(date -d "${launch_time}" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%S" "$(echo ${launch_time} | cut -d. -f1)" +%s 2>/dev/null || echo "0")
  local age_seconds=$((now - launch_epoch))
  
  if [[ $age_seconds -lt 300 ]]; then
    info "Instance is new (${age_seconds}s old) - initial deployment"
    echo "initial"
    return
  fi
  
  # Check version marker file via SSM
  info "Checking for existing deployment version..."
  local cmd_id
  cmd_id=$(aws ssm send-command \
    --instance-ids "${instance_id}" \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=["cat /opt/glow/docker-mount-data/.glow-deployment-version 2>/dev/null || echo NONE"]' \
    --query 'Command.CommandId' \
    --output text \
    --region "${AWS_REGION}" 2>/dev/null || echo "")
  
  if [[ -z "$cmd_id" ]]; then
    warn "Could not query instance (SSM not ready yet?)"
    echo "initial"
    return
  fi
  
  # Wait for command to complete
  sleep 5
  
  local version
  version=$(aws ssm get-command-invocation \
    --command-id "${cmd_id}" \
    --instance-id "${instance_id}" \
    --query 'StandardOutputContent' \
    --output text \
    --region "${AWS_REGION}" 2>/dev/null | tr -d '\n' || echo "NONE")
  
  if [[ "$version" == "NONE" ]] || [[ -z "$version" ]]; then
    warn "No deployment version found - treating as initial deployment"
    echo "initial"
  else
    info "Existing deployment found: ${version}"
    echo "update"
  fi
}

# ─── Stream CloudWatch logs ──────────────────────────────────────────────────
stream_activation_logs() {
  local log_group="/aws/ec2/cloud-init"
  
  step "Monitoring activation via CloudWatch logs"
  info "Log group: ${log_group}"
  
  # Wait for log stream to appear (up to 2 minutes)
  local retries=24
  info "Waiting for logs to appear..."
  while ! aws logs describe-log-streams \
    --log-group-name "${log_group}" \
    --max-items 1 \
    --region "${AWS_REGION}" &>/dev/null; do
    retries=$((retries - 1))
    if [[ $retries -eq 0 ]]; then
      warn "CloudWatch logs not available yet"
      warn "User data may still be running in background"
      return 1
    fi
    sleep 5
  done
  
  info "Streaming logs (press Ctrl+C to stop monitoring, deployment continues in background)..."
  echo ""
  
  # Tail logs and look for markers
  # Note: This will run until timeout or user interrupts
  timeout 600 aws logs tail "${log_group}" \
    --follow \
    --format short \
    --region "${AWS_REGION}" 2>/dev/null | while read -r line; do
    echo "$line"
    
    if echo "$line" | grep -q "\[SUCCESS\]"; then
      info "Deployment successful!"
      return 0
    fi
    
    if echo "$line" | grep -q "\[ERROR\]"; then
      error "Deployment failed!"
      return 1
    fi
  done
  
  local tail_exit=$?
  
  if [[ $tail_exit -eq 124 ]]; then
    error "Deployment timed out after 10 minutes"
    return 1
  fi
  
  return 0
}

# ─── Trigger update via SSM ──────────────────────────────────────────────────
trigger_update() {
  local instance_id="$1"
  local git_ref="${2:-}"
  
  step "Triggering stack update via SSM"
  
  local commands="cd /opt/glow && "
  if [[ -n "$git_ref" ]]; then
    commands+="GIT_REF='${git_ref}' "
  fi
  commands+="bash deploy/scripts/update-stack.sh"
  
  info "Running: ${commands}"
  
  local cmd_id
  cmd_id=$(aws ssm send-command \
    --instance-ids "${instance_id}" \
    --document-name "AWS-RunShellScript" \
    --parameters "commands=[\"${commands}\"]" \
    --query 'Command.CommandId' \
    --output text \
    --region "${AWS_REGION}")
  
  info "SSM Command ID: ${cmd_id}"
  info "Monitoring output..."
  
  # Poll for command completion
  local status="InProgress"
  while [[ "$status" == "InProgress" ]] || [[ "$status" == "Pending" ]]; do
    sleep 5
    status=$(aws ssm get-command-invocation \
      --command-id "${cmd_id}" \
      --instance-id "${instance_id}" \
      --query 'Status' \
      --output text \
      --region "${AWS_REGION}" 2>/dev/null || echo "Pending")
    echo -n "."
  done
  echo ""
  
  # Show output
  aws ssm get-command-invocation \
    --command-id "${cmd_id}" \
    --instance-id "${instance_id}" \
    --query 'StandardOutputContent' \
    --output text \
    --region "${AWS_REGION}"
  
  if [[ "$status" == "Success" ]]; then
    info "Update completed successfully"
    return 0
  else
    error "Update failed with status: ${status}"
    aws ssm get-command-invocation \
      --command-id "${cmd_id}" \
      --instance-id "${instance_id}" \
      --query 'StandardErrorContent' \
      --output text \
      --region "${AWS_REGION}"
    return 1
  fi
}

# ─── Handle deployment failure ───────────────────────────────────────────────
handle_failure() {
  local instance_id="$1"
  
  error "Deployment failed or timed out"
  echo ""
  warn "You can:"
  warn "  1. Check logs: aws logs tail /aws/ec2/cloud-init --follow --region ${AWS_REGION}"
  warn "  2. Debug via SSM: aws ssm start-session --target ${instance_id} --region ${AWS_REGION}"
  warn "  3. Destroy and retry"
  echo ""
  
  read -p "Destroy infrastructure and start over? [y/N] " -r
  echo ""
  
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    step "Destroying infrastructure"
    terraform -chdir="${TERRAFORM_DIR}" destroy -auto-approve
    echo ""
    info "Infrastructure destroyed"
    info "Run ./deploy/deploy.sh again to retry deployment"
    exit 1
  else
    info "Leaving resources in place for debugging"
    info "SSM access: aws ssm start-session --target ${instance_id} --region ${AWS_REGION}"
    exit 1
  fi
}

# ─── Main ────────────────────────────────────────────────────────────────────
main() {
  parse_args "$@"

  step "Starting Glow deployment"

  if [[ "${REPLACE}" == "true" ]]; then
    info "Replace mode enabled"
    info "Resource address: ${REPLACE_RESOURCE}"
  fi
  
  check_tools
  
  local account_id
  account_id="$(check_aws_auth)"
  
  # Get domain name from terraform.tfvars
  local domain_name
  domain_name="$(get_domain_from_tfvars)"
  info "Domain: ${domain_name}"
  
  # Check for explicit bucket override
  local override_bucket
  override_bucket="$(get_override_bucket_from_tfvars)"
  
  # Generate S3 bucket name (use override if provided)
  local tfstate_bucket
  if [[ -n "$override_bucket" ]]; then
    tfstate_bucket="$override_bucket"
    info "Using override Terraform state bucket: ${tfstate_bucket}"
  else
    tfstate_bucket="$(generate_bucket_name "${domain_name}")"
    info "Auto-generated Terraform state bucket: ${tfstate_bucket}"
  fi
  
  ensure_backend_bucket "${tfstate_bucket}"
  
  # Run Terraform
  run_terraform "${tfstate_bucket}"
  
  # Get outputs
  local instance_id
  instance_id="$(terraform -chdir="${TERRAFORM_DIR}" output -raw instance_id)"
  
  local domain_name
  domain_name="$(terraform -chdir="${TERRAFORM_DIR}" output -raw domain_name)"
  
  local git_ref
  git_ref="$(terraform -chdir="${TERRAFORM_DIR}" output -raw git_ref 2>/dev/null || echo "")"
  
  # Detect deployment state
  local state
  state=$(get_deployment_state "${instance_id}")
  
  case "$state" in
    initial)
      info "Initial deployment - user_data will run automatically"
      stream_activation_logs || handle_failure "${instance_id}"
      ;;
    update)
      info "Existing deployment detected - triggering update"
      trigger_update "${instance_id}" "${git_ref}" || handle_failure "${instance_id}"
      ;;
    *)
      error "Unknown deployment state: ${state}"
      exit 1
      ;;
  esac
  
  step "Deployment complete!"
  echo ""
  info "Dashboard:   https://${domain_name}"
  info "API:         https://api.${domain_name}"
  info "ODK Central: https://odk.${domain_name}"
  echo ""
  info "SSM access:  aws ssm start-session --target ${instance_id} --region ${AWS_REGION}"
  info "View logs:   aws logs tail /aws/ec2/cloud-init --follow --region ${AWS_REGION}"
  echo ""
  
  # Show DNS setup instructions if needed
  local dns_managed
  dns_managed="$(terraform -chdir="${TERRAFORM_DIR}" output -raw dns_managed 2>/dev/null || echo "true")"
  
  if [[ "${dns_managed}" == "false" ]]; then
    warn "DNS is NOT managed by Route 53 (manage_dns=false)"
    echo ""
    terraform -chdir="${TERRAFORM_DIR}" output -raw dns_setup_instructions
    echo ""
    warn "IMPORTANT: Your services will NOT be accessible until DNS records are created!"
    warn "Copy the instructions above and send them to your domain administrator."
    echo ""
  fi
  
  warn "ODK Central admin credentials are stored on the instance at:"
  warn "  /opt/glow/docker-mount-data/.deploy/.env.admin"
  echo ""
  info "Retrieve with: aws ssm start-session --target ${instance_id} --region ${AWS_REGION}"
}

main "$@"
