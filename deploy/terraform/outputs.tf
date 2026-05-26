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
  value       = "/opt/glow/deploy/.deploy/share/.env.runtime"
}

# ─── DNS Setup Instructions ──────────────────────────────────────────────────

output "dns_managed" {
  description = "Whether DNS is managed by Terraform in Route 53"
  value       = var.manage_dns
}

output "dns_setup_instructions" {
  description = "DNS records to configure (if manage_dns=false, share these with your domain administrator)"
  value = var.domain_name != "" ? (var.manage_dns ? 
    "DNS records automatically created in Route 53" :
    <<-EOT
    
    ═══════════════════════════════════════════════════════════════════════════
    DNS SETUP INSTRUCTIONS
    ═══════════════════════════════════════════════════════════════════════════
    
    Your domain is NOT managed by Route 53 (manage_dns=false).
    Share these DNS records with your domain administrator:
    
    ───────────────────────────────────────────────────────────────────────────
    1. ACM Certificate Validation (CNAME records)
    ───────────────────────────────────────────────────────────────────────────
    ${join("\n    ", [for dvo in aws_acm_certificate.main[0].domain_validation_options : 
      format("%-60s  CNAME  %s", dvo.resource_record_name, dvo.resource_record_value)
    ])}
    
    IMPORTANT: The certificate will not validate until these CNAME records are created.
              This may take 30+ minutes after DNS propagation.
              Check status: aws acm describe-certificate --certificate-arn ${aws_acm_certificate.main[0].arn}
    
    ───────────────────────────────────────────────────────────────────────────
    2. Application CNAME records (point to ALB)
    ───────────────────────────────────────────────────────────────────────────
    ${var.domain_name}          CNAME  ${aws_lb.main.dns_name}
    api.${var.domain_name}      CNAME  ${aws_lb.main.dns_name}
    odk.${var.domain_name}      CNAME  ${aws_lb.main.dns_name}
    
    ───────────────────────────────────────────────────────────────────────────
    3. What to tell your domain administrator:
    ───────────────────────────────────────────────────────────────────────────
    
    "Please create the following DNS records for our Glow deployment:
    
    For ACM certificate validation (temporary, can be removed after cert validates):
    ${join("\n    ", [for dvo in aws_acm_certificate.main[0].domain_validation_options : 
      format("%s  →  CNAME  →  %s", dvo.resource_record_name, dvo.resource_record_value)
    ])}
    
    For application access (permanent):
    ${var.domain_name}       →  CNAME  →  ${aws_lb.main.dns_name}
    api.${var.domain_name}   →  CNAME  →  ${aws_lb.main.dns_name}
    odk.${var.domain_name}   →  CNAME  →  ${aws_lb.main.dns_name}
    
    TTL: 300 seconds (5 minutes) is recommended for all records.
    "
    
    ═══════════════════════════════════════════════════════════════════════════
    
    EOT
  ) : "No domain configured"
}

output "acm_certificate_arn" {
  description = "ARN of the ACM certificate (for verification)"
  value       = var.domain_name != "" ? aws_acm_certificate.main[0].arn : null
}

output "acm_validation_status_command" {
  description = "AWS CLI command to check certificate validation status"
  value       = var.domain_name != "" && !var.manage_dns ? "aws acm describe-certificate --certificate-arn ${aws_acm_certificate.main[0].arn} --query 'Certificate.Status' --output text" : null
}
