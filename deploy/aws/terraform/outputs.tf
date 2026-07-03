output "alb_dns_name" {
  value = aws_lb.main.dns_name
}

output "runner_launch_template_id" {
  value = aws_launch_template.runner.id
}

output "runner_launch_template_latest_version" {
  value = aws_launch_template.runner.latest_version
}

output "runner_subnet_id" {
  value = data.aws_subnet.runner.id
}

output "data_volume_id" {
  value = aws_ebs_volume.data.id
}

output "primary_target_group_arn" {
  value = aws_lb_target_group.dashboard.arn
}

output "target_group_arns" {
  value = [
    aws_lb_target_group.api.arn,
    aws_lb_target_group.dashboard.arn,
    aws_lb_target_group.odk.arn,
  ]
}

output "certificate_arn" {
  value = var.certificate_arn
}

output "dashboard_url" {
  value = "https://${var.domain_name}"
}
