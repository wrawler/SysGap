resource "azurerm_resource_group" "app" {
  name     = "${var.project_name}-rg"
  location = var.location
}

resource "azurerm_storage_account" "app" {
  name                      = substr(replace("${var.project_name}${random_string.suffix.result}", "-", ""), 0, 24)
  resource_group_name       = azurerm_resource_group.app.name
  location                  = azurerm_resource_group.app.location
  account_tier              = "Standard"
  account_replication_type  = "LRS"
  min_tls_version           = "TLS1_2"
  shared_access_key_enabled = true
}

resource "azurerm_storage_container" "reports" {
  name                  = "reports"
  storage_account_id    = azurerm_storage_account.app.id
  container_access_type = "private"
}

resource "azurerm_storage_table" "reports" {
  name                 = "Reports"
  storage_account_name = azurerm_storage_account.app.name
}

resource "azurerm_role_assignment" "blob_reports" {
  scope                = azurerm_storage_account.app.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

resource "azurerm_role_assignment" "table_reports" {
  scope                = azurerm_storage_account.app.id
  role_definition_name = "Storage Table Data Contributor"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

resource "azurerm_user_assigned_identity" "app" {
  name                = "${var.project_name}-identity"
  location            = azurerm_resource_group.app.location
  resource_group_name = azurerm_resource_group.app.name
}

resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}
