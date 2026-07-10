# Glow AWS Deployment

Simplified deployment using:

- Local Packer builds for thin runner AMIs
- Single-pass Terraform for infrastructure
- SSM-based in-place updates for routine releases
- Long-lived EC2 instance with persistent root volume

## Prerequisites

### Option 1: Docker (Recommended)

1. Docker
2. AWS credentials (via SSO, profile, or environment variables)

### Option 2: Direct Python

1. `uv`
2. `terraform`
3. `packer`
4. `git`
5. AWS credentials for the target account

## Usage

### Docker Compose (Easiest)

The simplest way to deploy is using Docker Compose with profiles. Use `--profile sso` for AWS SSO authentication or
`--profile env` for environment credentials.

#### Initial Provision

**Using AWS SSO (for individual users):**

```bash
# First, authenticate on your host machine
export AWS_PROFILE=my-profile
aws sso login

# Navigate to deploy/aws directory
cd deploy/aws

# Run deployment with SSO profile
docker compose --profile sso run --rm deploy \
  --domain eu.glow-project.org \
  --certificate-arn arn:aws:acm:eu-west-2:123456789012:certificate/abc123
```

**Using environment credentials (for CI or temporary credentials):**

```bash
cd deploy/aws

# Run deployment with env profile
docker compose --profile env run --rm deploy-env \
  --domain eu.glow-project.org \
  --certificate-arn arn:aws:acm:eu-west-2:123456789012:certificate/abc123
```

Note: Ensure `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and optionally `AWS_SESSION_TOKEN` are set in your
environment.

#### Subsequent Updates

**Using AWS SSO:**

```bash
AWS_PROFILE=my-profile 
aws sso login
cd deploy/aws

docker compose --profile sso run --rm deploy \
  --domain eu.glow-project.org \
  --git-ref v1.2.3 \
  --update
```

**Using environment credentials:**

```bash
cd deploy/aws

docker compose --profile env run --rm deploy-env \
  --domain eu.glow-project.org \
  --git-ref v1.2.3 \
  --update
```

### Docker Run (Alternative)

If you prefer not to use Docker Compose, you can use `docker run` directly.

#### Build the launcher image

From the repository root:

```bash
docker build -t glow-launcher -f deploy/aws/Dockerfile .
```

#### Initial Provision

**Using AWS SSO (for individual users):**

```bash
# First, authenticate on your host machine
aws sso login --profile my-profile

# Then run the deployment
docker run --rm -it \
  -e AWS_PROFILE=my-profile \
  -e AWS_REGION=eu-west-2 \
  -v "$HOME/.aws:/aws-host:ro" \
  glow-launcher \
  --domain eu.glow-project.org \
  --certificate-arn arn:aws:acm:eu-west-2:123456789012:certificate/abc123
```

**Using environment credentials (for CI or temporary credentials):**

```bash
docker run --rm -it \
  -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
  -e AWS_SESSION_TOKEN=$AWS_SESSION_TOKEN \
  -e AWS_REGION=eu-west-2 \
  glow-launcher \
  --domain eu.glow-project.org \
  --certificate-arn arn:aws:acm:eu-west-2:123456789012:certificate/abc123
```

This will:

1. Build a runner AMI in your AWS account using Packer
2. Apply Terraform to create infrastructure and a single EC2 instance
3. Wait for the instance to bootstrap and activate the stack
4. Verify health checks

#### Subsequent Updates

**Using AWS SSO:**

```bash
docker run --rm -it \
  -e AWS_PROFILE=my-profile \
  -e AWS_REGION=eu-west-2 \
  -v "$HOME/.aws:/aws-host:ro" \
  glow-launcher \
  --domain eu.glow-project.org \
  --git-ref v1.2.3 \
  --update
```

**Using environment credentials:**

```bash
docker run --rm -it \
  -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
  -e AWS_SESSION_TOKEN=$AWS_SESSION_TOKEN \
  -e AWS_REGION=eu-west-2 \
  glow-launcher \
  --domain eu.glow-project.org \
  --git-ref v1.2.3 \
  --update
```

This will:

1. Find the existing instance via Terraform outputs
2. Send an SSM command to update the repository and restart containers
3. Verify health checks

### Direct Python Deployment

If you prefer to install dependencies locally:

#### Initial Provision

```bash
uv run --project deploy/aws deploy/aws/deploy.py \
  --domain eu.glow-project.org \
  --certificate-arn arn:aws:acm:eu-west-2:123456789012:certificate/abc123
```

#### Subsequent Updates

```bash
uv run --project deploy/aws deploy/aws/deploy.py \
  --domain eu.glow-project.org \
  --git-ref v1.2.3 \
  --update
```

### Command-Line Flags

- `--domain` (required): deployment domain
- `--certificate-arn`: ACM certificate ARN (if omitted, must exist in account)
- `--git-ref`: git tag/branch/commit to deploy (default: main)
- `--aws-region`: AWS region (default: eu-west-2 or AWS_REGION env var)
- `--runner-instance-type`: EC2 instance type (default: t3.medium)
- `--runner-root-volume-size-gb`: root volume size in GB (default: 100)
- `--force-rebuild-ami`: force AMI rebuild even if one exists
- `--dry-run`: plan only, do not apply
- `--update`: update existing instance instead of provision

### AWS Authentication

The deploy script uses standard AWS credential resolution via boto3:

1. **Environment variables**: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`
2. **AWS config and credentials files**: `~/.aws/config` and `~/.aws/credentials` (respects `AWS_PROFILE`)
3. **IAM role** (when running in EC2, ECS, Lambda, etc.)

For containerized deployments:

- **AWS SSO users**: Mount `~/.aws` read-only and authenticate on the host before running the container
- The launcher copies `~/.aws` into container-local `~/.aws` at startup, so cache or token refreshes inside Docker do not write root-owned files back to the host
- **CI/CD**: Pass credentials as environment variables
- **Credential process or vault tools**: If using `credential_process`, `aws-vault`, or OS keychain helpers, either:
  - Include the helper binary in the image, or
  - Use environment credentials instead

## Architecture

### AMI

The runner AMI is thin:

- Base: Amazon Linux 2023
- Pre-installed: Docker, git, curl, jq, CloudWatch agent
- Build artifact is tagged with git commit SHA

### Instance

The EC2 instance is long-lived:

- Managed by Terraform with `lifecycle.ignore_changes = [ami, user_data]`
- Root EBS volume stores all persistent state under `/var/lib/glow`
- `delete_on_termination = false` protects data

### Persistent State

All application state lives in `/var/lib/glow`:

- Postgres data
- ODK secrets
- Runtime configuration
- Deployment metadata

The repository checkout at `/opt/glow` has `docker-mount-data` symlinked to `/var/lib/glow`.

### Updates

Routine updates happen via SSM without replacing the instance:

1. Fetch and checkout the target git ref
2. Optionally run `deploy/update-instance.sh` hook if present
3. Stop containers
4. Restart containers with `activate-stack.sh`
5. Verify health

AMI rebuilds are only needed for:

- First deployment into an account
- Dependency changes in `install-runner-deps.sh`
- Explicit instance replacement

## Notes

- DNS is assumed to be managed externally
- ACM certificate must be issued before deployment
- The deploy script prints DNS routing records for the external DNS owner
- Backups via AWS Backup or EBS snapshots are recommended
