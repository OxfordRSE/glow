#!/usr/bin/env bash
set -euo pipefail

export AWS_REGION="${aws_region}"
export DOMAIN_NAME="${domain_name}"
export GIT_REPO_URL="${git_repo_url}"
export GIT_CHECKOUT_REF="${git_checkout_ref}"
export CLOUDWATCH_BOOTSTRAP_LOG_GROUP="${cloudwatch_bootstrap_log_group}"
export CLOUDWATCH_SYSTEM_LOG_GROUP="${cloudwatch_system_log_group}"

exec /opt/glow-runner/bootstrap.sh
