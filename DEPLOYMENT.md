# Glow Deployment Quick Start

## One-Command Deployment

```bash
./deploy/deploy.sh
```

That's it! This single command deploys the entire Glow infrastructure to AWS.

## Prerequisites (5 minutes)

1. **AWS CLI** - configured with your credentials
   ```bash
   aws configure
   ```

2. **Terraform** - version 1.5.0 or later
   ```bash
   # macOS
   brew install terraform
   
   # Ubuntu/Debian  
   wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
   echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
   sudo apt update && sudo apt install terraform
   ```

3. **SSH Key Pair** - created in AWS EC2 console
   - Go to EC2 → Key Pairs → Create key pair
   - Download the `.pem` file to `~/.ssh/`
   - Set permissions: `chmod 400 ~/.ssh/your-key.pem`

4. **Domain Setup** - choose ONE of:

   **Option A: You own the domain's Route 53 hosted zone**
   ```bash
   aws route53 create-hosted-zone --name example.ac.uk --caller-reference $(date +%s)
   ```
   Then update your domain's nameservers at your registrar.
   
   **Option B: Delegated subdomain (managed by another organization)**
   
   You're deploying to a subdomain like `eu.glow-project.org` where the parent organization owns `glow-project.org`.
   
   No Route 53 setup needed! The deployment will generate DNS instructions to send to the domain owner.

## Configuration (2 minutes)

Create `deploy/terraform/terraform.tfvars`:

**Option A: You own the domain (manage DNS automatically)**
```hcl
domain_name             = "glow.example.ac.uk"
manage_dns              = true  # Default - creates Route 53 records
ssh_key_name            = "my-key-pair"
ssh_allowed_cidr_blocks = ["0.0.0.0/0"]  # Restrict to your IP in production
```

**Option B: Delegated subdomain (DNS managed externally)**
```hcl
domain_name             = "eu.glow-project.org"
manage_dns              = false  # Don't create Route 53 records
ssh_key_name            = "my-key-pair"
ssh_allowed_cidr_blocks = ["0.0.0.0/0"]  # Restrict to your IP in production
```

See `deploy/terraform/terraform.tfvars.example` for all options.

## Deploy (15-20 minutes)

```bash
./deploy/deploy.sh
```

The script will:
1. Create S3 bucket for Terraform state
2. Run Terraform to create AWS infrastructure
3. Request ACM certificate (DNS validation)
4. Upload compose files to EC2 via SSH
5. Install Docker on EC2
6. Generate runtime secrets
7. Start all services (Glow + ODK Central)
8. Configure ODK integration

**If using delegated subdomain (manage_dns=false):**

The deployment will display DNS setup instructions at the end. Copy these and send them to your domain administrator. Example output:

```
═══════════════════════════════════════════════════════════════════════════
DNS SETUP INSTRUCTIONS
═══════════════════════════════════════════════════════════════════════════

Your domain is NOT managed by Route 53 (manage_dns=false).
Share these DNS records with your domain administrator:

For ACM certificate validation (temporary):
_abc123.eu.glow-project.org  →  CNAME  →  _def456.acm-validations.aws.
_abc123.api.eu.glow-project.org  →  CNAME  →  _def456.acm-validations.aws.
_abc123.odk.eu.glow-project.org  →  CNAME  →  _def456.acm-validations.aws.

For application access (permanent):
eu.glow-project.org      →  CNAME  →  glow-core-alb-123456789.eu-west-2.elb.amazonaws.com
api.eu.glow-project.org  →  CNAME  →  glow-core-alb-123456789.eu-west-2.elb.amazonaws.com
odk.eu.glow-project.org  →  CNAME  →  glow-core-alb-123456789.eu-west-2.elb.amazonaws.com
```

**Services will NOT be accessible until:**
1. Domain administrator creates the DNS records
2. ACM certificate validates (10-30 minutes after DNS propagation)

Check certificate status:
```bash
aws acm describe-certificate --certificate-arn arn:aws:acm:... --query 'Certificate.Status'
```

## Access Your Services

After deployment (and DNS setup if manage_dns=false):

- **Dashboard**: `https://<your-domain>`
- **API**: `https://api.<your-domain>`  
- **ODK Central**: `https://odk.<your-domain>`

## Get Credentials

ODK credentials are auto-generated and stored on EC2:

```bash
# Get the SSH command from terraform
terraform -chdir=deploy/terraform output ssh_command

# SSH to instance
ssh -i ~/.ssh/my-key.pem ec2-user@<ip>

# View credentials
cat /opt/glow/.env.runtime
```

Look for:
- `ODK_API_EMAIL`
- `ODK_API_PASSWORD`

## Troubleshooting

**Deployment fails during terraform apply:**
- Check AWS credentials: `aws sts get-caller-identity`
- Verify SSH key exists in AWS: `aws ec2 describe-key-pairs`
- Ensure Route 53 zone exists: `aws route53 list-hosted-zones`

**Can't SSH to EC2:**
- Check key permissions: `chmod 400 ~/.ssh/key.pem`
- Verify your IP is allowed in terraform.tfvars
- Wait a minute for instance to fully boot

**Services not accessible:**
- ACM certificate validation takes 10-30 minutes
- Check target health: AWS Console → EC2 → Target Groups
- SSH to instance and check: `sudo docker compose ps`

## What Gets Created

- **1x EC2 instance** (t3.medium) running Docker Compose
- **1x Application Load Balancer** with subdomain routing
- **1x EBS volume** (100GB) for persistent data
- **Route 53 DNS records** for all subdomains
- **ACM TLS certificate** (auto-renewing)
- **Security groups** for ALB and EC2

**Estimated cost**: ~$55/month

## Next Steps

1. **Log into ODK Central** at `https://odk.glow.example.ac.uk`
2. **Create projects and forms** in ODK Central
3. **Upload data** to `/opt/glow/data/` on EC2
4. **Configure backups** - snapshot the EBS volume regularly

## Full Documentation

See `deploy/terraform/README.md` for complete documentation including:
- Architecture details
- Management commands
- Update procedures
- Backup and recovery

## Need Help?

Check the logs on EC2:
```bash
ssh -i ~/.ssh/key.pem ec2-user@<ip>
sudo docker compose logs -f
```
