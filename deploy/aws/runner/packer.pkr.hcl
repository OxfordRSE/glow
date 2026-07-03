packer {
  required_version = ">= 1.10.0"

  required_plugins {
    amazon = {
      source  = "github.com/hashicorp/amazon"
      version = ">= 1.3.0"
    }
  }
}

variable "aws_region" {
  type    = string
  default = "eu-west-2"
}

variable "runner_ami_version" {
  type = string
}

locals {
  ami_name = "glow-runner-${var.runner_ami_version}-${formatdate("YYYYMMDDhhmmss", timestamp())}"
}

source "amazon-ebs" "runner" {
  region        = var.aws_region
  instance_type = "t3.small"
  ssh_username  = "ec2-user"
  ami_name      = local.ami_name

  source_ami_filter {
    filters = {
      name                = "al2023-ami-*-x86_64"
      architecture        = "x86_64"
      root-device-type    = "ebs"
      virtualization-type = "hvm"
    }
    most_recent = true
    owners      = ["amazon"]
  }

  launch_block_device_mappings {
    device_name           = "/dev/xvda"
    volume_type           = "gp3"
    volume_size           = 30
    delete_on_termination = true
  }

  tags = {
    Name      = local.ami_name
    Component = "glow-runner"
    Version   = var.runner_ami_version
  }
}

build {
  sources = ["source.amazon-ebs.runner"]

  provisioner "shell" {
    execute_command = "sudo -E bash '{{ .Path }}'"
    script          = "./install-runner-deps.sh"
  }

  provisioner "file" {
    source      = "./bootstrap.sh"
    destination = "/tmp/bootstrap.sh"
  }

  provisioner "file" {
    source      = "./healthcheck.sh"
    destination = "/tmp/healthcheck.sh"
  }

  provisioner "shell" {
    inline = [
      "sudo mkdir -p /opt/glow-runner",
      "sudo mv /tmp/bootstrap.sh /opt/glow-runner/bootstrap.sh",
      "sudo mv /tmp/healthcheck.sh /opt/glow-runner/healthcheck.sh",
      "sudo chmod 0755 /opt/glow-runner/bootstrap.sh /opt/glow-runner/healthcheck.sh"
    ]
  }
}
