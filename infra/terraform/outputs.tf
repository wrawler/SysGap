output "api_url" {
  description = "Public URL for the API container app."
  value       = "https://${azurerm_container_app.api.ingress[0].fqdn}"
}

output "storage_account_name" {
  value = azurerm_storage_account.app.name
}

output "frontend_url" {
  description = "Default HTTPS URL for the Static Web App frontend."
  value       = "https://${azurerm_static_web_app.frontend.default_host_name}"
}

output "frontend_deployment_token" {
  description = "Deployment token for the Static Web App GitHub action."
  value       = azurerm_static_web_app.frontend.api_key
  sensitive   = true
}
