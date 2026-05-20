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

variable "image_tag" {
  description = "Docker image tag to deploy (e.g. 0.1.0)"
  type        = string
}

variable "api_min_n" {
  description = "Minimum N (student count) for suppression"
  type        = number
  default     = 5
}

variable "api_secret_key" {
  description = "JWT secret key for the API"
  type        = string
  sensitive   = true
}

variable "container_cpu" {
  description = "CPU units for each container (1024 = 1 vCPU)"
  type        = number
  default     = 256
}

variable "container_memory" {
  description = "Memory in MiB for each container"
  type        = number
  default     = 512
}

variable "desired_count" {
  description = "Desired number of ECS tasks"
  type        = number
  default     = 1
}

variable "domain_name" {
  description = <<-EOT
    Custom domain name for the application (e.g. "dashboard.example.ac.uk").
    Set this in your terraform.tfvars file. When set:
      - Terraform requests an ACM certificate via DNS validation (Route 53).
      - A Route 53 ALIAS record is created pointing the domain to the ALB.
      - The HTTPS listener (port 443) is created; HTTP redirects to HTTPS.
    Leave empty ("") for HTTP-only with the ALB DNS name directly.

    After the first apply with a domain name, check the `domain_setup_note`
    output for any manual steps required (e.g. delegating nameservers if
    the hosted zone was newly created outside this stack).
  EOT
  type        = string
  default     = ""
}
