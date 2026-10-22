terraform {
  required_providers {
    scaleway = {
      source = "scaleway/scaleway"
    }
  }
}

# A single scale-to-zero Serverless Container. Cheap by default:
# min_scale = 0 means 0 € when idle.
resource "scaleway_container" "this" {
  name           = var.name
  namespace_id   = var.namespace_id
  image          = var.image
  port           = var.port
  privacy        = var.privacy

  min_scale    = var.min_scale
  max_scale    = var.max_scale
  cpu_limit    = var.cpu_limit    # mCPU
  memory_limit = var.memory_limit # MB

  environment_variables        = var.environment_variables
  secret_environment_variables = var.secret_environment_variables
}
