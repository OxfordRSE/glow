#!/usr/bin/env bash
set -euo pipefail

dnf update -y
dnf install -y \
  amazon-cloudwatch-agent \
  curl \
  docker \
  docker-compose-plugin \
  file \
  git \
  jq \
  openssl \
  shadow-utils \
  util-linux

systemctl enable docker
usermod -aG docker ec2-user
mkdir -p /opt/glow-runner
