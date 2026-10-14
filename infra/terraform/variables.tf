variable "location" {
  type        = string
  default     = "eastus"
  description = "Azure region for the low-cost deployment."
}

variable "project_name" {
  type    = string
  default = "sysgap"
}

variable "container_image" {
  type        = string
  description = "Published backend image, including its tag."
}

variable "container_cpu" {
  type    = number
  default = 0.25
}

variable "container_memory" {
  type    = string
  default = "0.5Gi"
}

variable "container_registry_server" {
  type        = string
  description = "Container registry server, for example sysgap.azurecr.io."
}

variable "container_registry_username" {
  type      = string
  sensitive = true
}

variable "container_registry_password" {
  type      = string
  sensitive = true
}

variable "frontend_location" {
  type        = string
  default     = "eastasia"
  description = "Azure Static Web App region permitted by the subscription policy."
}

variable "frontend_custom_domain" {
  type        = string
  default     = ""
  description = "Optional custom hostname, such as app.example.com."
}

variable "frontend_api_url" {
  type        = string
  description = "Public API origin used by the static frontend."
}

variable "allowed_frontend_origins" {
  type        = string
  description = "Comma-separated origins allowed by the API CORS policy."
}
