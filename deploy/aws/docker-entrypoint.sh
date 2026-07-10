#!/bin/bash
set -euo pipefail

# Entrypoint script for glow-launcher container
# Copies host AWS config into a container-local home when provided,
# then forwards all arguments to deploy.py.

if [[ -d /aws-host ]]; then
  rm -rf /root/.aws
  mkdir -p /root/.aws
  cp -a /aws-host/. /root/.aws/
fi

exec python3 /opt/glow/deploy/aws/deploy.py "$@"
