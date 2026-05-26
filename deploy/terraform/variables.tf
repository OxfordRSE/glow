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
    Root domain name for the application (e.g. "glow.example.ac.uk").
    When set, the following subdomains will be configured:
      - glow.example.ac.uk (dashboard)
      - api.glow.example.ac.uk (API)
      - odk.glow.example.ac.uk (ODK Central)
    
    Terraform will:
      - Request an ACM certificate via DNS validation (Route 53)
      - Create Route 53 ALIAS records pointing to the ALB
      - Configure HTTPS listener (port 443) with host-based routing
      - Redirect HTTP (port 80) to HTTPS
    
    A Route 53 hosted zone for the parent domain must already exist.
  EOT
  type        = string
}
