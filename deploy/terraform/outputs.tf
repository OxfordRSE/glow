output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = aws_lb.main.dns_name
}

output "ec2_instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.main.id
}

output "ec2_public_ip" {
  description = "EC2 instance public IP address"
  value       = aws_instance.main.public_ip
}

output "ssh_key_name" {
  description = "SSH key pair name"
  value       = var.ssh_key_name
}

output "domain_name" {
  description = "Root domain name"
  value       = var.domain_name
}

output "data_volume_id" {
  description = "EBS data volume ID"
  value       = aws_ebs_volume.data.id
}

output "dashboard_url" {
  description = "Dashboard URL"
  value       = "https://${var.domain_name}"
}

output "api_url" {
  description = "API URL"
  value       = "https://api.${var.domain_name}"
}

output "odk_url" {
  description = "ODK Central URL"
  value       = "https://odk.${var.domain_name}"
}

output "ssh_command" {
  description = "SSH command to connect to EC2 instance"
  value       = "ssh -i ~/.ssh/${var.ssh_key_name}.pem ec2-user@${aws_instance.main.public_ip}"
}

output "credentials_location" {
  description = "Location of runtime credentials on EC2 instance"
  value       = "/opt/glow/.env.runtime"
}
