data "aws_ami" "runner" {
  owners      = ["self"]
  most_recent = true

  filter {
    name   = "tag:Component"
    values = ["glow-runner"]
  }

  filter {
    name   = "tag:Version"
    values = [var.runner_ami_version]
  }
}

resource "aws_ebs_volume" "data" {
  availability_zone = data.aws_subnet.runner.availability_zone
  size              = var.data_volume_size_gb
  type              = "gp3"
  encrypted         = true

  tags = merge(local.tags, {
    Name      = "${var.app_name}-data"
    Component = "glow-data"
  })
}

resource "aws_iam_role" "runner" {
  name = "${var.app_name}-runner-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "sts:AssumeRole"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = local.tags
}

resource "aws_iam_role_policy_attachment" "runner_ssm" {
  role       = aws_iam_role.runner.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "runner_cloudwatch" {
  role       = aws_iam_role.runner.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

resource "aws_iam_instance_profile" "runner" {
  name = "${var.app_name}-runner-profile"
  role = aws_iam_role.runner.name
}

resource "aws_launch_template" "runner" {
  name_prefix            = "${var.app_name}-runner-"
  image_id               = data.aws_ami.runner.id
  instance_type          = var.runner_instance_type
  update_default_version = true

  iam_instance_profile {
    name = aws_iam_instance_profile.runner.name
  }

  vpc_security_group_ids = [aws_security_group.runner.id]

  block_device_mappings {
    device_name = "/dev/xvda"

    ebs {
      volume_type           = "gp3"
      volume_size           = var.runner_root_volume_size_gb
      encrypted             = true
      delete_on_termination = true
    }
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  user_data = base64encode(templatefile(
    "${path.module}/../templates/runner-userdata.sh.tpl",
    {
      aws_region                      = var.aws_region
      domain_name                     = var.domain_name
      git_repo_url                    = var.git_repo_url
      git_checkout_ref                = var.git_checkout_ref
      cloudwatch_bootstrap_log_group  = aws_cloudwatch_log_group.bootstrap.name
      cloudwatch_containers_log_group = aws_cloudwatch_log_group.containers.name
      cloudwatch_system_log_group     = aws_cloudwatch_log_group.system.name
    }
  ))

  tag_specifications {
    resource_type = "instance"
    tags = merge(local.tags, {
      Name      = "${var.app_name}-runner"
      Component = "glow-runner"
      Version   = var.runner_ami_version
    })
  }

  tag_specifications {
    resource_type = "volume"
    tags          = local.tags
  }

  tags = local.tags
}
