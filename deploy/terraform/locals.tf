locals {
  project_name = "glow"

  tags = {
    Project      = var.app_name
    project-name = local.project_name
    ManagedBy    = "terraform"
    Environment  = "production"
  }
}
