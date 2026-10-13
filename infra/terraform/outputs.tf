output "api_url" {
  description = "Public URL for the API container app."
  value       = "https://${azurerm_container_app.api.ingress[0].fqdn}"
}

output "storage_account_name" {
  value = azurerm_storage_account.app.name
}
