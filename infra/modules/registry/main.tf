terraform {
  required_providers {
    scaleway = {
      source = "scaleway/scaleway"
    }
  }
}

# Container Registry namespace. Push images here, then reference them from containers.
resource "scaleway_registry_namespace" "this" {
  name      = var.name
  is_public = false
}
