#!/bin/bash
# EC2 User Data - Runs on first boot
# All output captured by cloud-init to /var/log/cloud-init-output.log

set -euo pipefail

# Variables injected by Terraform
DOMAIN_NAME="${domain_name}"
GIT_REPO="${git_repo_url}"
GIT_REF="${git_ref}"

echo "[PROGRESS] Starting EC2 initialization"
echo "[INFO] Domain: $DOMAIN_NAME"
echo "[INFO] Git repo: $GIT_REPO"
echo "[INFO] Git ref: $${GIT_REF:-latest release}"

# Install git
echo "[PROGRESS] Installing git"
yum install -y git

# Clone repository
echo "[PROGRESS] Cloning repository"
git clone "$GIT_REPO" /opt/glow
cd /opt/glow

# Determine ref to checkout
if [ -z "$GIT_REF" ]; then
  # Find latest release tag
  git fetch --tags
  GIT_REF=$(git describe --tags $(git rev-list --tags --max-count=1) 2>/dev/null || echo "main")
  echo "[PROGRESS] Auto-detected ref: $GIT_REF"
else
  echo "[PROGRESS] Using specified ref: $GIT_REF"
fi

# Validate and checkout
if ! git rev-parse --verify "$GIT_REF" >/dev/null 2>&1; then
  echo "[ERROR] Invalid git ref: $GIT_REF"
  exit 1
fi

git checkout "$GIT_REF"
echo "[INFO] Checked out: $(git rev-parse HEAD)"

# Run activation script
echo "[PROGRESS] Running activation script"
export DOMAIN_NAME
bash deploy/scripts/activate-stack.sh

# Note: activate-stack.sh will output [SUCCESS] or [ERROR] marker
