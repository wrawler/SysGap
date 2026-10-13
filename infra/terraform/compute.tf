resource "azurerm_log_analytics_workspace" "app" {
  name                = "${var.project_name}-logs"
  location            = azurerm_resource_group.app.location
  resource_group_name = azurerm_resource_group.app.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

resource "azurerm_container_app_environment" "app" {
  name                       = "${var.project_name}-env"
  location                   = azurerm_resource_group.app.location
  resource_group_name        = azurerm_resource_group.app.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.app.id
}

resource "azurerm_container_app" "api" {
  name                         = "${var.project_name}-api"
  container_app_environment_id = azurerm_container_app_environment.app.id
  resource_group_name          = azurerm_resource_group.app.name
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server               = var.container_registry_server
    username             = var.container_registry_username
    password_secret_name = "registry-password"
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "auto"
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  secret {
    name  = "registry-password"
    value = var.container_registry_password
  }

  template {
    min_replicas = 0
    max_replicas = 2

    container {
      name   = "api"
      image  = var.container_image
      cpu    = var.container_cpu
      memory = var.container_memory

      env {
        name  = "AZURE_STORAGE_ACCOUNT_URL"
        value = azurerm_storage_account.app.primary_blob_endpoint
      }
      env {
        name  = "AZURE_TABLE_ACCOUNT_URL"
        value = azurerm_storage_account.app.primary_table_endpoint
      }
      env {
        name  = "AZURE_BLOB_CONTAINER"
        value = azurerm_storage_container.reports.name
      }
      env {
        name  = "AZURE_TABLE_NAME"
        value = azurerm_storage_table.reports.name
      }
    }

    http_scale_rule {
      name                = "http"
      concurrent_requests = "20"
    }
  }
}
