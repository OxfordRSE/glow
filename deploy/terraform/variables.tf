variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "eu-west-2"
}

variable "app_name" {
  description = "Application name (used as prefix for all resources)"
  type        = string
  default     = "glow-core"
}

# ─── EC2 Configuration ────────────────────────────────────────────────────────

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.medium"
}

variable "availability_zone" {
  description = "Availability zone for EC2 instance and EBS volume"
  type        = string
  default     = "eu-west-2a"
}

variable "data_volume_size_gb" {
  description = "Size of the persistent data EBS volume in GB"
  type        = number
  default     = 100
}

variable "ssh_key_name" {
  description = "Name of the SSH key pair for EC2 access (must already exist in AWS)"
  type        = string
}

variable "ssh_allowed_cidr_blocks" {
  description = "CIDR blocks allowed to SSH to the EC2 instance"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

# ─── Domain Configuration ─────────────────────────────────────────────────────

variable "domain_name" {
  description = <<-EOT
    Root domain name for the application (e.g. "eu.glow-project.org" or "glow.example.ac.uk").
    When set, the following subdomains will be configured:
      - <domain> (dashboard)
      - api.<domain> (API)
      - odk.<domain> (ODK Central)
    
    Terraform will:
      - Request an ACM certificate via DNS validation
      - Configure HTTPS listener (port 443) with host-based routing
      - Redirect HTTP (port 80) to HTTPS
    
    If you control the Route 53 hosted zone for the domain (or parent domain), 
    set manage_dns=true to auto-create DNS records.
    
    If the domain is managed externally (delegated subdomain), set manage_dns=false
    and follow the DNS setup instructions in terraform outputs.
  EOT
  type        = string
}

variable "manage_dns" {
  description = <<-EOT
    Whether to manage DNS records in Route 53.
    
    Set to true if:
      - You own the domain's Route 53 hosted zone, OR
      - You own the parent domain's zone (e.g. you own "example.ac.uk" and deploying to "glow.example.ac.uk")
    
    Set to false if:
      - The domain is managed by another organization
      - You're deploying to a delegated subdomain (e.g. "eu.glow-project.org" where parent owns "glow-project.org")
    
    When false, terraform outputs will provide DNS records to share with the domain owner.
  EOT
  type        = bool
  default     = true
}
