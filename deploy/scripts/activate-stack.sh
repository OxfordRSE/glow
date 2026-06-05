#!/usr/bin/env bash
# activate-stack.sh — Runtime activation script
# 
# This script runs on EC2 or self-hosted VM to:
#   1. Install Docker and Docker Compose
#   2. Mount data volume (EC2 only)
#   3. Set up data directory structure
#   4. Start the docker-compose stack (Glow + ODK Central)
#   5. Configure ODK Central admin user
#   6. Create ODK API integration user with read-only access
#   7. Store credentials for API container to consume
#
# Environment variables expected:
#   DOMAIN_NAME - root domain (e.g., glow.example.com)

set -euo pipefail

# ─── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; RESET='\033[0m'
info()  { echo -e "${GREEN}[INFO]${RESET}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error() { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
step()  { echo -e "\n${BLUE}▶${RESET} $*\n"; }

DOMAIN_NAME="${DOMAIN_NAME:?DOMAIN_NAME environment variable required}"
WORK_DIR="/opt/glow"
DEPLOY_DIR="${WORK_DIR}/deploy"
DATA_DIR="${WORK_DIR}/docker-mount-data"
ADMIN_ENV="${DATA_DIR}/.deploy/.env.admin"
RUNTIME_ENV="${DATA_DIR}/.deploy/share/.env.runtime"
FORMS_STATE="${DATA_DIR}/.deploy/share/odk-forms-state.json"
SCRIPTS_DIR="${DEPLOY_DIR}/scripts"
FORMS_DIR="${WORK_DIR}/odk-forms"

cd "${WORK_DIR}"

# Source ODK API helper functions
source "${SCRIPTS_DIR}/odk-api-helper.sh"

# ─── Environment Detection ───────────────────────────────────────────────────
detect_environment() {
  if curl -s -f -m 1 http://169.254.169.254/latest/meta-data/instance-id &>/dev/null 2>&1; then
    echo "ec2"
  else
    echo "vm"
  fi
}

# ─── OS-Aware Docker Installation ────────────────────────────────────────────
install_docker() {
  if command -v docker &>/dev/null; then
    info "Docker already installed: $(docker --version)"
    return
  fi
  
  step "Installing Docker"
  
  if [ -f /etc/os-release ]; then
    . /etc/os-release
    case "$ID" in
      amzn|amazonlinux)
        sudo yum update -y
        sudo yum install -y docker
        sudo systemctl enable docker
        sudo systemctl start docker
        sudo usermod -aG docker "${USER}"
        ;;
      ubuntu|debian)
        sudo apt-get update
        sudo apt-get install -y docker.io docker-compose-plugin
        sudo systemctl enable docker
        sudo systemctl start docker
        sudo usermod -aG docker "${USER}"
        ;;
      *)
        error "Unsupported OS: $ID"
        error "Please install Docker manually: https://docs.docker.com/engine/install/"
        exit 1
        ;;
    esac
  else
    error "Cannot detect OS (/etc/os-release not found)"
    exit 1
  fi
  
  info "Docker installed"
}

# ─── EBS Volume Mounting (EC2 only) ──────────────────────────────────────────
mount_data_volume() {
  local env_type
  env_type=$(detect_environment)
  
  if [[ "$env_type" != "ec2" ]]; then
    info "Not on EC2, skipping EBS volume mount"
    return
  fi
  
  step "Mounting EBS data volume"
  
  # Check if /data is already mounted
  if mountpoint -q /data 2>/dev/null; then
    info "/data already mounted"
    return
  fi
  
  # Wait for device to be available (can take a few seconds)
  local retries=10
  while [ ! -e /dev/xvdf ] && [ $retries -gt 0 ]; do
    info "Waiting for /dev/xvdf to be available..."
    sleep 2
    retries=$((retries - 1))
  done
  
  if [ ! -e /dev/xvdf ]; then
    error "/dev/xvdf not found - EBS volume not attached"
    exit 1
  fi
  
  # Check if /dev/xvdf has a filesystem
  if ! sudo file -s /dev/xvdf | grep -q filesystem; then
    info "Formatting /dev/xvdf as ext4"
    sudo mkfs.ext4 -F /dev/xvdf
  else
    info "Existing filesystem found on /dev/xvdf"
  fi
  
  # Create mount point and mount
  sudo mkdir -p /data
  sudo mount /dev/xvdf /data
  
  # Add to fstab if not present (for reboots)
  if ! grep -q "/dev/xvdf" /etc/fstab 2>/dev/null; then
    echo "/dev/xvdf /data ext4 defaults,nofail 0 2" | sudo tee -a /etc/fstab
  fi
  
  # Set ownership
  sudo chown -R "${USER}:${USER}" /data
  
  info "EBS volume mounted at /data"
}

