#!/bin/bash
set -euo pipefail

# Entrypoint script for glow-launcher container
# Forwards all arguments to deploy.py

exec python3 /opt/glow/deploy/aws/deploy.py "$@"
