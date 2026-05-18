# Devcontainer image: consolidated Python + Node + dev tooling
FROM mcr.microsoft.com/devcontainers/base:ubuntu

# Install Python 3.12
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install -y --no-install-recommends \
        python3.12 \
        python3.12-venv \
        python3-pip \
        gcc \
        libffi-dev \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1 \
    && rm -rf /var/lib/apt/lists/*

# Install Node 22
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast Python package management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:${PATH}"

# Install Playwright system dependencies
RUN npx --yes playwright@1.55.0 install-deps chromium

# Set working directory
WORKDIR /workspace

# Keep container running
CMD ["sleep", "infinity"]
