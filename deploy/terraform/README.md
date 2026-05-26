# Glow Infrastructure Deployment

Single-command deployment of Glow (API + Dashboard + ODK Central) on AWS.

## Architecture

- **EC2 instance** running Docker Compose with all services
- **Application Load Balancer** with subdomain-based routing:
  - `example.com` → Dashboard
  - `api.example.com` → Glow API
  - `odk.example.com` → ODK Central
- **Route 53** DNS + **ACM** TLS certificates
- **EBS volume** for persistent data storage

## Prerequisites

1. **AWS CLI** installed and configured (`aws configure`)
2. **Terraform** >= 1.5.0
3. **Route 53 hosted zone** for your domain (if using manage_dns=true)

## Quick Start

### 1. Create terraform.tfvars

```hcl
# terraform/terraform.tfvars

aws_region        = "eu-west-2"
availability_zone = "eu-west-2a"

# Domain configuration (Route 53 hosted zone must exist)
domain_name = "glow.example.ac.uk"

# EC2 configuration
instance_type       = "t3.medium"
data_volume_size_gb = 100

# Deployment configuration
# git_ref = "v1.2.3"  # Specific version (leave empty for latest release)
```

### 2. Deploy

```bash
./deploy/deploy.sh
```

This will:
1. Create S3 bucket for Terraform state (if needed)
2. Run `terraform init` and `terraform apply`
3. EC2 user data automatically:
   - Clones the repository from GitHub
   - Installs Docker and Docker Compose
   - Mounts persistent EBS volume
   - Generates runtime secrets
   - Starts the full stack (Glow + ODK Central)
   - Creates ODK admin user
   - Creates ODK API integration user
4. Monitor progress via CloudWatch logs

### 3. Access Your Services

After deployment completes:

- **Dashboard**: `https://glow.example.ac.uk`
- **API**: `https://api.glow.example.ac.uk`
- **ODK Central**: `https://odk.glow.example.ac.uk`

### 4. Retrieve Credentials

ODK Central admin credentials are stored on the EC2 instance.

**Via SSM Session Manager (recommended):**
```bash
aws ssm start-session --target <instance-id>
cat /opt/glow/docker-mount-data/.deploy/.env.admin
```

**Or get from terraform output:**
```bash
terraform -chdir=deploy/terraform output -raw ssm_session_command
```

## File Structure

```
deploy/
├── deploy.sh                    # Main deployment script
├── terraform/
│   ├── main.tf                  # Terraform backend config
│   ├── variables.tf             # Input variables
│   ├── outputs.tf               # Output values
│   ├── ec2.tf                   # EC2 instance, IAM, EBS
│   ├── alb.tf                   # Load balancer, listeners, routing
│   ├── cloudwatch.tf            # CloudWatch log groups
│   ├── user-data.sh             # EC2 bootstrap script
│   └── terraform.tfvars         # Your configuration (create this)
└── scripts/
    ├── activate-stack.sh        # Runtime activation
    └── update-stack.sh          # Update existing deployment
```

## Management

### View Logs

**CloudWatch logs (activation/updates):**
```bash
aws logs tail /aws/ec2/cloud-init --follow
```

**Application logs via SSM:**
```bash
aws ssm start-session --target <instance-id>
cd /opt/glow
sudo docker compose logs -f
```

### Restart Services

```bash
aws ssm start-session --target <instance-id>
cd /opt/glow
sudo docker compose --profile odk restart
```

### Update Deployment

Edit `terraform.tfvars` (e.g., change `git_ref` to new version) and re-run:

```bash
./deploy/deploy.sh
```

The script will detect the existing deployment and trigger an update.

### Destroy Everything

```bash
cd deploy/terraform
terraform destroy
```

⚠️ **Warning**: This deletes all resources including data. Backup first!

## Troubleshooting

### Cannot access instance

**SSM Session Manager not working:**
- Ensure instance has SSM agent running (pre-installed on Amazon Linux 2023)
- Check IAM role has SSM permissions (should be automatic)
- Install session manager plugin: `aws ssm start-session` will show instructions

**EC2 Instance Connect:**
```bash
aws ec2-instance-connect ssh --instance-id <instance-id>
```

### Services not starting

Check activation logs:
```bash
aws logs tail /aws/ec2/cloud-init --follow
```

Or connect to instance and check:
```bash
aws ssm start-session --target <instance-id>
sudo docker compose ps
sudo docker compose logs
```

### Certificate validation slow

ACM DNS validation can take 10-30 minutes. This is normal.

### ALB health checks failing

Check target groups in AWS console. Services must be healthy on EC2 first.

### Deployment version conflicts

If you see a major version upgrade error, check:
```bash
cat /opt/glow/docker-mount-data/.glow-deployment-version
```

Consult the upgrade guide: `UPGRADING.md`

## Cost Estimate

Approximate monthly costs (eu-west-2):

- EC2 t3.medium: ~$30/month
- EBS 100GB gp3: ~$8/month  
- ALB: ~$16/month
- Route 53: ~$0.50/month
- **Total**: ~$55/month

## Security Notes

- All secrets are generated at runtime and stored on EC2 only
- TLS certificates auto-renew via ACM
- EBS volumes are encrypted at rest
- Instance access via SSM Session Manager (no SSH port exposed)
- Review security groups before production use

## Support

For issues, check:
1. EC2 logs: `cat /var/log/user-data.log`
2. Docker compose logs: `sudo docker compose logs`
3. Terraform outputs: `terraform output`
