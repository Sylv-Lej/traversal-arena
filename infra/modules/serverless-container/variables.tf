variable "name" { type = string }
variable "namespace_id" { type = string }
variable "image" { type = string }
variable "port" {
  type    = number
  default = 8000
}
variable "min_scale" {
  type    = number
  default = 0 # scale-to-zero
}
variable "max_scale" {
  type    = number
  default = 1
}
variable "cpu_limit" {
  type    = number
  default = 140 # mCPU
}
variable "memory_limit" {
  type    = number
  default = 256 # MB
}
variable "environment_variables" {
  type    = map(string)
  default = {}
}
variable "secret_environment_variables" {
  type      = map(string)
  default   = {}
  sensitive = true
}
variable "privacy" {
  type        = string
  default     = "public"
  description = "public = accessible par tous ; private = 403 sans token Scaleway (site hors ligne)."
}
