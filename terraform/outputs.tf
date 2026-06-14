# Wyniki dzialania Terraform - Stokklukeanalyse

output "ecr_repository_url" {
  description = "Adres URL rejestru Amazon ECR"
  value       = aws_ecr_repository.ecr_repo.repository_url
}

output "application_url" {
  description = "Publiczny adres URL wdrozonej aplikacji"
  value       = "http://${aws_lb.main.dns_name}"
}
