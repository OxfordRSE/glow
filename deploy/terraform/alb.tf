data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# ─── Application Load Balancer ───────────────────────────────────────────────

resource "aws_lb" "main" {
  name               = "${var.app_name}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = data.aws_subnets.default.ids

  tags = local.tags
}

# Target groups for each service
resource "aws_lb_target_group" "api" {
  name        = "${var.app_name}-api-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = data.aws_vpc.default.id
  target_type = "instance"

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    matcher             = "200"
  }

  tags = local.tags
}

resource "aws_lb_target_group" "dashboard" {
  name        = "${var.app_name}-dashboard-tg"
  port        = 3000
  protocol    = "HTTP"
  vpc_id      = data.aws_vpc.default.id
  target_type = "instance"

  health_check {
    path                = "/en"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    matcher             = "200"
  }

  tags = local.tags
}

resource "aws_lb_target_group" "odk" {
  name        = "${var.app_name}-odk-tg"
  port        = 8080
  protocol    = "HTTP"
  vpc_id      = data.aws_vpc.default.id
  target_type = "instance"

  health_check {
    path                = "/"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    matcher             = "200,302"
  }

  tags = local.tags
}

# Attach EC2 instance to target groups
resource "aws_lb_target_group_attachment" "api" {
  target_group_arn = aws_lb_target_group.api.arn
  target_id        = aws_instance.main.id
  port             = 8000
}

resource "aws_lb_target_group_attachment" "dashboard" {
  target_group_arn = aws_lb_target_group.dashboard.arn
  target_id        = aws_instance.main.id
  port             = 3000
}

resource "aws_lb_target_group_attachment" "odk" {
  target_group_arn = aws_lb_target_group.odk.arn
  target_id        = aws_instance.main.id
  port             = 8080
}

# HTTP listener: redirect to HTTPS when domain is configured
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = var.domain_name != "" ? "redirect" : "fixed-response"

    dynamic "redirect" {
      for_each = var.domain_name != "" ? [1] : []
      content {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }

    dynamic "fixed_response" {
      for_each = var.domain_name == "" ? [1] : []
      content {
        content_type = "text/plain"
        message_body = "Domain name not configured"
        status_code  = "503"
      }
    }
  }

  tags = local.tags
}

# HTTPS listener with host-based routing (only created when domain_name is set)
resource "aws_lb_listener" "https" {
  count             = var.domain_name != "" ? 1 : 0
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate_validation.main[0].certificate_arn

  # Default action: return 404
  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      message_body = "Not found"
      status_code  = "404"
    }
  }

  tags = local.tags
}

# Listener rules for subdomain routing
resource "aws_lb_listener_rule" "api" {
  count        = var.domain_name != "" ? 1 : 0
  listener_arn = aws_lb_listener.https[0].arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  condition {
    host_header {
      values = ["api.${var.domain_name}"]
    }
  }

  tags = local.tags
}

resource "aws_lb_listener_rule" "odk" {
  count        = var.domain_name != "" ? 1 : 0
  listener_arn = aws_lb_listener.https[0].arn
  priority     = 200

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.odk.arn
  }

  condition {
    host_header {
      values = ["odk.${var.domain_name}"]
    }
  }

  tags = local.tags
}

resource "aws_lb_listener_rule" "dashboard" {
  count        = var.domain_name != "" ? 1 : 0
  listener_arn = aws_lb_listener.https[0].arn
  priority     = 300

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.dashboard.arn
  }

  condition {
    host_header {
      values = [var.domain_name]
    }
  }

  tags = local.tags
}

# ─── Security groups ─────────────────────────────────────────────────────────

resource "aws_security_group" "alb" {
  name        = "${var.app_name}-alb-sg"
  description = "ALB security group"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.tags
}

# ─── Route 53 + ACM (only when domain_name is set) ───────────────────────────

# Look up the Route 53 hosted zone for the domain (only if manage_dns=true).
# Zone lookup: strips the leftmost label to find the parent zone.
#   e.g. "eu.glow-project.org" → looks for zone "glow-project.org"
# The hosted zone must already exist in Route 53 (or be delegated to AWS).
data "aws_route53_zone" "main" {
  count        = var.domain_name != "" && var.manage_dns ? 1 : 0
  name         = join(".", slice(split(".", var.domain_name), 1, length(split(".", var.domain_name))))
  private_zone = false
}

# Request an ACM certificate for the domain and subdomains (DNS validation)
resource "aws_acm_certificate" "main" {
  count             = var.domain_name != "" ? 1 : 0
  domain_name       = var.domain_name
  validation_method = "DNS"

  subject_alternative_names = [
    "api.${var.domain_name}",
    "odk.${var.domain_name}"
  ]

  lifecycle {
    create_before_destroy = true
  }

  tags = local.tags
}

# Create the DNS validation records in Route 53 (only if manage_dns=true)
resource "aws_route53_record" "cert_validation" {
  for_each = var.domain_name != "" && var.manage_dns ? {
    for dvo in aws_acm_certificate.main[0].domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  } : {}

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = data.aws_route53_zone.main[0].zone_id
}

# Wait for ACM certificate validation to complete (only if manage_dns=true)
resource "aws_acm_certificate_validation" "main" {
  count                   = var.domain_name != "" && var.manage_dns ? 1 : 0
  certificate_arn         = aws_acm_certificate.main[0].arn
  validation_record_fqdns = [for record in aws_route53_record.cert_validation : record.fqdn]
}

# DNS alias record pointing the root domain to the ALB (only if manage_dns=true)
resource "aws_route53_record" "main" {
  count   = var.domain_name != "" && var.manage_dns ? 1 : 0
  zone_id = data.aws_route53_zone.main[0].zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}

# DNS alias record for api subdomain (only if manage_dns=true)
resource "aws_route53_record" "api" {
  count   = var.domain_name != "" && var.manage_dns ? 1 : 0
  zone_id = data.aws_route53_zone.main[0].zone_id
  name    = "api.${var.domain_name}"
  type    = "A"

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}

# DNS alias record for odk subdomain (only if manage_dns=true)
resource "aws_route53_record" "odk" {
  count   = var.domain_name != "" && var.manage_dns ? 1 : 0
  zone_id = data.aws_route53_zone.main[0].zone_id
  name    = "odk.${var.domain_name}"
  type    = "A"

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}
