provider "aws" {
  region = var.aws_region
}

locals {
  tags = {
    ManagedBy    = "Terraform"
    project-name = var.app_name
    Domain       = var.domain_name
    Stack        = "glow"
  }
}
