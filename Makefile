# Traversal — dev local et déploiement Scaleway.
#
#   make help                 # liste les cibles
#   make dev                  # backend + frontend local (Docker, DB Lampion)
#   make dev-back             # backend local (DB Lampion, uploads ./uploads)
#   make dev-front            # frontend local
#   make deploy TAG=<sha>     # build + push + terraform apply (bout en bout)
#
# Secrets : ./.env.deploy (gitignoré, modèle .env.deploy.example).
# La DB est TOUJOURS Lampion : DATABASE_URL est résolu automatiquement (projet créé
# si absent) à partir de la seule LAMPION_API_KEY. Override possible en fixant DATABASE_URL.

# Nom du site : préfixe des images, projet Lampion du dev, clé de l'état Terraform.
# Ne pas changer sans migrer l'infra déployée.
SITE     := traversal
REGION   ?= fr-par
LAMPION_REGION ?= fr-par-1
# TAG : utiliser un sha git (ex. $(git rev-parse --short HEAD)) pour forcer un redeploy.
TAG      ?= latest
INFRA    := infra
ENV_FILE := .env.deploy

# Charge et exporte les secrets (SCW_*, S3_*, LAMPION_API_KEY, DATABASE_URL) s'ils existent.
-include $(ENV_FILE)
export

# Les noms de registre et de bucket doivent être uniques chez Scaleway : suffixés par le
# début de l'id du projet Scaleway.
PROJECT8 = $(shell printf '%s' "$(SCW_DEFAULT_PROJECT_ID)" | cut -c1-8)
REGISTRY_NAME ?= traversal-$(PROJECT8)
REGISTRY_HOST ?= rg.$(REGION).scw.cloud
REGISTRY ?= $(REGISTRY_HOST)/$(REGISTRY_NAME)
# État Terraform sur Object Storage (bucket privé, versionné), créé par `make tfstate`.
TF_STATE_BUCKET ?= traversal-tfstate-$(PROJECT8)
# Projet Lampion du dev local (« traversal »), et base de PROD séparée (« traversal-prod »).
LAMPION_PROJECT      ?= $(SITE)
LAMPION_PROJECT_PROD ?= traversal-prod
LAMPION_NAME = $(LAMPION_PROJECT)

# Domaine du site ET des emails : avec lui, Terraform crée tout seul le domaine d'envoi
# (TEM) et sa clé dédiée — plus rien à remplir pour les emails. Les quatre variables
# ci-dessous ne servent que sans domaine.
TF_VAR_domain = traversal-bot.app
# Arène seule tant que false. Rouvrir tout le site (sans rebuild, le front relit la
# variable à chaque requête) : `make apply TF_VAR_full_site=true TAG=<tag actuel>`.
TF_VAR_full_site ?= false
# Parties de l'arène consultables (relecture, rejeu sur l'accueil) ; false = résultats seuls.
# Ouvrir : `make apply TF_VAR_arena_replays=true TAG=<tag actuel>`.
TF_VAR_arena_replays ?= false
# Emails (mot de passe oublié) et URL publique : à remplir dans .env.deploy quand le
# domaine est prêt. Passés à Terraform par l'environnement (jamais en ligne de commande).
TF_VAR_public_url     = $(PUBLIC_URL)
TF_VAR_mail_from      = $(MAIL_FROM)
TF_VAR_tem_project_id = $(TEM_PROJECT_ID)
TF_VAR_tem_secret_key = $(TEM_SECRET_KEY)

# Assure le projet Lampion (le crée via l'API si absent) et renvoie la connection string.
# Ne dépend QUE de LAMPION_API_KEY (+ docker) : script stdlib exécuté dans un conteneur python.
LAMPION_ENSURE = docker run --rm \
	  -e LAMPION_API_KEY -e LAMPION_PROJECT_NAME="$(LAMPION_NAME)" -e LAMPION_REGION="$(LAMPION_REGION)" \
	  -e LAMPION_API_BASE \
	  -v "$(CURDIR)/infra/scripts:/scripts:ro" \
	  python:3.12-slim python /scripts/lampion_ensure_db.py
# Résout DATABASE_URL : override manuel s'il est déjà défini, sinon via Lampion.
RESOLVE_DB = DATABASE_URL="$${DATABASE_URL:-$$($(LAMPION_ENSURE))}"

