# Konfiguracja Terraform - Stokklukeanalyse AWS Infrastructure

terraform {
  required_version = ">= 1.0.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# --- 1. SIEĆ (VPC & SUBNETS) ---
# Tworzymy dedykowane VPC dla izolacji
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags = {
    Name = "${var.project_name}-vpc"
  }
}

# Pobieramy dostępne strefy dostępności (Availability Zones)
data "aws_availability_zones" "available" {
  state = "available"
}

# Podsieć publiczna 1 (Strefa A)
resource "aws_subnet" "public_1" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true
  tags = {
    Name = "${var.project_name}-public-subnet-1"
  }
}

# Podsieć publiczna 2 (Strefa B)
resource "aws_subnet" "public_2" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.2.0/24"
  availability_zone       = data.aws_availability_zones.available.names[1]
  map_public_ip_on_launch = true
  tags = {
    Name = "${var.project_name}-public-subnet-2"
  }
}

# Brama internetowa (Internet Gateway)
resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id
  tags = {
    Name = "${var.project_name}-igw"
  }
}

# Tabela routingu dla podsieci publicznych
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }
  tags = {
    Name = "${var.project_name}-public-rt"
  }
}

# Powiązanie tabeli routingu z podsiecią 1
resource "aws_route_table_association" "public_1" {
  subnet_id      = aws_subnet.public_1.id
  route_table_id = aws_route_table.public.id
}

# Powiązanie tabeli routingu z podsiecią 2
resource "aws_route_table_association" "public_2" {
  subnet_id      = aws_subnet.public_2.id
  route_table_id = aws_route_table.public.id
}


# --- 2. BEZPIECZEŃSTWO (SECURITY GROUPS) ---
# Grupa bezpieczeństwa dla Load Balancera (ALB)
resource "aws_security_group" "alb" {
  name        = "${var.project_name}-alb-sg"
  description = "Zezwala na ruch HTTP z calego internetu"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-alb-sg"
  }
}

# Grupa bezpieczeństwa dla kontenera ECS Fargate
resource "aws_security_group" "ecs_tasks" {
  name        = "${var.project_name}-ecs-tasks-sg"
  description = "Zezwala na ruch HTTP tylko z Load Balancera (ALB)"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-ecs-tasks-sg"
  }
}


# --- 3. REPOZYTORIUM OBRAZÓW (AMAZON ECR) ---
resource "aws_ecr_repository" "ecr_repo" {
  name                 = var.project_name
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
  force_delete = true # Pozwala na latwe usuniecie ECR razem z obrazami przy terraform destroy
}


# --- 4. LOAD BALANCER (ALB) ---
# Application Load Balancer
resource "aws_lb" "main" {
  name               = "${var.project_name}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = [aws_subnet.public_1.id, aws_subnet.public_2.id]
  tags = {
    Name = "${var.project_name}-alb"
  }
}

# Grupa docelowa (Target Group)
resource "aws_lb_target_group" "app" {
  name        = "${var.project_name}-tg"
  port        = 80
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip" # Wymagane dla ECS Fargate

  health_check {
    path                = "/health" # Nasz endpoint /health!
    protocol            = "HTTP"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 3
    unhealthy_threshold = 3
  }
}

# Listener kierujący ruch z portu 80 do Target Group
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}


# --- 5. ROLA IAM DLA ECS ---
# Rola wykonawcza dla ECS (do pobierania obrazu z ECR i zapisu logów w CloudWatch)
resource "aws_iam_role" "ecs_execution_role" {
  name = "${var.project_name}-ecs-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

# Podłączenie standardowych uprawnień do roli wykonawczej ECS
resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Rola zadania ECS (dla samego uruchomionego kontenera)
resource "aws_iam_role" "ecs_task_role" {
  name = "${var.project_name}-ecs-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}


# --- 6. OBSERWOWALNOŚĆ (CLOUDWATCH LOGS) ---
resource "aws_cloudwatch_log_group" "log_group" {
  name              = "/ecs/${var.project_name}"
  retention_in_days = 7 # Przechowuj logi przez 7 dni (wystarczajace i tanie)
}


# --- 7. USŁUGA ECS (CLUSTER, TASK & SERVICE) ---
# Klaster ECS
resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster"
}

# Definicja Zadania (Task Definition)
resource "aws_ecs_task_definition" "app" {
  family                   = "${var.project_name}-task"
  network_mode             = "awsvpc" # Wymagane dla Fargate
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"  # 0.25 vCPU (Najmniejsza i najtansza opcja)
  memory                   = "512"  # 512 MB RAM (Najmniejsza i najtansza opcja)
  execution_role_arn       = aws_iam_role.ecs_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
    {
      name      = var.project_name
      image     = "${aws_ecr_repository.ecr_repo.repository_url}:latest"
      essential = true
      portMappings = [
        {
          containerPort = 80
          hostPort      = 80
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.log_group.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "app"
        }
      }
    }
  ])
}

# Usługa ECS Fargate (ECS Service)
resource "aws_ecs_service" "main" {
  name            = "${var.project_name}-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  launch_type     = "FARGATE"
  desired_count   = 1 # Uruchamiamy 1 replike kontenera

  network_configuration {
    security_groups  = [aws_security_group.ecs_tasks.id]
    subnets          = [aws_subnet.public_1.id, aws_subnet.public_2.id]
    assign_public_ip = true # Kluczowe dla Fargate w publicznej podsieci bez NAT!
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = var.project_name
    container_port   = 80
  }

  # Ignoruj zmiany obrazu (GitHub Actions bedzie aktualizowac wersje, nie chcemy konfliktow w Terraformie)
  lifecycle {
    ignore_changes = [task_definition]
  }

  depends_on = [aws_lb_listener.http]
}
