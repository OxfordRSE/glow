#!/usr/bin/env bash
set -euo pipefail

echo "[PROGRESS] Start bootstrap"

touch /opt/glow-runner/bootstrap.start
exec > >(tee -a /var/log/glow-runner-bootstrap.log) 2>&1

echo "[PROGRESS] Configure env"

cloud_init_config=/opt/aws/amazon-cloudwatch-agent/etc/cloud_init.json
cloud_glow_config=/opt/aws/amazon-cloudwatch-agent/etc/glow.json

AWS_REGION="${AWS_REGION:?AWS_REGION is required}"
DOMAIN_NAME="${DOMAIN_NAME:?DOMAIN_NAME is required}"
GIT_REPO_URL="${GIT_REPO_URL:?GIT_REPO_URL is required}"
GIT_CHECKOUT_REF="${GIT_CHECKOUT_REF:?GIT_CHECKOUT_REF is required}"
CLOUDWATCH_BOOTSTRAP_LOG_GROUP="${CLOUDWATCH_BOOTSTRAP_LOG_GROUP:?CLOUDWATCH_BOOTSTRAP_LOG_GROUP is required}"
CLOUDWATCH_CONTAINERS_LOG_GROUP="${CLOUDWATCH_CONTAINERS_LOG_GROUP:?CLOUDWATCH_CONTAINERS_LOG_GROUP is required}"
CLOUDWATCH_SYSTEM_LOG_GROUP="${CLOUDWATCH_SYSTEM_LOG_GROUP:?CLOUDWATCH_SYSTEM_LOG_GROUP is required}"

touch /opt/glow-runner/bootstrap.loadenv

TOKEN=$(curl -fsS -X PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
INSTANCE_ID=$(curl -fsS -H "X-aws-ec2-metadata-token: ${TOKEN}" \
  http://169.254.169.254/latest/meta-data/instance-id)

touch /opt/glow-runner/bootstrap.fetchenv

echo "[PROGRESS] Set up cloudwatch"

cat > ${cloud_glow_config} <<EOF
{
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
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
  -s \
  -c "file:${cloud_init_config}"
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a append-config \
  -m ec2 \
  -c file:${cloud_glow_config}

touch /opt/glow-runner/bootstrap.conflog

echo "[PROGRESS] Configure docker logging"

mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<EOF
{
  "log-driver": "awslogs",
  "log-opts": {
    "awslogs-region": "${AWS_REGION}",
    "awslogs-group": "${CLOUDWATCH_CONTAINERS_LOG_GROUP}",
    "awslogs-create-group": "false",
    "tag": "${INSTANCE_ID}-{{.Name}}"
  }
}
EOF

if [[ -d /opt/glow-runner ]]; then
  echo "[PROGRESS] dir /opt/glow-runner exists"
else
  echo "[ERROR] could not find /opt/glow-runner"
  exit 101
fi

echo "[PROGRESS] Restart docker service"
systemctl restart docker

touch /opt/glow-runner/bootstrap.dockerready

if [[ -d /opt/glow/.git ]]; then
  echo "[PROGRESS] Refreshing existing repository clone"
  git -C /opt/glow fetch --tags --prune origin
else
  echo "[PROGRESS] Cloning repository"
  rm -rf /opt/glow
  git clone "$GIT_REPO_URL" /opt/glow
fi

touch /opt/glow-runner/bootstrap.gitpull

echo "[PROGRESS] Checking out ${GIT_CHECKOUT_REF}"
git -C /opt/glow fetch --tags --prune origin
git -C /opt/glow checkout --force "$GIT_CHECKOUT_REF"

touch /opt/glow-runner/bootstrap.checkout

echo "[PROGRESS] Write /etc/glow-runner.env"

cat > /etc/glow-runner.env <<EOF
AWS_REGION=${AWS_REGION}
DOMAIN_NAME=${DOMAIN_NAME}
GIT_REPO_URL=${GIT_REPO_URL}
GIT_CHECKOUT_REF=${GIT_CHECKOUT_REF}
CLOUDWATCH_CONTAINERS_LOG_GROUP=${CLOUDWATCH_CONTAINERS_LOG_GROUP}
EOF

touch /opt/glow-runner/bootstrap.ready
echo "[SUCCESS] Runner bootstrap complete"
