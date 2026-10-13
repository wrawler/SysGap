variable "location" {
  type        = string
  default     = "eastus"
  description = "Azure region for the low-cost deployment."
}

variable "project_name" {
  type    = string
  default = "pricerig"
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
  description = "Container registry server, for example pricerig.azurecr.io."
}

variable "container_registry_username" {
  type      = string
  sensitive = true
}

variable "container_registry_password" {
  type      = string
  sensitive = true
}
