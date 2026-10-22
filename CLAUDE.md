# CLAUDE.md — Traversal (arène de bots)

Jeu de stratégie 3D façon chess.com (local, bot, en ligne, classement, comptes) et arène de
bots WebAssembly des joueurs. Extrait du monorepo RevKit (`sylv_monolith`) : ce dépôt est
autonome. Voir `README.md`, `PLAN.md`, `SCALING.md`, `RULES.md`, `engine-rs/ARENA.md`.

## Stack

| Couche   | Techno                                   | Hébergement                          |
|----------|------------------------------------------|--------------------------------------|
| Frontend | Next.js 15 (App Router, TypeScript)      | Scaleway Serverless Container        |
| Backend  | FastAPI (Python 3.12, async)             | Scaleway Serverless Container        |
| Moteur   | Rust (`engine-rs`) : module Python + runner de l'arène | Serverless Job (cron)  |
| DB       | PostgreSQL 17                            | **Lampion** (`traversal` dev, `traversal-prod` prod) |
| Infra    | Terraform                                | provider `scaleway/scaleway`         |

## Structure

```
backend/          # App FastAPI (routes, modèles, migrations Alembic, tests)
frontend/         # App Next.js
engine-rs/        # Moteur Rust : core, SDK des bots, bots maison, runner de l'arène, module py
infra/            # Terraform (main.tf…), modules/ (registry, serverless-container), scripts/
packages/revkit/  # Lib backend (create_app, settings, db, auth, ratelimit) — copie vendorée
```

## Commandes (tout en Docker, rien à installer sur l'hôte)

Secrets dans `./.env.deploy` (gitignoré, modèle `.env.deploy.example`) : `SCW_*`,
`LAMPION_API_KEY`. `DATABASE_URL` est résolu tout seul via Lampion.

```bash
make dev                                   # backend :8000 + frontend :3000 (DB Lampion « traversal »)
make arena-dev                             # runner de l'arène contre le backend local
make deploy TAG=$(git rev-parse --short HEAD)
make help                                  # toutes les cibles
```

`SITE := traversal` dans le Makefile nomme les images, le projet Lampion du dev et la clé de
l'état Terraform (`traversal/terraform.tfstate`) : ne pas le changer sans migrer l'infra.

## Conventions

- **📱 Mobile obligatoire**, cible **320 px** : `clamp()` pour les tailles, `100dvh`,
  `env(safe-area-inset-*)`, cibles tactiles ≥ 44 px + `touch-action: manipulation`, zéro
  scroll horizontal, `-webkit-text-size-adjust: 100%`.
- **Backend** : routes async, Pydantic, SQLAlchemy async, `/healthz`. Sans état (N instances,
  Postgres `LISTEN/NOTIFY`). CORS fermé (`FRONTEND_ORIGIN` vide).
- **Frontend** : composants serveur par défaut, `"use client"` seulement si interaction. Le
  navigateur ne parle jamais à l'API : tout passe par le relais `app/api/[...path]/route.ts`,
  qui détient la clé d'API.
- **Secrets** : via Terraform (`secret_environment_variables`), jamais dans le code ni le repo.
- **Coût** : scale-to-zero (`min_scale = 0`), région `fr-par`.
