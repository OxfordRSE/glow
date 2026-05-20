resource "aws_ecs_cluster" "main" {
  name = var.app_name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = local.tags
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
  }
}

# IAM role for ECS task execution
resource "aws_iam_role" "ecs_task_execution" {
  name = "${var.app_name}-ecs-task-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })

  tags = local.tags
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Allow ECS to pull from ECR and write to CloudWatch
resource "aws_iam_role_policy" "ecs_task_execution_extra" {
  name = "${var.app_name}-ecs-extra"
  role = aws_iam_role.ecs_task_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["ssm:GetParameters", "secretsmanager:GetSecretValue"]
        Resource = "*"
      }
    ]
  })
}

# CloudWatch log group
resource "aws_cloudwatch_log_group" "main" {
  name              = "/ecs/${var.app_name}"
  retention_in_days = 30
  tags              = local.tags
}

# EFS for persistent data (API database + data files)
resource "aws_efs_file_system" "api_data" {
  creation_token = "${var.app_name}-api-data"
  encrypted      = true
  tags           = merge(local.tags, { Name = "${var.app_name}-api-data" })
}

resource "aws_efs_mount_target" "api_data" {
  for_each        = toset(data.aws_subnets.default.ids)
  file_system_id  = aws_efs_file_system.api_data.id
  subnet_id       = each.value
  security_groups = [aws_security_group.efs.id]
}

resource "aws_security_group" "efs" {
  name        = "${var.app_name}-efs-sg"
  description = "EFS security group"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port       = 2049
    to_port         = 2049
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.tags
}

# Nginx config stored in SSM Parameter Store
resource "aws_ssm_parameter" "nginx_conf" {
  name  = "/${var.app_name}/nginx-conf"
  type  = "String"
  value = file("${path.module}/../nginx-ecs.conf")
  tags  = local.tags
}

# Task definition
resource "aws_ecs_task_definition" "main" {
  family                   = var.app_name
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.container_cpu * 3  # three containers
  memory                   = var.container_memory * 3
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn

  volume {
    name = "api-data"
    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.api_data.id
      root_directory     = "/"
      transit_encryption = "ENABLED"
    }
  }

  container_definitions = jsonencode([
    {
      name      = "proxy"
      image     = "nginx:alpine"
      essential = true
      portMappings = [{
        containerPort = 80
        hostPort      = 80
        protocol      = "tcp"
      }]
      dependsOn = [
        { containerName = "api", condition = "HEALTHY" },
        { containerName = "dashboard", condition = "START" }
      ]
      environment = []
      mountPoints = []
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.main.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "proxy"
        }
      }
    },
    {
      name      = "api"
      image     = "${aws_ecr_repository.api.repository_url}:${var.image_tag}"
      essential = true
      portMappings = [{
        containerPort = 8000
        hostPort      = 8000
        protocol      = "tcp"
      }]
      environment = [
        { name = "GLOW_DATA_PATH", value = "/data/data.csv" },
        { name = "GLOW_MIN_N", value = tostring(var.api_min_n) },
        { name = "GLOW_SECRET_KEY", value = var.api_secret_key },
        { name = "GLOW_DATABASE_URL", value = "sqlite:////data/auth.db" },
        { name = "GLOW_CORS_ORIGINS", value = jsonencode(["*"]) }
      ]
      mountPoints = [{
        sourceVolume  = "api-data"
        containerPath = "/data"
        readOnly      = false
      }]
      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 15
      }
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.main.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "api"
        }
      }
    },
    {
      name      = "dashboard"
      image     = "${aws_ecr_repository.dashboard.repository_url}:${var.image_tag}"
      essential = true
      portMappings = [{
        containerPort = 3000
        hostPort      = 3000
        protocol      = "tcp"
      }]
      environment = [
        { name = "NODE_ENV", value = "production" }
      ]
      mountPoints = []
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.main.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "dashboard"
        }
      }
    }
  ])

  tags = local.tags
}

# ECS Service
resource "aws_ecs_service" "main" {
  name                               = var.app_name
  cluster                            = aws_ecs_cluster.main.id
  task_definition                    = aws_ecs_task_definition.main.arn
  desired_count                      = var.desired_count
  launch_type                        = "FARGATE"
  health_check_grace_period_seconds  = 60

  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.main.arn
    container_name   = "proxy"
    container_port   = 80
  }

  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }

  tags = local.tags
}
