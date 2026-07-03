output "runner_codebuild_project_name" {
  value = aws_codebuild_project.runner.name
}

output "runner_codebuild_log_group_name" {
  value = aws_cloudwatch_log_group.runner_codebuild.name
}
