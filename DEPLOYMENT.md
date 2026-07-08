# Glow Deployment Quick Start

## Prerequisites

### Option 1: Docker (Recommended)

1. Docker
2. AWS credentials (via SSO, profile, or environment variables)

Build the launcher image from the repository root:

```bash
docker build -t glow-launcher -f deploy/aws/Dockerfile .
```

### Option 2: Direct Python

1. `uv`
2. `terraform`
3. `packer`
4. `git`
5. AWS credentials for EC2, ALB, ACM, S3, IAM, and SSM

## Initial Provision

### Using Docker with AWS SSO (Individual Users)

```bash
# Authenticate on your host machine first
aws sso login --profile my-profile

# Run deployment
docker run --rm -it \
  -e AWS_PROFILE=my-profile \
  -e AWS_REGION=eu-west-2 \
  -v "$HOME/.aws:/root/.aws:ro" \
  glow-launcher \
  --domain eu.glow-project.org \
  --certificate-arn arn:aws:acm:eu-west-2:123456789012:certificate/abc123
```

### Using Docker with Environment Credentials (CI/CD)

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

### Using Direct Python

```bash
uv run --project deploy/aws deploy/aws/deploy.py \
  --domain eu.glow-project.org \
  --certificate-arn arn:aws:acm:eu-west-2:123456789012:certificate/abc123
```

## Update Existing Deployment

### Using Docker with AWS SSO

```bash
docker run --rm -it \
  -e AWS_PROFILE=my-profile \
  -e AWS_REGION=eu-west-2 \
  -v "$HOME/.aws:/root/.aws:ro" \
  glow-launcher \
  --domain eu.glow-project.org \
  --git-ref v1.2.3 \
  --update
```

### Using Docker with Environment Credentials

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

### Using Direct Python

```bash
uv run --project deploy/aws deploy/aws/deploy.py \
  --domain eu.glow-project.org \
  --git-ref v1.2.3 \
  --update
```

## What It Does

### Initial Provision

1. Resolves the git reference to a commit SHA
2. Checks if a runner AMI exists in your AWS account for that commit
3. Builds the AMI using Packer if not found
4. Applies Terraform to create:
   - ALB with HTTPS listeners
   - Security groups and IAM roles
   - Single long-lived EC2 instance with 100GB root volume
   - CloudWatch log groups
5. Waits for the instance to bootstrap and activate the stack
6. Verifies service health

### Update

1. Finds the existing instance via Terraform state
2. Sends an SSM command to:
   - Fetch and checkout the target git reference
   - Run optional `deploy/update-instance.sh` hook
   - Stop and restart containers
3. Verifies service health

## Flags

- `--domain` (required): deployment domain
- `--certificate-arn`: ACM certificate ARN
- `--git-ref`: git tag/branch/commit (default: main)
- `--aws-region`: AWS region (default: eu-west-2 or AWS_REGION env var)
- `--runner-instance-type`: instance type (default: t3.medium)
- `--runner-root-volume-size-gb`: root volume size (default: 100GB)
- `--force-rebuild-ami`: rebuild AMI even if one exists
- `--dry-run`: plan only, do not apply
- `--update`: update existing instance instead of provision

## Certificate Assumption

Deployment requires an already-issued ACM certificate for:

- `<domain>`
- `api.<domain>`
- `odk.<domain>`

Provide the ARN with `--certificate-arn`.

## DNS Ownership

DNS is assumed to be managed externally. After deployment, configure these records with your DNS provider:

- `<domain>` → ALB DNS (CNAME or ALIAS)
- `api.<domain>` → ALB DNS (CNAME)
- `odk.<domain>` → ALB DNS (CNAME)

The deploy script prints the exact ALB DNS name.

## Architecture

- **AMI**: Thin image with Docker, git, and dependencies pre-installed
- **Instance**: Long-lived EC2 with persistent root volume
- **State**: All data stored in `/var/lib/glow` on the root volume
- **Updates**: In-place via SSM, no instance replacement
- **Backups**: Use AWS Backup or EBS snapshots

## Notes

- The instance is protected with `delete_on_termination = false` on the root volume
- Terraform ignores AMI and userdata changes to prevent accidental replacement
- For dependency updates, rebuild the AMI with `--force-rebuild-ami`
- Routine application updates use `--update` and happen over SSM
