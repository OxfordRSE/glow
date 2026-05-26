# CloudWatch log group for cloud-init logs
resource "aws_cloudwatch_log_group" "cloud_init" {
  name              = "/aws/ec2/cloud-init"
  retention_in_days = 7

  tags = local.tags
}
