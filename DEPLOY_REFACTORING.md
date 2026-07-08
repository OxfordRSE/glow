# Deployment Refactoring Summary

## Overview

Radically simplified the AWS deployment from a blue/green cutover model to a single long-lived instance with SSM-based updates.

## Removed Files

### Cutover and Data Volume Management
- `deploy/aws/src/glow_aws_deploy/cutover.py`
- `deploy/aws/runtime/mount-data-volume.sh`
- `deploy/aws/runtime/unmount-data-volume.sh`
- `deploy/aws/tests/test_cutover.py`
- `deploy/aws/tests/test_mount_data_volume.py`

### CodeBuild/Bootstrap Infrastructure
- `deploy/aws/terraform_bootstrap/` (entire directory)
- `deploy/aws/codebuild/` (entire directory)
- `deploy/aws/src/glow_aws_deploy/builds.py`
- `deploy/aws/runner/VERSION`
- `deploy/aws/runner/bootstrap.sh`

### Old Python Package
- `deploy/aws/src/` (entire directory - replaced with single script)
- `deploy/aws/tests/` (entire directory)

## Modified Files

### Terraform
- `deploy/aws/terraform/runner.tf`: Replaced launch template with single `aws_instance`, added target group attachments
- `deploy/aws/terraform/variables.tf`: Changed from `runner_ami_version` to `runner_ami_id`, removed `data_volume_size_gb`
- `deploy/aws/terraform/outputs.tf`: Simplified to just instance ID and URLs

### Runtime Scripts
- `deploy/aws/runtime/activate-stack.sh`: Updated to use `/var/lib/glow` instead of `/data` mount
- `deploy/aws/runtime/stop-stack.sh`: Updated state directory path
- `deploy/aws/runtime/update-instance.sh`: New script for SSM-based updates

### Packer
- `deploy/aws/runner/packer.pkr.hcl`: Tag AMIs with git commit instead of version file

### Templates
- `deploy/aws/templates/runner-userdata.sh.tpl`: Now handles full bootstrap including stack activation

### Deploy Script
- `deploy/aws/deploy.py`: Complete rewrite - single 500-line script with:
  - Local Packer AMI building
  - One-pass Terraform apply
  - SSM-based updates
  - Inline waiting with spinner (no console spam)
  - Provision and update modes

### Documentation
- `deploy/aws/README.md`: Rewritten for new model
- `deploy/aws/pyproject.toml`: Simplified dependencies
- `DEPLOYMENT.md`: Updated quick start guide
- `AGENTS.md`: Updated AWS deployment section
- `README.md`: Updated deployment documentation

## Architecture Changes

### Before
- Separate EBS data volume
- Blue/green cutover with volume handoff
- CodeBuild AMI builds in AWS
- Launch template only
- Python launch new instance, attach volume, register with ALB
- Complex rollback logic

### After
- Single long-lived EC2 instance
- 100GB root volume with `delete_on_termination = false`
- Local Packer AMI builds
- Direct `aws_instance` resource
- Terraform manages target group attachments
- SSM-based in-place updates
- No cutover, no rollback needed

## Key Design Decisions

1. **State on root volume**: All data in `/var/lib/glow`, symlinked to `/opt/glow/docker-mount-data`
2. **AMI keyed by git commit**: Find or build AMI tagged with git SHA
3. **Lifecycle protection**: `ignore_changes = [ami, user_data]` prevents accidental replacement
4. **SSM for updates**: Routine releases update code and restart containers in-place
5. **Single deploy script**: All logic in one 500-line Python file instead of multi-module package

## Benefits

- **Simpler**: ~2000 lines of code removed
- **Faster**: No cutover delay, no volume handoff
- **Cheaper**: No temporary second instance during updates
- **Clearer**: One script, one Terraform pass
- **Safer**: No moving volumes between instances

## Tradeoffs

- **No automatic rollback**: Updates happen in-place (can still rollback via git)
- **Data tied to instance**: Use AWS Backup or snapshots for disaster recovery
- **AMI refresh requires planning**: Not routine, needs explicit `--force-rebuild-ami`

## Usage

### Initial provision
```bash
uv run --project deploy/aws deploy/aws/deploy.py \
  --domain example.com \
  --certificate-arn arn:aws:acm:...
```

### Update existing
```bash
uv run --project deploy/aws deploy/aws/deploy.py \
  --domain example.com \
  --git-ref v1.2.3 \
  --update
```