# ─── Data Directory Setup ────────────────────────────────────────────────────
setup_data_directory() {
  local env_type
  env_type=$(detect_environment)
  
  step "Setting up data directory"
  
  cd "${WORK_DIR}"
  
  if [[ "$env_type" == "ec2" ]]; then
    # On EC2: symlink ./docker-mount-data → /data
    if [[ -L "docker-mount-data" ]]; then
      info "docker-mount-data symlink already exists"
    elif [[ -d "docker-mount-data" ]]; then
      warn "docker-mount-data is a directory, converting to symlink"
      sudo rm -rf docker-mount-data
      ln -s /data docker-mount-data
    else
      info "Creating symlink: docker-mount-data → /data"
      ln -s /data docker-mount-data
    fi
  else
    # On VM: create local directory
    if [[ ! -d "docker-mount-data" ]]; then
      info "Creating local data directory: docker-mount-data"
      mkdir -p docker-mount-data
    fi
  fi
  
  # Create subdirectories for all services
  mkdir -p docker-mount-data/{glow-postgres,odk-postgres,odk-transfer,odk-secrets,odk-enketo-redis-main,odk-enketo-redis-cache}
  
  # Also create .deploy directories in the data dir
  mkdir -p docker-mount-data/.deploy/share
  
  info "Data directory ready: ${WORK_DIR}/docker-mount-data"
}

# ─── Version Validation ──────────────────────────────────────────────────────
validate_deployment_version() {
  local version_file="${WORK_DIR}/docker-mount-data/.glow-deployment-version"
  local current_version
  
  # Get current version from git
  cd "${WORK_DIR}"
  current_version=$(git describe --tags --exact-match 2>/dev/null || git describe --tags 2>/dev/null || echo "dev-$(git rev-parse --short HEAD)")
  
  info "Current deployment version: ${current_version}"
  
  if [[ ! -f "$version_file" ]]; then
    info "No previous deployment found (initial deployment)"
    echo "[PROGRESS] Initial deployment of ${current_version}"
    return 0
  fi
  
  local previous_version
  previous_version=$(cat "$version_file")
  
  info "Previous deployment version: ${previous_version}"
  echo "[PROGRESS] Upgrading from ${previous_version} to ${current_version}"
  
  # Extract major versions (handle v1.2.3 or 1.2.3 format)
  local prev_major
  local curr_major
  prev_major=$(echo "$previous_version" | sed -E 's/^v?([0-9]+)\..*/\1/' | grep -E '^[0-9]+$' || echo "0")
  curr_major=$(echo "$current_version" | sed -E 's/^v?([0-9]+)\..*/\1/' | grep -E '^[0-9]+$' || echo "0")
  
  if [[ "$curr_major" -gt "$prev_major" ]] && [[ "$prev_major" != "0" ]]; then
    echo "[ERROR] Major version upgrade detected: ${previous_version} → ${current_version}"
    error "Major version upgrades require manual migration steps."
    error "Please consult the upgrade guide before proceeding."
    error ""
    error "Upgrade guide: https://github.com/OxfordRSE/glow/blob/main/UPGRADING.md"
    error ""
    error "To force upgrade (NOT RECOMMENDED), remove: ${version_file}"
    exit 1
  fi
  
  if [[ "$curr_major" -lt "$prev_major" ]] && [[ "$curr_major" != "0" ]]; then
    warn "Downgrading major version: ${previous_version} → ${current_version}"
    warn "This may cause data compatibility issues!"
  fi
  
  info "Version upgrade path validated"
}