# Scaleway Serverless Containers n'accepte QUE amd64 : sur Mac Apple Silicon un
# `docker build` nu produit de l'arm64 et le container part en status "error".
PLATFORM ?= linux/amd64
IMG_BACK  := $(REGISTRY)/$(SITE)-backend:$(TAG)
IMG_FRONT := $(REGISTRY)/$(SITE)-frontend:$(TAG)
IMG_ARENA := $(REGISTRY)/$(SITE)-arena:$(TAG)

# Les clés Scaleway servent aussi de clés S3 (état Terraform distant sur Object Storage).
TF     := AWS_ACCESS_KEY_ID="$(SCW_ACCESS_KEY)" AWS_SECRET_ACCESS_KEY="$(SCW_SECRET_KEY)" terraform -chdir=$(INFRA)
# database_url est injecté par recipe (résolu via Lampion), pas ici.
TFVARS := \
  -var="image_backend=$(IMG_BACK)" \
  -var="image_frontend=$(IMG_FRONT)" \
  -var="image_arena=$(IMG_ARENA)" \
  -var="region=$(REGION)" \
  -var="registry_name=$(REGISTRY_NAME)"

ARENA_TOKEN ?= dev-arena-token-not-a-secret

# Tout ce qui touche à l'infra déployée utilise la base de PROD.
registry plan apply offline online down destroy deploy redeploy db-prod arena-rotate-token: LAMPION_NAME = $(LAMPION_PROJECT_PROD)

.DEFAULT_GOAL := help

.PHONY: help
help: ## Affiche cette aide
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n",$$1,$$2}'

# --- Secrets -----------------------------------------------------------------
.PHONY: secrets
secrets: ## Vérifie la présence de ./.env.deploy
	@test -f $(ENV_FILE) || { echo "❌ Manque $(ENV_FILE) — copie .env.deploy.example puis remplis-le."; exit 1; }

# --- Dev local (100% Docker, aucun outil requis sur l'hôte) ------------------
.PHONY: dev dev-back dev-front dev-down
dev: secrets ## Lance backend + frontend en local (Docker, hot-reload, DB Lampion auto)
	@set -e; $(RESOLVE_DB); export DATABASE_URL; docker compose up

dev-back: secrets ## Lance le backend seul (DB Lampion auto, uploads ./uploads)
	@set -e; $(RESOLVE_DB); export DATABASE_URL; docker compose up backend

dev-front: ## Lance le frontend seul (pas de DB)
	docker compose up frontend

dev-down: ## Stoppe le stack local et supprime les volumes (node_modules, venv)
	docker compose down -v

# --- Base de données Lampion -------------------------------------------------
.PHONY: db db-prod
db: ## Assure le projet Lampion (créé si absent) et affiche DATABASE_URL
	@echo "DATABASE_URL=$$($(LAMPION_ENSURE))"

db-prod: ## Idem pour la base de prod (LAMPION_PROJECT_PROD)
	@echo "DATABASE_URL=$$($(LAMPION_ENSURE))"

# --- Images ------------------------------------------------------------------
.PHONY: login build build-back build-front build-arena push push-arena arena-audit
login: ## Login Docker sur le registre Scaleway
	@echo "$(SCW_SECRET_KEY)" | docker login $(REGISTRY_HOST) -u nologin --password-stdin

# --provenance=false : sans ça, buildx (Docker Desktop) pousse un INDEX OCI multi-manifestes
# avec une entrée d'attestation "unknown/unknown". Scaleway Serverless Containers ne sait pas
# lire cet index et rejette l'image ("Invalid Image architecture"). On force un manifeste unique.
build-back: ## Build l'image backend
	docker build --provenance=false --platform=$(PLATFORM) -f backend/Dockerfile -t $(IMG_BACK) .

build-front: ## Build l'image frontend
	docker build --provenance=false --platform=$(PLATFORM) -f frontend/Dockerfile -t $(IMG_FRONT) frontend

# Failles publiées (RustSec) dans les dépendances du runner : wasmtime est la barrière
# entre les bots et la machine, il doit rester à jour. Lancé avant chaque build-arena.
arena-audit: ## Vérifie qu'aucune faille connue ne touche le runner de l'arène (cargo audit)
	docker run --rm -v "$(abspath engine-rs)":/w -v trav-cargo:/usr/local/cargo/registry -w /w/arena \
	  rust:1.88-slim sh -c 'cargo install -q cargo-audit --locked >/dev/null 2>&1; cargo audit'

build-arena: arena-audit ## Build l'image du runner de l'arène (traversal-arena + bots maison)
	docker build --provenance=false --platform=$(PLATFORM) -f engine-rs/arena/Dockerfile -t $(IMG_ARENA) engine-rs

