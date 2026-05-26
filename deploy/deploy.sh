#!/usr/bin/env bash
# deploy.sh — Single-command deployment for Glow infrastructure
# Usage: ./deploy/deploy.sh
#
# Prerequisites:
#   - aws CLI configured
#   - terraform installed
#   - SSH key pair created in AWS (specified in terraform.tfvars)
#
# This script:
#   1. Creates S3 bucket for Terraform state (if needed)
#   2. Runs terraform init + apply
#   3. Uploads compose files and activation script to EC2
#   4. Runs remote activation to start stack + configure ODK integration

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "${SCRIPT_DIR}")"
TERRAFORM_DIR="${SCRIPT_DIR}/terraform"
APP_NAME="glow-core"
AWS_REGION="${AWS_REGION:-eu-west-2}"

# ─── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; RESET='\033[0m'
info()  { echo -e "${GREEN}[INFO]${RESET}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error() { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
step()  { echo -e "\n${BLUE}▶${RESET} $*\n"; }

# ─── Check tools ─────────────────────────────────────────────────────────────
check_tools() {
  local missing=()
  for tool in aws terraform ssh scp; do
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
  
  step "Initializing Terraform"
  terraform -chdir="${TERRAFORM_DIR}" init \
    -backend-config="bucket=${bucket}" \
    -backend-config="region=${AWS_REGION}" \
    -reconfigure
  
  step "Running Terraform plan"
  terraform -chdir="${TERRAFORM_DIR}" plan
  
  echo ""
  read -p "Apply these changes? [y/N] " -n 1 -r
  echo ""
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    warn "Deployment cancelled"
    exit 0
  fi
  
  step "Applying Terraform configuration"
  terraform -chdir="${TERRAFORM_DIR}" apply -auto-approve
}

# ─── Upload and activate on EC2 ──────────────────────────────────────────────
activate_ec2_stack() {
  local ssh_key="$1"
  local ec2_ip="$2"
  local domain="$3"
  
  step "Uploading compose files and activation script to EC2"
  
  # Wait for EC2 SSH to be ready
  info "Waiting for SSH to be ready on ${ec2_ip}..."
  local retries=30
  while ! ssh -i "${ssh_key}" -o ConnectTimeout=5 -o StrictHostKeyChecking=no \
    ec2-user@"${ec2_ip}" "echo ok" &>/dev/null; do
    retries=$((retries - 1))
    if [[ $retries -eq 0 ]]; then
      error "SSH connection timed out"
      exit 1
    fi
    sleep 10
  done
  info "SSH ready"
  
  # Create remote directories
  ssh -i "${ssh_key}" -o StrictHostKeyChecking=no ec2-user@"${ec2_ip}" \
    "sudo mkdir -p /opt/glow/deploy/scripts && sudo chown -R ec2-user:ec2-user /opt/glow"
  
  # Upload compose files
  scp -i "${ssh_key}" -o StrictHostKeyChecking=no \
    "${REPO_ROOT}/compose.yml" \
    "${REPO_ROOT}/compose.override.yml" \
    "${REPO_ROOT}/.env.example" \
    ec2-user@"${ec2_ip}":/opt/glow/
  
  # Upload ODK Central configs
  scp -i "${ssh_key}" -o StrictHostKeyChecking=no -r \
    "${REPO_ROOT}/odk-central" \
    ec2-user@"${ec2_ip}":/opt/glow/
  
  # Upload activation script
  scp -i "${ssh_key}" -o StrictHostKeyChecking=no \
    "${SCRIPT_DIR}/scripts/activate-stack.sh" \
    ec2-user@"${ec2_ip}":/opt/glow/deploy/scripts/
  
  step "Running activation script on EC2"
  ssh -i "${ssh_key}" -o StrictHostKeyChecking=no ec2-user@"${ec2_ip}" \
    "cd /opt/glow && DOMAIN_NAME=${domain} bash deploy/scripts/activate-stack.sh"
  
  info "Stack activation complete"
}

# ─── Main ────────────────────────────────────────────────────────────────────
main() {
  step "Starting Glow deployment"
  
  check_tools
  
  local account_id
  account_id="$(check_aws_auth)"
  
  # S3 bucket for Terraform state (account-unique)
  local tfstate_bucket="${APP_NAME}-tfstate-${account_id}"
  ensure_backend_bucket "${tfstate_bucket}"
  
  # Run Terraform
  run_terraform "${tfstate_bucket}"
  
  # Extract outputs
  local ec2_ip
  ec2_ip="$(terraform -chdir="${TERRAFORM_DIR}" output -raw ec2_public_ip)"
  
  local ssh_key_name
  ssh_key_name="$(terraform -chdir="${TERRAFORM_DIR}" output -raw ssh_key_name)"
  
  local domain_name
  domain_name="$(terraform -chdir="${TERRAFORM_DIR}" output -raw domain_name)"
  
  # Construct SSH key path (assumes default location)
  local ssh_key="${HOME}/.ssh/${ssh_key_name}.pem"
  if [[ ! -f "${ssh_key}" ]]; then
    ssh_key="${HOME}/.ssh/${ssh_key_name}"
    if [[ ! -f "${ssh_key}" ]]; then
      error "SSH key not found: ${ssh_key_name}"
      error "Expected at: ${HOME}/.ssh/${ssh_key_name}.pem or ${HOME}/.ssh/${ssh_key_name}"
      exit 1
    fi
  fi
  
  # Upload and activate
  activate_ec2_stack "${ssh_key}" "${ec2_ip}" "${domain_name}"
  
  step "Deployment complete!"
  echo ""
  info "Dashboard:   https://${domain_name}"
  info "API:         https://api.${domain_name}"
  info "ODK Central: https://odk.${domain_name}"
  echo ""
  info "SSH access:  ssh -i ${ssh_key} ec2-user@${ec2_ip}"
  echo ""
  
  # Show DNS setup instructions if DNS is not managed by Route 53
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
    
    # Show certificate validation command
    local cert_status_cmd
    cert_status_cmd="$(terraform -chdir="${TERRAFORM_DIR}" output -raw acm_validation_status_command 2>/dev/null || echo "")"
    if [[ -n "${cert_status_cmd}" ]]; then
      info "Check certificate validation status with:"
      echo "  ${cert_status_cmd}"
      echo ""
    fi
  else
    info "DNS records created in Route 53"
    info "Certificate validation may take 10-30 minutes"
    echo ""
  fi
  warn "ODK Central admin credentials are in /opt/glow/.env.runtime on the EC2 instance"
  warn "Retrieve with: ssh -i ${ssh_key} ec2-user@${ec2_ip} 'cat /opt/glow/.env.runtime'"
}

main "$@"