# ─── Write Deployment Version ────────────────────────────────────────────────
write_deployment_version() {
  local version_file="${WORK_DIR}/docker-mount-data/.glow-deployment-version"
  local current_version
  
  cd "${WORK_DIR}"
  current_version=$(git describe --tags --exact-match 2>/dev/null || git describe --tags 2>/dev/null || echo "dev-$(git rev-parse --short HEAD)")
  
  echo "$current_version" > "$version_file"
  info "Deployment version written: ${current_version}"
}

# ─── Install Docker ──────────────────────────────────────────────────────────
# (Function defined above in OS-Aware Docker Installation section)

# ─── Install Docker Compose ──────────────────────────────────────────────────
install_compose() {
  if docker compose version &>/dev/null; then
    info "Docker Compose already installed: $(docker compose version)"
    return
  fi
  
  step "Installing Docker Compose plugin"
  COMPOSE_VERSION="v2.24.5"
  sudo mkdir -p /usr/local/lib/docker/cli-plugins
  sudo curl -SL "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-x86_64" \
    -o /usr/local/lib/docker/cli-plugins/docker-compose
  sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
  
  info "Docker Compose installed"
}

# ─── Generate runtime environment ────────────────────────────────────────────
generate_runtime_env() {
  step "Generating runtime environment"
  
  # Create deploy directories
  mkdir -p "$(dirname "${ADMIN_ENV}")" "$(dirname "${RUNTIME_ENV}")"
  
  # Generate secrets
  local glow_secret
  glow_secret="$(openssl rand -base64 32 | tr -d '\n')"
  
  local postgres_password
  postgres_password="$(openssl rand -base64 32 | tr -d '\n')"
  
  local odk_postgres_password
  odk_postgres_password="$(openssl rand -base64 32 | tr -d '\n')"
  
  local odk_admin_password
  odk_admin_password="$(openssl rand -base64 64 | tr -d '\n')"
  
  local odk_api_password
  odk_api_password="$(openssl rand -base64 24 | tr -d '\n')"
  
  # Create base .env from example
  cp .env.example .env
  
  # Create admin credentials file (host-only, never loaded by containers)
  local admin_email="glow-admin@${DOMAIN_NAME}"
  cat > "${ADMIN_ENV}" <<EOF
# ODK Admin Credentials (host-only access, NOT loaded by containers)
# Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)
ODK_ADMIN_EMAIL=${admin_email}
ODK_ADMIN_PASSWORD=${odk_admin_password}
EOF
  chmod 600 "${ADMIN_ENV}"
  
  # Create runtime env with generated secrets (loaded by containers)
  local api_user_email="glow-api@${DOMAIN_NAME}"
  cat > "${RUNTIME_ENV}" <<EOF
# Auto-generated runtime secrets - $(date -u +%Y-%m-%dT%H:%M:%SZ)
# Loaded by containers via env_file

# Glow API
GLOW_SECRET_KEY=${glow_secret}
GLOW_MIN_N=5
GLOW_ODK_API_URL=http://odk-service:8383
GLOW_ODK_API_EMAIL=${api_user_email}
GLOW_ODK_API_PASSWORD=${odk_api_password}
GLOW_ODK_PROJECT_ID=1
GLOW_ODK_FORM_ID=bewell_questionnaire
GLOW_DATA_CACHE_PATH=.cache.parquet
GLOW_DATA_REFRESH_HOURS=1
GLOW_METADATA_DATABASE_URL=postgresql+psycopg://glow:${postgres_password}@api-db:5432/glow
GLOW_CORS_ORIGINS=["https://${DOMAIN_NAME}","https://api.${DOMAIN_NAME}"]

# Dashboard
PUBLIC_API_BASE=https://api.${DOMAIN_NAME}

# Postgres
POSTGRES_DB=glow
POSTGRES_USER=glow
POSTGRES_PASSWORD=${postgres_password}

# ODK Central
ODK_DOMAIN=odk.${DOMAIN_NAME}
ODK_SYSADMIN_EMAIL=admin@${DOMAIN_NAME}
ODK_SSL_TYPE=upstream
ODK_HTTP_PORT=8080
ODK_HTTPS_PORT=8443

# ODK Postgres
ODK_POSTGRES_DB=odk
ODK_POSTGRES_USER=odk
ODK_POSTGRES_PASSWORD=${odk_postgres_password}

# ODK Central version
ODK_CENTRAL_TAG=v2026.1.2

# ODK API Integration User (glow-api@<domain>)
ODK_API_EMAIL=${api_user_email}
ODK_API_PASSWORD=${odk_api_password}
ODK_API_URL=https://odk.${DOMAIN_NAME}
EOF

  chmod 600 "${RUNTIME_ENV}"
  
  # Initialize empty forms state file
  echo '{}' > "${FORMS_STATE}"
  chmod 600 "${FORMS_STATE}"
  
  info "Runtime environment generated:"
  info "  Admin credentials: ${ADMIN_ENV}"
  info "  Runtime environment: ${RUNTIME_ENV}"
  info "  Forms state: ${FORMS_STATE}"
}