build: secrets build-back build-front build-arena ## Build les trois images

push: login push-arena ## Push les trois images
	docker push $(IMG_BACK)
	docker push $(IMG_FRONT)

push-arena: login
	docker push $(IMG_ARENA)

# --- Terraform ---------------------------------------------------------------
.PHONY: init registry plan apply output destroy
init: tfstate ## terraform init (état distant sur Object Storage)
	$(TF) init -input=false -reconfigure -backend-config="bucket=$(TF_STATE_BUCKET)" -backend-config="key=$(SITE)/terraform.tfstate"

# État Terraform sur Object Storage (bucket privé et versionné), créé une fois.
.PHONY: tfstate
tfstate:
	@docker run --rm -e AWS_ACCESS_KEY_ID="$(SCW_ACCESS_KEY)" -e AWS_SECRET_ACCESS_KEY="$(SCW_SECRET_KEY)" \
	  -e AWS_DEFAULT_REGION=$(REGION) amazon/aws-cli --endpoint-url https://s3.$(REGION).scw.cloud \
	  s3api head-bucket --bucket $(TF_STATE_BUCKET) >/dev/null 2>&1 && echo "🗄  état Terraform : s3://$(TF_STATE_BUCKET)" || { \
	  docker run --rm -e AWS_ACCESS_KEY_ID="$(SCW_ACCESS_KEY)" -e AWS_SECRET_ACCESS_KEY="$(SCW_SECRET_KEY)" \
	    -e AWS_DEFAULT_REGION=$(REGION) amazon/aws-cli --endpoint-url https://s3.$(REGION).scw.cloud \
	    s3api create-bucket --bucket $(TF_STATE_BUCKET) >/dev/null && \
	  docker run --rm -e AWS_ACCESS_KEY_ID="$(SCW_ACCESS_KEY)" -e AWS_SECRET_ACCESS_KEY="$(SCW_SECRET_KEY)" \
	    -e AWS_DEFAULT_REGION=$(REGION) amazon/aws-cli --endpoint-url https://s3.$(REGION).scw.cloud \
	    s3api put-bucket-versioning --bucket $(TF_STATE_BUCKET) --versioning-configuration Status=Enabled && \
	  echo "🗄  bucket d'état Terraform créé : s3://$(TF_STATE_BUCKET)"; }

registry: ## Crée uniquement le registre (pré-requis au push)
	@set -e; $(RESOLVE_DB); $(TF) apply -auto-approve -target=module.registry $(TFVARS) -var="database_url=$$DATABASE_URL"

plan: ## terraform plan
	@set -e; $(RESOLVE_DB); $(TF) plan $(TFVARS) -var="database_url=$$DATABASE_URL"

apply: ## terraform apply (containers + registre + job de l'arène)
	@set -e; $(RESOLVE_DB); $(TF) apply -auto-approve $(TFVARS) -var="database_url=$$DATABASE_URL"

output: ## Affiche les URLs déployées
	$(TF) output

# --- Mise hors ligne / remise en ligne ---------------------------------------
.PHONY: offline online
offline: ## Rend le site + l'API inaccessibles (containers en privacy=private, réversible)
	@set -e; $(RESOLVE_DB); $(TF) apply -auto-approve $(TFVARS) -var="database_url=$$DATABASE_URL" \
	  -var="privacy=private"
	@echo "🔒 $(SITE) hors ligne : les URLs publiques renvoient 403."

online: ## Remet le site + l'API en ligne
	@set -e; $(RESOLVE_DB); $(TF) apply -auto-approve $(TFVARS) -var="database_url=$$DATABASE_URL" \
	  -var="privacy=public"
	@echo "🌍 $(SITE) de nouveau en ligne :" && $(TF) output

.PHONY: down
down: ## Supprime uniquement les 2 containers (garde DB et registre)
	@set -e; $(RESOLVE_DB); $(TF) destroy -auto-approve -target=module.backend -target=module.frontend $(TFVARS) -var="database_url=$$DATABASE_URL"

destroy: ## Détruit toute l'infra du site
	@set -e; $(RESOLVE_DB); $(TF) destroy $(TFVARS) -var="database_url=$$DATABASE_URL"

# --- Déploiement bout en bout ------------------------------------------------
# Un seul `apply` suffit : l'URL du backend est passée au front en variable
# d'environnement RUNTIME (résolue par Terraform dans le même apply).
.PHONY: deploy redeploy
deploy: secrets init registry build push apply ## Déploiement complet (1 commande)
	@echo "✅ $(SITE) déployé :" && $(TF) output

