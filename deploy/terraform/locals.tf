locals {
  tags = {
    project-name = var.app_name
    ManagedBy    = "terraform"
    Environment  = "production"
  }
}
