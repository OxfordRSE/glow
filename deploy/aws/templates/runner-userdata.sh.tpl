#!/usr/bin/env bash
set -euo pipefail

exec > >(tee -a /var/log/glow-runner-bootstrap.log) 2>&1

echo "[PROGRESS] Start bootstrap"

AWS_REGION="${aws_region}"
DOMAIN_NAME="${domain_name}"
GIT_REPO_URL="${git_repo_url}"
GIT_CHECKOUT_REF="${git_checkout_ref}"
CLOUDWATCH_BOOTSTRAP_LOG_GROUP="${cloudwatch_bootstrap_log_group}"
CLOUDWATCH_CONTAINERS_LOG_GROUP="${cloudwatch_containers_log_group}"
CLOUDWATCH_SYSTEM_LOG_GROUP="${cloudwatch_system_log_group}"

TOKEN=$(curl -fsS -X PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
INSTANCE_ID=$(curl -fsS -H "X-aws-ec2-metadata-token: $${TOKEN}" \
  http://169.254.169.254/latest/meta-data/instance-id)

echo "[PROGRESS] Set up CloudWatch Agent"

cloud_init_config=/opt/aws/amazon-cloudwatch-agent/etc/cloud_init.json
cloud_glow_config=/opt/aws/amazon-cloudwatch-agent/etc/glow.json

cat > $${cloud_glow_config} <<EOF
{
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/glow-runner-bootstrap.log",
            "log_group_name": "$${CLOUDWATCH_BOOTSTRAP_LOG_GROUP}",
            "log_stream_name": "$${INSTANCE_ID}/runner-bootstrap"
          },
          {
            "file_path": "/var/log/messages",
            "log_group_name": "$${CLOUDWATCH_SYSTEM_LOG_GROUP}",
            "log_stream_name": "$${INSTANCE_ID}/messages"
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
  -c "file:$${cloud_init_config}"
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a append-config \
  -m ec2 \
  -c file:$${cloud_glow_config}

echo "[PROGRESS] Configure docker logging"

mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<EOF
{
  "log-driver": "awslogs",
  "log-opts": {
    "awslogs-region": "$${AWS_REGION}",
    "awslogs-group": "$${CLOUDWATCH_CONTAINERS_LOG_GROUP}",
    "awslogs-create-group": "false",
    "tag": "$${INSTANCE_ID}-{{.Name}}"
  }
}
EOF

systemctl restart docker

echo "[PROGRESS] Clone repository"

if [[ -d /opt/glow/.git ]]; then
  echo "[PROGRESS] Refreshing existing repository clone"
  git -C /opt/glow fetch --tags --prune origin
else
  rm -rf /opt/glow
  git clone "$${GIT_REPO_URL}" /opt/glow
fi

echo "[PROGRESS] Checking out $${GIT_CHECKOUT_REF}"
git -C /opt/glow fetch --tags --prune origin
git -C /opt/glow checkout --force "$${GIT_CHECKOUT_REF}"

echo "[PROGRESS] Write /etc/glow-runner.env"

cat > /etc/glow-runner.env <<EOF
AWS_REGION=$${AWS_REGION}
DOMAIN_NAME=$${DOMAIN_NAME}
GIT_REPO_URL=$${GIT_REPO_URL}
GIT_CHECKOUT_REF=$${GIT_CHECKOUT_REF}
CLOUDWATCH_CONTAINERS_LOG_GROUP=$${CLOUDWATCH_CONTAINERS_LOG_GROUP}
EOF

touch /opt/glow-runner/bootstrap.ready

echo "[PROGRESS] Activate stack"
DOMAIN_NAME="$${DOMAIN_NAME}" bash /opt/glow/deploy/aws/runtime/activate-stack.sh

echo "[SUCCESS] Runner bootstrap complete"
