data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

data "aws_subnet" "runner" {
  id = sort(data.aws_subnets.default.ids)[0]
}

resource "aws_security_group" "alb" {
  name        = "${var.app_name}-alb-sg"
  description = "Glow ALB security group"
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

resource "aws_security_group" "runner" {
  name        = "${var.app_name}-runner-sg"
  description = "Glow runner security group"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description     = "API from ALB"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  ingress {
    description     = "Dashboard from ALB"
    from_port       = 3000
    to_port         = 3000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  ingress {
    description     = "ODK from ALB"
    from_port       = 8080
    to_port         = 8080
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.tags
}

resource "aws_lb" "main" {
  name               = "${var.app_name}-alb"
  load_balancer_type = "application"
  internal           = false
  security_groups    = [aws_security_group.alb.id]
  subnets            = sort(data.aws_subnets.default.ids)

  tags = local.tags
}

resource "aws_lb_target_group" "api" {
  name        = "${var.app_name}-api-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = data.aws_vpc.default.id
  target_type = "instance"

  health_check {
    path    = "/health"
    matcher = "200"
  }

  tags = local.tags
}

resource "aws_lb_target_group" "dashboard" {
  name        = "${var.app_name}-dash-tg"
  port        = 3000
  protocol    = "HTTP"
  vpc_id      = data.aws_vpc.default.id
  target_type = "instance"

  health_check {
    path    = "/en"
    matcher = "200"
  }

  tags = local.tags
}

locals {
  # A hosted zone was found in this account for the domain (or a parent of
  # it): the certificate and DNS records can be fully managed here. Without
  # one (domain hosted elsewhere), fall back to a pasted-in certificate ARN
  # and leave DNS to whoever owns that domain.
  auto_dns        = var.hosted_zone_id != ""
  certificate_arn = local.auto_dns ? try(one(values(aws_acm_certificate_validation.main)).certificate_arn, "") : var.certificate_arn
}

resource "aws_acm_certificate" "main" {
  for_each = local.auto_dns ? toset(["main"]) : toset([])

  domain_name       = var.domain_name
  validation_method = "DNS"

  subject_alternative_names = [
    "api.${var.domain_name}",
    "odk.${var.domain_name}",
  ]

  lifecycle {
    create_before_destroy = true
  }

  tags = local.tags
}

resource "aws_route53_record" "cert_validation" {
  # Keys must be statically known at plan time, so derive them from the
  # domain names we already know (not from the certificate's
  # domain_validation_options, which is unknown until apply).
  for_each = local.auto_dns ? toset([var.domain_name, "api.${var.domain_name}", "odk.${var.domain_name}"]) : toset([])

  zone_id         = var.hosted_zone_id
  name            = one([for dvo in one(values(aws_acm_certificate.main)).domain_validation_options : dvo.resource_record_name if dvo.domain_name == each.key])
  type            = one([for dvo in one(values(aws_acm_certificate.main)).domain_validation_options : dvo.resource_record_type if dvo.domain_name == each.key])
  records         = [one([for dvo in one(values(aws_acm_certificate.main)).domain_validation_options : dvo.resource_record_value if dvo.domain_name == each.key])]
  ttl             = 60
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "main" {
  for_each = local.auto_dns ? toset(["main"]) : toset([])

  certificate_arn         = one(values(aws_acm_certificate.main)).arn
  validation_record_fqdns = [for record in aws_route53_record.cert_validation : record.fqdn]
}

resource "aws_route53_record" "app" {
  for_each = local.auto_dns ? toset(["", "api.", "odk."]) : toset([])

  zone_id         = var.hosted_zone_id
  name            = "${each.key}${var.domain_name}"
  type            = "A"
  allow_overwrite = true

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}

resource "aws_lb_target_group" "odk" {
  name        = "${var.app_name}-odk-tg"
  port        = 8080
  protocol    = "HTTP"
  vpc_id      = data.aws_vpc.default.id
  target_type = "instance"

  health_check {
    path    = "/alb-health"
    matcher = "200"
  }

  tags = local.tags
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"

    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }

  tags = local.tags
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = local.certificate_arn

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

resource "aws_lb_listener_rule" "https_dashboard" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 100

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

resource "aws_lb_listener_rule" "https_api" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 200

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

resource "aws_lb_listener_rule" "https_odk" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 300

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
