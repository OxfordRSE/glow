FROM python:3.12-slim

# Install system dependencies and AWS CLI tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    unzip \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Terraform
ARG TERRAFORM_VERSION=1.9.8
RUN curl -fsSL "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip" -o /tmp/terraform.zip \
    && unzip -o /tmp/terraform.zip -d /usr/local/bin \
    && rm /tmp/terraform.zip \
    && chmod +x /usr/local/bin/terraform

# Install Packer
ARG PACKER_VERSION=1.11.2
RUN curl -fsSL "https://releases.hashicorp.com/packer/${PACKER_VERSION}/packer_${PACKER_VERSION}_linux_amd64.zip" -o /tmp/packer.zip \
    && unzip -o /tmp/packer.zip -d /usr/local/bin \
    && rm /tmp/packer.zip \
    && chmod +x /usr/local/bin/packer

# Install AWS CLI v2
RUN curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip \
    && unzip /tmp/awscliv2.zip -d /tmp \
    && /tmp/aws/install \
    && rm -rf /tmp/aws /tmp/awscliv2.zip

# Install Python dependencies
RUN pip install --no-cache-dir boto3>=1.35.0

# Copy only the deploy/aws directory into the image
WORKDIR /opt/glow
COPY deploy/aws /opt/glow/deploy/aws

# Ensure deploy script is executable
RUN chmod +x /opt/glow/deploy/aws/deploy.py

# Copy entrypoint script
COPY deploy/aws/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