# ─── Start docker-compose stack ──────────────────────────────────────────────
start_stack() {
  step "Starting docker-compose stack"
  
  # Use sudo until user re-login adds them to docker group
  sudo docker compose --env-file "${RUNTIME_ENV}" pull
  sudo docker compose --env-file "${RUNTIME_ENV}" build
  sudo docker compose --env-file "${RUNTIME_ENV}" up -d
  
  info "Waiting for services to start..."
  sleep 60
  
  # Show status
  sudo docker compose --env-file "${RUNTIME_ENV}" ps
}

# ─── Wait for ODK service to be ready ────────────────────────────────────────
wait_for_odk() {
  step "Waiting for ODK Central service to be ready"

  local retries=30
  while ! sudo docker compose --env-file "${RUNTIME_ENV}" exec -T service \
    curl -sf http://localhost:8383 &>/dev/null; do
    retries=$((retries - 1))
    if [[ $retries -eq 0 ]]; then
      error "ODK Central service failed to start after "
      sudo docker compose --env-file "${RUNTIME_ENV}" logs service
      exit 1
    fi
    sleep 10
  done
  
  info "ODK Central service is ready"
}

# ─── Configure ODK Central ───────────────────────────────────────────────────
configure_odk() {
  step "Configuring ODK Central"

  source "${ADMIN_ENV}"
  source "${RUNTIME_ENV}"
  
  local admin_email="${ODK_ADMIN_EMAIL}"
  local admin_password="${ODK_ADMIN_PASSWORD}"
  local api_email="${ODK_API_EMAIL}"
  local api_password="${ODK_API_PASSWORD}"
  
  # Step 1: Create admin user via CLI
  info "Creating ODK admin user: ${admin_email}"
  sudo docker compose --env-file "${RUNTIME_ENV}" --profile odk exec -T service \
    node /usr/odk/lib/bin/cli.js user-create "${admin_email}" "${admin_password}" || {
    info "Admin user already exists (this is expected on re-run)"
  }
  
  # Step 2: Promote admin to site administrator
  info "Promoting admin to site administrator"
  sudo docker compose --env-file "${RUNTIME_ENV}" --profile odk exec -T service \
    node /usr/odk/lib/bin/cli.js user-promote "${admin_email}" || {
    info "Admin already promoted (this is expected on re-run)"
  }
  
  # Step 3: Authenticate as admin to get session token
  info "Authenticating as admin via HTTP API"
  local admin_token
  admin_token=$(odk_login "${admin_email}" "${admin_password}") || {
    error "Failed to authenticate as admin"
    return 1
  }
  
  # Step 4: Create default project
  local project_name="GLOW Data Collection"
  info "Creating project: ${project_name}"
  local project_id
  project_id=$(odk_create_project "${project_name}" "${admin_token}") || {
    error "Failed to create project"
    return 1
  }
  
  # Step 5: Create API user
  info "Creating API user: ${api_email}"
  local api_actor_id
  api_actor_id=$(odk_create_user "${api_email}" "${api_password}" "${admin_token}") || {
    error "Failed to create API user"
    return 1
  }
  
  # Step 6: Assign viewer role (roleId=2) to API user on project
  info "Assigning viewer role to API user on project"
  odk_assign_role "${project_id}" "${api_actor_id}" "2" "${admin_token}" || {
    error "Failed to assign role to API user"
    return 1
  }
  
  info "ODK Central configuration complete"
  info "  Project: ${project_name} (ID: ${project_id})"
  info "  Admin: ${admin_email} (stored in ${ADMIN_ENV})"
  info "  API User: ${api_email} (stored in ${RUNTIME_ENV})"
}

