#!/usr/bin/env bash
set -euo pipefail

exec > >(tee -a /var/log/glow-runner-bootstrap.log) 2>&1

mkdir -p /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.d
cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.d/glow.json <<EOF
{
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/cloud-init-output.log",
            "log_group_name": "${CLOUDWATCH_BOOTSTRAP_LOG_GROUP}",
            "log_stream_name": "${INSTANCE_ID}/cloud-init-output"
          },
          {
            "file_path": "/var/log/glow-runner-bootstrap.log",
            "log_group_name": "${CLOUDWATCH_BOOTSTRAP_LOG_GROUP}",
            "log_stream_name": "${INSTANCE_ID}/runner-bootstrap"
          },
          {
            "file_path": "/var/log/messages",
            "log_group_name": "${CLOUDWATCH_SYSTEM_LOG_GROUP}",
            "log_stream_name": "${INSTANCE_ID}/messages"
          }
        ]
      }
    }
  }
}
EOF

/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a stop || true
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.d/glow.json \
  -s

if [[ -d /opt/glow-runner ]]; then
  echo "[PROGRESS] dir /opt/glow-runner exists"
else
  echo "[ERROR] could not find /opt/glow-runner"
  exit 101
fi

AWS_REGION="${AWS_REGION:?AWS_REGION is required}"
DOMAIN_NAME="${DOMAIN_NAME:?DOMAIN_NAME is required}"
GIT_REPO_URL="${GIT_REPO_URL:?GIT_REPO_URL is required}"
GIT_CHECKOUT_REF="${GIT_CHECKOUT_REF:?GIT_CHECKOUT_REF is required}"
CLOUDWATCH_BOOTSTRAP_LOG_GROUP="${CLOUDWATCH_BOOTSTRAP_LOG_GROUP:?CLOUDWATCH_BOOTSTRAP_LOG_GROUP is required}"
CLOUDWATCH_SYSTEM_LOG_GROUP="${CLOUDWATCH_SYSTEM_LOG_GROUP:?CLOUDWATCH_SYSTEM_LOG_GROUP is required}"

echo "[PROGRESS] Starting runner bootstrap"
systemctl start docker

TOKEN=$(curl -fsS -X PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
INSTANCE_ID=$(curl -fsS -H "X-aws-ec2-metadata-token: ${TOKEN}" \
  http://169.254.169.254/latest/meta-data/instance-id)

if [[ -d /opt/glow/.git ]]; then
  echo "[PROGRESS] Refreshing existing repository clone"
  git -C /opt/glow fetch --tags --prune origin
else
  echo "[PROGRESS] Cloning repository"
  rm -rf /opt/glow
  git clone "$GIT_REPO_URL" /opt/glow
fi

echo "[PROGRESS] Checking out ${GIT_CHECKOUT_REF}"
git -C /opt/glow fetch --tags --prune origin
git -C /opt/glow checkout --force "$GIT_CHECKOUT_REF"

cat > /etc/glow-runner.env <<EOF
AWS_REGION=${AWS_REGION}
DOMAIN_NAME=${DOMAIN_NAME}
GIT_REPO_URL=${GIT_REPO_URL}
GIT_CHECKOUT_REF=${GIT_CHECKOUT_REF}
EOF

touch /opt/glow-runner/bootstrap.ready
echo "[SUCCESS] Runner bootstrap complete"
