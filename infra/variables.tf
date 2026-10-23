variable "arena_replays" {
  type        = bool
  default     = false
  description = "Parties de l'arène consultables (relecture, rejeu sur l'accueil) ; false = résultats seuls."
}

variable "full_site" {
  type        = bool
  default     = false
  description = "Site complet (jouer en ligne, puzzles, regarder, classement des joueurs) ; false = arène seule."
}

variable "domain" {
  type        = string
  default     = ""
  description = "Domaine du site et des emails (ex. traversal-bot.app). Vide : URL Scaleway, pas d'email."
}

variable "region" {
  type    = string
  default = "fr-par"
}

variable "registry_name" {
  type    = string
  default = "traversal"
}

variable "image_backend" {
  type        = string
  description = "Full registry image ref for the backend, e.g. rg.fr-par.scw.cloud/revkit-.-backend:latest"
}

variable "image_arena" {
  type        = string
  description = "Image du runner de l'arène des bots (traversal-arena)"
}

variable "arena_schedule" {
  type        = string
  default     = "*/30 * * * *"
  description = "Passages du runner de l'arène (cron). Chaque passage s'arrête quand la file est vide."
}

variable "image_frontend" {
  type        = string
  description = "Full registry image ref for the frontend"
}

variable "database_url" {
  type        = string
  description = "Lampion Postgres connection string (postgresql://...)"
  sensitive   = true
}

variable "frontend_origin" {
  type        = string
  default     = ""
  description = <<-EOT
    Origine autorisée par le CORS du backend. Vide = aucune (défaut sûr) : le
    navigateur passe par la route serveur du front et n'appelle jamais l'API
    directement, donc aucune origine n'a besoin d'être ouverte. Ne remplir que pour
    autoriser explicitement un appel direct depuis un navigateur.
  EOT
}

variable "privacy" {
  type        = string
  default     = "public"
  description = "public = site en ligne ; private = hors ligne (403 pour tout le monde)."
  validation {
    condition     = contains(["public", "private"], var.privacy)
    error_message = "privacy doit valoir \"public\" ou \"private\"."
  }
}

# --- Emails (mot de passe oublié) via Scaleway Transactional Email -----------------
# Vides = aucun email envoyé (le lien est seulement écrit dans les logs du backend).
variable "public_url" {
  type        = string
  default     = ""
  description = "URL publique du site (liens dans les emails), ex. https://traversal.example.com"
}

variable "mail_from" {
  type        = string
  default     = ""
  description = "Expéditeur, sur un domaine vérifié dans Scaleway TEM (ex. noreply@traversal.example.com)"
}

variable "tem_secret_key" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Clé IAM Scaleway DÉDIÉE, limitée à TransactionalEmailFullAccess (pas la clé d'admin)"
}

variable "traversal_login" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Compte traversalgame.com qui lit les parties à importer (vide : import fermé)"
}

variable "traversal_password" {
  type      = string
  default   = ""
  sensitive = true
}

variable "tem_project_id" {
  type        = string
  default     = ""
  description = "Projet Scaleway où le domaine TEM est configuré"
}

variable "backend_max_scale" {
  description = "Instances max du backend (sans état : partagent la base Lampion)"
  type        = number
  default     = 3
}

variable "frontend_max_scale" {
  description = "Instances max du frontend"
  type        = number
  default     = 3
}