# ─── Process and upload ODK forms ────────────────────────────────────────────
process_forms() {
  step "Processing ODK forms"
  
  if [[ ! -d "${FORMS_DIR}" ]]; then
    info "No forms directory found at ${FORMS_DIR}, skipping form upload"
    return 0
  fi
  
  # Count forms
  local form_count
  form_count=$(find "${FORMS_DIR}" -type f \( -name "*.xml" -o -name "*.xlsx" -o -name "*.xls" \) | wc -l)
  
  if [[ $form_count -eq 0 ]]; then
    info "No forms found in ${FORMS_DIR}, skipping form upload"
    return 0
  fi
  
  info "Found ${form_count} form(s) in ${FORMS_DIR}"
  
  source "${ADMIN_ENV}"
  source "${RUNTIME_ENV}"
  
  local admin_email="${ODK_ADMIN_EMAIL}"
  local admin_password="${ODK_ADMIN_PASSWORD}"
  
  # Authenticate
  local admin_token
  admin_token=$(odk_login "${admin_email}" "${admin_password}") || {
    error "Failed to authenticate for form upload"
    return 1
  }
  
  # Get project ID
  local project_name="GLOW Data Collection"
  local project_id
  project_id=$(odk_get_project_by_name "${project_name}" "${admin_token}") || {
    error "Failed to get project ID"
    return 1
  }
  
  # Load existing forms state
  local forms_state
  if [[ -f "${FORMS_STATE}" ]]; then
    forms_state=$(cat "${FORMS_STATE}")
  else
    forms_state='{}'
  fi
  
  # Track upload results
  local uploaded=0
  local skipped=0
  local failed=0
  local failed_list=()
  
  # Process each form file
  while IFS= read -r -d '' form_file; do
    local filename
    filename=$(basename "$form_file")
    info "Processing: ${filename}"
    
    local xml_content
    local xmlformid
    
    # Convert XLSForm to XML if needed
    if [[ "$form_file" == *.xls || "$form_file" == *.xlsx ]]; then
      info "  Converting XLSForm to XML..."
      xml_content=$(convert_xlsform_to_xml "$form_file") || {
        odk_warn "  Failed to convert XLSForm: ${filename}"
        ((failed++))
        failed_list+=("${filename} (conversion failed)")
        continue
      }
    else
      # Already XML
      xml_content=$(cat "$form_file")
    fi
    
    # Extract xmlFormId
    xmlformid=$(extract_xmlformid_from_xml "$xml_content") || {
      odk_warn "  Failed to extract xmlFormId from: ${filename}"
      ((failed++))
      failed_list+=("${filename} (no xmlFormId)")
      continue
    }
    
    # Calculate hash
    local current_hash
    current_hash=$(echo -n "$xml_content" | sha256sum | cut -d' ' -f1)
    
    # Check if form changed
    local stored_hash
    stored_hash=$(echo "$forms_state" | jq -r --arg id "$xmlformid" '.[$id].hash // empty')
    
    if [[ "$current_hash" == "$stored_hash" ]]; then
      info "  Skipping ${xmlformid} (unchanged)"
      ((skipped++))
      continue
    fi
    
    # Upload form (retry 3x)
    local upload_success=0
    for attempt in 1 2 3; do
      if odk_upload_form "${project_id}" "$xml_content" "${admin_token}" &>/dev/null; then
        upload_success=1
        break
      fi
      odk_warn "  Upload attempt ${attempt}/3 failed for ${xmlformid}"
      sleep 2
    done
    
    if [[ $upload_success -eq 1 ]]; then
      info "  Uploaded ${xmlformid}"
      ((uploaded++))
      
      # Update state
      forms_state=$(echo "$forms_state" | jq \
        --arg id "$xmlformid" \
        --arg hash "$current_hash" \
        --arg filename "$filename" \
        --arg uploaded "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        '.[$id] = {hash: $hash, filename: $filename, uploaded: $uploaded}')
    else
      odk_warn "  Failed to upload ${xmlformid} after 3 attempts"
      ((failed++))
      failed_list+=("${filename} (upload failed)")
    fi
    
  done < <(find "${FORMS_DIR}" -type f \( -name "*.xml" -o -name "*.xlsx" -o -name "*.xls" \) -print0)
  
  # Save updated state
  echo "$forms_state" > "${FORMS_STATE}"
  
  # Summary
  step "Form upload summary"
  info "  Uploaded: ${uploaded}"
  info "  Skipped (unchanged): ${skipped}"
  info "  Failed: ${failed}"
  
  if [[ ${#failed_list[@]} -gt 0 ]]; then
    warn "Failed forms:"
    for failed_form in "${failed_list[@]}"; do
      warn "  - ${failed_form}"
    done
  fi
}

# ─── Restart API to pick up ODK credentials ──────────────────────────────────
restart_api() {
  step "Restarting API container with ODK credentials"
  
  sudo docker compose --env-file "${RUNTIME_ENV}" up -d --force-recreate api
  
  info "API restarted with ODK integration credentials"
}

# ─── Health checks ───────────────────────────────────────────────────────────
verify_stack() {
  step "Verifying stack health"
  
  # Check docker containers
  info "Container status:"
  sudo docker compose --env-file "${RUNTIME_ENV}" ps
  
  # Check API health
  if sudo docker compose --env-file "${RUNTIME_ENV}" exec -T api \
    curl -sf http://localhost:8000/health &>/dev/null; then
    info "✓ API health check passed"
  else
    warn "✗ API health check failed"
  fi
  
  # Check dashboard
  if sudo docker compose --env-file "${RUNTIME_ENV}" exec -T dashboard \
    curl -sf http://localhost:3000 &>/dev/null; then
    info "✓ Dashboard health check passed"
  else
    warn "✗ Dashboard health check failed"
  fi
  
  # Check ODK nginx
  if sudo docker compose --env-file "${RUNTIME_ENV}" --profile odk exec -T nginx \
    curl -sf http://localhost &>/dev/null; then
    info "✓ ODK Central health check passed"
  else
    warn "✗ ODK Central health check failed"
  fi
}

# ─── Main ────────────────────────────────────────────────────────────────────
main() {
  info "Starting stack activation for domain: ${DOMAIN_NAME}"
  
  # Environment setup
  mount_data_volume         # EC2 only: mount /dev/xvdf to /data
  setup_data_directory      # Create docker-mount-data (symlink or dir)
  validate_deployment_version  # Check for major version upgrades
  
  install_docker
  install_compose
  
  # Only generate if not already present (idempotent)
  if [[ ! -f "${RUNTIME_ENV}" ]]; then
    generate_runtime_env
  else
    info "Runtime environment already exists: ${RUNTIME_ENV}"
  fi
  
  start_stack
  wait_for_odk
  configure_odk
  process_forms
  restart_api
  verify_stack
  
  # Write version marker on success
  write_deployment_version
  
  echo "[SUCCESS] Stack activation complete!"
  echo ""
  info "Services are running with docker-compose"
  info "View logs: cd ${WORK_DIR} && sudo docker compose logs -f"
  info "Admin credentials: ${ADMIN_ENV}"
  info "Runtime environment: ${RUNTIME_ENV}"
  echo ""
}

main "$@"
