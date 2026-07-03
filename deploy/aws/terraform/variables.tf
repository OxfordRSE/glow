variable "app_name" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "certificate_arn" {
  type = string
}

variable "domain_name" {
  type = string
}

variable "git_repo_url" {
  type = string
}

variable "git_checkout_ref" {
  type = string
}

variable "runner_ami_version" {
  type = string
}

variable "runner_instance_type" {
  type = string
}

variable "runner_root_volume_size_gb" {
  type = number
}

variable "data_volume_size_gb" {
  type = number
}
