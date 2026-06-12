resource "aws_cloudwatch_log_group" "bootstrap" {
  name              = "/glow/${var.domain_name}/bootstrap"
  retention_in_days = 14

  tags = local.tags
}

resource "aws_cloudwatch_log_group" "system" {
  name              = "/glow/${var.domain_name}/system"
  retention_in_days = 14

  tags = local.tags
}