redeploy: build push apply ## Redéploie le code (utiliser TAG=$$(git rev-parse --short HEAD))
	@echo "ℹ️  avec TAG=latest, Scaleway ne redéploie pas : passe un TAG unique."

# --- Arène : dev local et jeton du runner ------------------------------------
.PHONY: arena-dev arena-rotate-token
arena-dev: ## Joue les parties de l'arène contre le backend local (make dev), en boucle
	docker build -f engine-rs/arena/Dockerfile -t traversal-arena engine-rs
	docker run --rm --add-host=host.docker.internal:host-gateway -e ARENA_TOKEN="$(ARENA_TOKEN)" \
	  traversal-arena work --api http://host.docker.internal:8000 --forever

# Fuite (ou doute) : un nouveau jeton aléatoire est tiré et posé partout en un `apply`
# (secret du backend, Secret Manager, référence du Job). L'ancien ne vaut plus rien dès
# que le backend a redémarré avec le nouveau.
arena-rotate-token: ## Renouvelle ARENA_TOKEN (fuite ?) : backend et runner reçoivent le nouveau
	@set -e; $(RESOLVE_DB); $(TF) apply -auto-approve -replace=random_password.arena_token $(TFVARS) -var="database_url=$$DATABASE_URL"

# --- SDK des bots : dépôt public (miroir) ---------------------------------------------
# traversal-core + traversal-bot + bots d'exemple + runner, recopiés depuis engine-rs (la
# référence reste ici). Les auteurs de bots dépendent du dépôt git, à un tag :
#   traversal-bot = { git = "https://github.com/Sylv-Lej/traversal-rust-sdk", tag = "vX.Y.Z" }
SDK_REPO ?= ../traversal-rust-sdk
SDK_VERSION = $(shell sed -n 's/^version = "\(.*\)"$$/\1/p' engine-rs/Cargo.toml | head -1)
SDK_RUST = docker run --rm -v "$(abspath $(SDK_REPO))":/w -v trav-cargo:/usr/local/cargo/registry -w /w

.PHONY: sdk-sync sdk-check sdk-push sdk-publish
sdk-sync: ## Recopie le SDK des bots dans SDK_REPO (../traversal-rust-sdk), sans commit
	sh engine-rs/scripts/sync_sdk.sh $(SDK_REPO)

sdk-check: sdk-sync ## sdk-sync, puis tests, bots d'exemple en WASM et runner, dans le dépôt du SDK
	$(SDK_RUST) rust:1.88-slim sh -c 'rustup target add wasm32-unknown-unknown >/dev/null 2>&1 && \
	  cargo test -q -p traversal-core -p traversal-bot && \
	  cargo build -q --release --target wasm32-unknown-unknown -p traversal-starter-bot -p traversal-minimal-bot && \
	  cd arena && cargo build -q --release --locked'
	@echo "✅ SDK $(SDK_VERSION) prêt dans $(SDK_REPO)"

sdk-push: sdk-check ## sdk-check, puis commit + tag v$(SDK_VERSION) + push du dépôt du SDK
	@git -C $(SDK_REPO) rev-parse -q --verify "refs/tags/v$(SDK_VERSION)" >/dev/null && \
	  { echo "le tag v$(SDK_VERSION) existe déjà : monte la version (engine-rs/Cargo.toml)"; exit 1; } || true
	git -C $(SDK_REPO) add -A
	git -C $(SDK_REPO) diff --cached --quiet || git -C $(SDK_REPO) commit -q -m "SDK $(SDK_VERSION)"
	git -C $(SDK_REPO) tag -a v$(SDK_VERSION) -m "SDK $(SDK_VERSION)"
	git -C $(SDK_REPO) push -u origin HEAD
	# Le tag explicitement : les auteurs de bots dépendent de lui (`tag = "vX.Y.Z"`).
	git -C $(SDK_REPO) push origin v$(SDK_VERSION)

sdk-publish: sdk-push ## (optionnel) publie aussi traversal-core et traversal-bot sur crates.io
	@[ -n "$(CARGO_REGISTRY_TOKEN)" ] || { echo "CARGO_REGISTRY_TOKEN manquant (.env.deploy)"; exit 1; }
	$(SDK_RUST) -e CARGO_REGISTRY_TOKEN rust:1.90-slim cargo publish -p traversal-core -p traversal-bot
