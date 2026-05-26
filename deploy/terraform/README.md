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
3. **SSH key pair** created in AWS EC2
4. **Route 53 hosted zone** for your domain

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

# SSH access (key must exist in AWS)
ssh_key_name            = "my-key-pair"
ssh_allowed_cidr_blocks = ["0.0.0.0/0"]  # Restrict to your IP in production
```

### 2. Deploy

```bash
./terraform/deploy.sh
```

This will:
1. Create S3 bucket for Terraform state (if needed)
2. Run `terraform init` and `terraform apply`
3. Upload compose files to EC2 via SSH
4. Run activation script that:
   - Installs Docker and Docker Compose
   - Generates runtime secrets
   - Starts the full stack (Glow + ODK Central)
   - Creates ODK admin user (`noreply@<domain>`)
   - Creates ODK API integration user
   - Stores all credentials in `/opt/glow/.env.runtime`

### 3. Access Your Services

After deployment completes:

- **Dashboard**: `https://glow.example.ac.uk`
- **API**: `https://api.glow.example.ac.uk`
- **ODK Central**: `https://odk.glow.example.ac.uk`

### 4. Retrieve Credentials

ODK Central admin credentials are stored on the EC2 instance:

```bash
ssh -i ~/.ssh/my-key-pair.pem ec2-user@<instance-ip> 'cat /opt/glow/.env.runtime'
```

Or use the SSH command from terraform outputs:

```bash
terraform -chdir=terraform output -raw ssh_command | bash -c "$(cat) 'cat /opt/glow/.env.runtime'"
```

## File Structure

```
terraform/
├── deploy.sh          # Main deployment script
├── main.tf            # Terraform backend config
├── variables.tf       # Input variables
├── outputs.tf         # Output values
├── ec2.tf             # EC2 instance, IAM, EBS
├── alb.tf             # Load balancer, listeners, routing
└── terraform.tfvars   # Your configuration (create this)

scripts/
└── activate-stack.sh  # EC2 runtime activation
```

## Management

### View Logs

SSH to instance and use docker compose:

```bash
ssh -i ~/.ssh/my-key-pair.pem ec2-user@<instance-ip>
cd /opt/glow
sudo docker compose logs -f
```

### Restart Services

```bash
sudo docker compose --env-file .env.runtime restart
```

### Update Infrastructure

Edit `terraform.tfvars` and re-run:

```bash
./terraform/deploy.sh
```

### Destroy Everything

```bash
cd terraform
terraform destroy
```

⚠️ **Warning**: This deletes all resources including data. Backup first!

## Troubleshooting

### SSH connection fails

- Check security group allows your IP
- Verify key name matches in terraform.tfvars
- Ensure `.pem` file has correct permissions: `chmod 400 ~/.ssh/key.pem`

### Services not starting

SSH to instance and check:

```bash
sudo docker compose --env-file /opt/glow/.env.runtime ps
sudo docker compose --env-file /opt/glow/.env.runtime logs
```

### Certificate validation slow

ACM DNS validation can take 10-30 minutes. This is normal.

### ALB health checks failing

Check target groups in AWS console. Services must be healthy on EC2 first.

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
- Restrict SSH access via `ssh_allowed_cidr_blocks`
- Review security groups before production use

## Support

For issues, check:
1. EC2 logs: `cat /var/log/user-data.log`
2. Docker compose logs: `sudo docker compose logs`
3. Terraform outputs: `terraform output`
