output "alb_dns_name" {
  value = aws_lb.main.dns_name
}

output "runner_instance_id" {
  value = aws_instance.runner.id
}

output "certificate_arn" {
  value = var.certificate_arn
}

output "dashboard_url" {
  value = "https://${var.domain_name}"
}

output "api_url" {
  value = "https://api.${var.domain_name}"
}

output "odk_url" {
  value = "https://odk.${var.domain_name}"
}
