# Definicja zmiennych Terraform - Stokklukeanalyse

variable "aws_region" {
  description = "Region AWS, w ktorym zostanie wdrozone rozwiazanie"
  type        = string
  default     = "eu-central-1" # Frankfurt
}

variable "project_name" {
  description = "Nazwa projektu, uzywana do oznaczania zasobow"
  type        = string
  default     = "stokklukka"
}
