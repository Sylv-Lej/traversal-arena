# Infra Scaleway du site Traversal — PRÉPARÉE, PAS ENCORE DÉPLOYÉE.
# Tout est à lui : registre d'images, namespace de containers, base Lampion « traversal-prod »
# (voir le Makefile). Déploiement : `make deploy TAG=<sha>`.
# Base : projet Lampion `traversal` (DATABASE_URL, obligatoire). Backend sans état :
# plusieurs instances partagent la base et se parlent par Postgres LISTEN/NOTIFY.

terraform {
  # État sur Scaleway Object Storage (bucket créé par `make tfstate`, nom passé à
  # `terraform init` par le Makefile). Les identifiants S3 = clés Scaleway.
  backend "s3" {
    region                      = "fr-par"
    endpoint                    = "https://s3.fr-par.scw.cloud"
    skip_credentials_validation = true
    skip_region_validation      = true
    skip_metadata_api_check     = true
  }
  required_providers {
    scaleway = {
      source  = "scaleway/scaleway"
      version = "~> 2.48"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "scaleway" {
  region = var.region
  zone   = "${var.region}-1"
}

locals {
  name = "traversal"
  # Domaine du site (traversal-bot.app) : sert aussi à envoyer les emails. Vide = URL
  # Scaleway, et les variables mail_from / tem_* de .env.deploy (sans quoi, pas d'email).
  has_domain     = var.domain != ""
  public_url     = local.has_domain ? "https://${var.domain}" : var.public_url
  mail_from      = local.has_domain ? "noreply@${var.domain}" : var.mail_from
  tem_project_id = local.has_domain ? scaleway_tem_domain.mail[0].project_id : var.tem_project_id
  tem_secret_key = local.has_domain ? scaleway_iam_api_key.mailer[0].secret_key : var.tem_secret_key
}

# Clé partagée front(serveur) <-> API, jamais livrée au navigateur.
resource "random_password" "api_key" {
  length  = 48
  special = false
}

# Jeton du runner de l'arène (ARENA.md) : n'ouvre QUE l'API du runner (prendre une
# partie, la rendre), pas le reste de l'API.
resource "random_password" "arena_token" {
  length  = 48
  special = false
}

module "registry" {
  source = "./modules/registry"
  name   = var.registry_name
}

resource "scaleway_container_namespace" "main" {
  name = local.name
}

# --- Backend (FastAPI) ---
# Sans état : Scaleway ajoute des instances selon la charge (jusqu'à max_scale). Chaque
# instance ouvre au plus ~11 connexions Postgres (pool 5 + 5, + 1 d'écoute) : rester
# sous la limite de connexions de Lampion. Le bot calcule côté backend : 500 mCPU.
module "backend" {
  source       = "./modules/serverless-container"
  name         = "${local.name}-backend"
  namespace_id = scaleway_container_namespace.main.id
  image        = var.image_backend
  port         = 8000
  privacy      = var.privacy
  memory_limit = 512
  cpu_limit    = 500
  max_scale    = var.backend_max_scale

  environment_variables = {
    FRONTEND_ORIGIN = var.frontend_origin
    PUBLIC_URL      = local.public_url
    MAIL_FROM       = local.mail_from
    TEM_PROJECT_ID  = local.tem_project_id
    # Parties de l'arène consultables (relecture, rejeu sur l'accueil) : `services/arena.py`.
    ARENA_REPLAYS = var.arena_replays ? "1" : ""
  }
  secret_environment_variables = {
    DATABASE_URL   = var.database_url
    API_KEY        = random_password.api_key.result
    TEM_SECRET_KEY = local.tem_secret_key
    ARENA_TOKEN    = random_password.arena_token.result
  }
}

# --- Frontend (Next.js) ---
module "frontend" {
  source       = "./modules/serverless-container"
  name         = "${local.name}-frontend"
  namespace_id = scaleway_container_namespace.main.id
  image        = var.image_frontend
  port         = 3000
  privacy      = var.privacy
  memory_limit = 256
  cpu_limit    = 140
  max_scale    = var.frontend_max_scale # sans état, comme le backend

  environment_variables = {
    API_URL = module.backend.endpoint
    # Site complet (jouer, puzzles, regarder…) ou arène seule : `frontend/lib/site.ts`.
    FULL_SITE = var.full_site ? "1" : ""
  }
  secret_environment_variables = {
    API_KEY = random_password.api_key.result
  }
}

# --- Arène des bots : runner (Serverless Job) ---
# Joue les parties des bots WebAssembly envoyés par les joueurs (`traversal-arena work`),
# toutes les 30 min, jusqu'à ce que la file soit vide (ou 25 min). 0 € entre deux
# passages. Ses seuls accès : l'URL du backend et ARENA_TOKEN — pas la base, pas la clé
# d'API. Le backend rejoue et vérifie chaque partie rendue.
resource "scaleway_secret" "arena_token" {
  name = "${local.name}-arena-token"
}

resource "scaleway_secret_version" "arena_token" {
  secret_id = scaleway_secret.arena_token.id
  data      = random_password.arena_token.result
}

resource "scaleway_job_definition" "arena" {
  name                   = "${local.name}-arena"
  image_uri              = var.image_arena
  cpu_limit              = 1000 # mCPU : les parties sont jouées l'une après l'autre
  memory_limit           = 512  # MB : 2 bots × 64 Mo au plus, plus les modules compilés
  local_storage_capacity = 1000 # MB
  timeout                = "30m"
  env = {
    ARENA_API = module.backend.endpoint
  }
  secret_reference {
    secret_id      = scaleway_secret.arena_token.id
    secret_version = scaleway_secret_version.arena_token.revision
    environment    = "ARENA_TOKEN"
  }
  cron {
    schedule = var.arena_schedule
    timezone = "Europe/Paris"
  }
}

# --- Domaine : site + emails ---
# DNS chez Cloudflare (à poser à la main, voir l'output `dns_records`) :
# 1. AVANT le premier apply : CNAME du domaine vers le container frontend, en « DNS only »
#    (nuage gris) — Scaleway vérifie ce CNAME et émet lui-même le certificat HTTPS.
# 2. APRÈS : les enregistrements SPF / DKIM / DMARC du domaine d'envoi (TEM les vérifie
#    tout seul, les emails partent dès que le domaine est validé).
resource "scaleway_container_domain" "site" {
  count        = local.has_domain ? 1 : 0
  container_id = module.frontend.id
  hostname     = var.domain
}

resource "scaleway_tem_domain" "mail" {
  count      = local.has_domain ? 1 : 0
  name       = var.domain
  accept_tos = true
}

# Clé Scaleway DÉDIÉE à l'envoi d'emails (pas la clé d'admin) : si elle fuit, elle ne
# permet que d'envoyer des emails depuis ce domaine.
resource "scaleway_iam_application" "mailer" {
  count       = local.has_domain ? 1 : 0
  name        = "${local.name}-mailer"
  description = "Backend Traversal : envoi des emails (TEM) seulement"
}

resource "scaleway_iam_policy" "mailer" {
  count          = local.has_domain ? 1 : 0
  name           = "${local.name}-mailer"
  application_id = scaleway_iam_application.mailer[0].id
  rule {
    project_ids          = [scaleway_tem_domain.mail[0].project_id]
    permission_set_names = ["TransactionalEmailFullAccess"]
  }
}

resource "scaleway_iam_api_key" "mailer" {
  count              = local.has_domain ? 1 : 0
  application_id     = scaleway_iam_application.mailer[0].id
  default_project_id = scaleway_tem_domain.mail[0].project_id
  description        = "TEM_SECRET_KEY du backend Traversal"
}
