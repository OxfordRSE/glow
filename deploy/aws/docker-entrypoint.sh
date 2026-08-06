#!/bin/bash
set -euo pipefail

# Entrypoint script for glow-launcher container
# Copies host AWS config into a container-local home when provided,
# then forwards all arguments to the installed glow-deploy console script.

if [[ -d /aws-host ]]; then
  rm -rf /root/.aws
  mkdir -p /root/.aws
  cp -a /aws-host/. /root/.aws/
fi

exec glow-deploy "$@"
