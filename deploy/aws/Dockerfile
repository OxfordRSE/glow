FROM python:3.12-slim

# Install system dependencies and AWS CLI tools
# (no `git` package needed: glow-deploy resolves git refs via the GitHub API)
RUN apt-get update && apt-get install -y --no-install-recommends \
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

# Copy only the deploy/aws directory into the image, then install it as a
# package (this is what provides the `glow-deploy` console script).
WORKDIR /opt/glow
COPY deploy/aws /opt/glow/deploy/aws
RUN pip install --no-cache-dir /opt/glow/deploy/aws

# Copy entrypoint script
COPY deploy/aws/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
