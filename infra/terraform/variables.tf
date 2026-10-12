variable "gcp_project_id" {
  type        = string
  description = "The Google Cloud Project ID to deploy resources into"
}

variable "gcp_region" {
  type        = string
  default     = "us-central1"
  description = "Always Free tier eligible region"
}

variable "gcp_zone" {
  type        = string
  default     = "us-central1-f"
}