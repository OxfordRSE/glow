#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[runner-deps] %s\n' "$*" >&2
}

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  log "this script must run as root"
  exit 1
fi

log "updating system packages"
dnf update -y

log "installing base dependencies"
dnf install -y \
  awscli \
  docker \
  git \
  jq \
  amazon-cloudwatch-agent \
  amazon-ssm-agent

dnf clean all

log "enabling and starting amazon-ssm-agent"
systemctl enable amazon-ssm-agent
systemctl restart amazon-ssm-agent

log "verifying amazon-ssm-agent"
systemctl is-active --quiet amazon-ssm-agent

log "enabling and starting docker"
systemctl enable docker
systemctl start docker

log "ensuring docker group exists"
if ! getent group docker >/dev/null 2>&1; then
  groupadd docker
fi

log "adding ec2-user to docker group"
if id ec2-user >/dev/null 2>&1; then
  usermod -aG docker ec2-user
fi

log "installing docker compose plugin"
mkdir -p /usr/local/lib/docker/cli-plugins

compose_plugin="/usr/local/lib/docker/cli-plugins/docker-compose"

# Prefer a repo package if it is available, otherwise install the plugin binary
# directly from Docker's release channel.
if dnf list --available docker-compose-plugin >/dev/null 2>&1; then
  dnf install -y docker-compose-plugin
else
  arch="$(uname -m)"
  case "$arch" in
    x86_64) compose_arch="x86_64" ;;
    aarch64) compose_arch="aarch64" ;;
    *)
      log "unsupported architecture for docker compose plugin: $arch"
      exit 1
      ;;
  esac

  compose_url="${DOCKER_COMPOSE_URL:-https://github.com/docker/compose/releases/latest/download/docker-compose-linux-${compose_arch}}"
  curl -fsSL "$compose_url" -o "$compose_plugin"
  chmod 0755 "$compose_plugin"
fi

log "verifying docker installation"
docker --version
docker compose version

log "runner dependencies installed"

log "enabling cloudwatch logging for cloud init"
systemctl enable amazon-cloudwatch-agent

sudo mkdir -p /opt/aws/amazon-cloudwatch-agent/etc

sudo tee /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.d/init.json >/dev/null <<'EOF'
{
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/cloud-init.log",
            "log_group_name": "/debug/glow/cloud-init",
            "log_stream_name": "{instance_id}",
            "timezone": "UTC"
          }
        ]
      }
    }
  }
}
EOF

sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -s \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.d/init.json

mkdir -p /opt/glow-runner
