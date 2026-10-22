# Traversal

Un « chess.com » pour [Traversal](https://www.traversalgame.com/rules) : jeu de stratégie à
2 joueurs sur un plateau 10×10 en relief, rendu en 3D (react-three-fiber).
Nom provisoire.

- Règles implémentées (et choix sur les ambiguïtés) : [`RULES.md`](./RULES.md)
- Plan d'implémentation complet : [`PLAN.md`](./PLAN.md)
- Capacité et montée en charge : [`SCALING.md`](./SCALING.md)
- Arène des bots (bots WebAssembly des joueurs) : [`engine-rs/ARENA.md`](./engine-rs/ARENA.md)

## Lancer en local

```bash
make dev   # base Lampion « traversal » (obligatoire : backend sans état)
```

Front http://localhost:3000 · API http://localhost:8000/docs.

- `make dev` : la base est le projet Lampion **`traversal`** (créé automatiquement depuis
  `LAMPION_API_KEY` de `./.env.deploy`). Les migrations Alembic s'appliquent au démarrage
  du backend, et les parties en cours reprennent après un redémarrage.
- Depuis le Mac, chaque requête SQL fait l'aller-retour jusqu'à Lampion (~35 ms depuis
  Docker) : un coup prend ~150 ms en local, quelques ms une fois déployé dans la même région.

Pour jouer en ligne contre soi-même : deux navigateurs (ou une fenêtre privée), « Jouer »
avec la même cadence dans les deux, ou « Défier un ami » et ouvrir le lien dans l'autre.

## Ce qui marche

| | |
|---|---|
| Modes | local (même écran), contre bot (5 niveaux), en ligne (invitation par lien + matchmaking par cadence) |
| Plateau | 3D : terrain en colonnes à strates, 5 styles de relief, pièces facettées (coins = Mouvement, pointes = Force), coups légaux, chemin, aperçu de combat, animations (marche, capture éjectée, sortie), vue de dessus, retourner, coordonnées, hauteurs (réglage) |
| Types de partie | **Bullet** (1 min + 1 s par coup), **Classique** (5 min par joueur), **Tactique** : match en 2 manches de 2 min ; avant chaque manche, chacun bannit un type de carte puis l'un choisit (il joue Rouge ; une carte jouée ne revient pas) ; à 1-1, manche décisive en bullet sur une carte tirée au sort ; 20 s par ban / choix (sinon tirage au sort). Un classement par type (le tactique au résultat du match). Contre un bot et en local : mêmes types + sans pendule (`backend/app/services/gametypes.py`, `matches.py`) |
| Partie | abandon, nulle, annulation, revanche (hors match), revue des coups (← →), sons |
| Spectateurs | page **Regarder** (`/watch`) : parties en ligne en cours, les plus relevées d'abord ; n'importe qui peut ouvrir une partie et la suivre en direct ; nombre de spectateurs affiché (compté en base, toutes instances) ; **anti-triche** : en partie en ligne, un spectateur voit la partie avec un tour de retard (2 demi-coups) — vue, flux temps réel, historique et liste ; tout est dévoilé à la fin (`SPECTATOR_DELAY_PLIES`, `backend/app/services/views.py`) |
| Classement | Glicko-2 par type de partie (bullet / classique / tactique), leaderboard, profils, courbe d'évolution |
| Rangs | vitrine « à la LoL » sur le Glicko-2 : Ardoise → Bronze → Argent → Or → Jade → Saphir → Diamant → Maître (+ Légende = top 3), divisions IV→I de 50 points, PL 0-100, 5 parties de placement, emblèmes SVG par palier, promotion/relégation en fin de partie, page `/ranks` qui explique tout |
| Puzzles | comme sur chess.com : **puzzles classés** (classement puzzles Glicko-2, chaque puzzle a sa propre note qui bouge), **puzzle du jour** (le même pour tous), **Puzzle Rush** (3 min, 5 min, Survie ; de plus en plus durs, 3 erreurs ; records et classement). Indice et solution pas à pas ; le serveur vérifie chaque coup. Générés à partir de parties bot contre bot : une position où UN coup gagne, sauve la partie ou prend un avantage décisif, vérifiée par le moteur (profondeur 4) ; thèmes (sortie, Sentinelle, combat, charge, parade, gain en N…). `python -m app.puzzles <parties> <nombre>` régénère `app/puzzles_data.json.gz`, chargé en base au démarrage |
| Arène des bots | page **Arène** (`/arena`) : un joueur inscrit envoie un bot WebAssembly (SDK Rust ou n'importe quel langage), il est validé puis classé en continu contre les autres et les 5 bots maison ; bac à sable wasmtime (fuel par coup, 64 Mo, aucun accès au système), runner à part (Serverless Job), chaque partie rejouée et vérifiée par le backend ; classement Bradley-Terry ancré sur Galet = 920. Voir [`engine-rs/ARENA.md`](./engine-rs/ARENA.md) |
| Bilan de partie | analyse de chaque coup d'une partie terminée par le bot « orque » (le plus fort de l'arène, `engine-rs/analysis`), budget de nœuds fixe (~profondeur 8, même bilan sur toute machine) : précision par joueur, appréciations (meilleur → gaffe) d'après les chances de gagner perdues — échelle mesurée sur des parties entre bots (`python -m app.analysis_calibration`) —, courbe d'avantage, meilleur coup tracé sur le plateau, barre d'évaluation ; calcul en arrière-plan (une analyse à la fois), gardé en base, recalculé si le moteur change (`analysis.VERSION`) |
| Comptes | invité automatique, puis compte email + mot de passe (argon2id) + **pays représenté** (obligatoire, pré-rempli d'après le navigateur, modifiable dans les réglages ; drapeau à côté du pseudo partout : partie, fin de partie, classement, profil, accueil — SVG `frontend/public/flags`, flag-icons MIT, noms de pays traduits par le navigateur) qui garde pseudo, parties et classement ; connexion multi-appareils ; mot de passe oublié (lien par email, 1 h, usage unique, déconnecte tous les appareils) ; changement de mot de passe |
| Sécurité | sessions expirées après 60 jours d'inactivité ; ménage toutes les 6 h (sessions expirées, invités inactifs 30 jours sans aucune partie) ; anti-CSRF dans le relais (`Sec-Fetch-Site` / `Origin` : seules nos pages peuvent modifier) ; en-têtes CSP stricte, anti-iframe, `nosniff`, HSTS (`next.config.js`) ; limites de débit par IP **partagées en base** pour connexion, inscription, invités, bilans et emails (en mémoire pour les coups) ; connexion bloquée 15 min après 5 échecs sur une même adresse (qu'elle ait un compte ou non) ; 12 flux temps réel max par IP ; email « mot de passe oublié » envoyé en arrière-plan (temps de réponse identique) |
| Persistance | Postgres Lampion, source de vérité : joueurs, sessions, classements, parties et coups, échéances des pendules, files bot/analyse, matchmaking |
| Montée en charge | backend **sans état** : N instances sur la même base, temps réel par Postgres `LISTEN/NOTIFY` (voir [`SCALING.md`](./SCALING.md)) |
| Mobile | utilisable à 320 px ; au doigt, une attaque se confirme d'un second tap |
| Langues | français + anglais : langue du navigateur à la première visite, puis choix FR/EN (cookie `tv_lang`, pas dans l'URL : un lien de partie s'ouvre dans la langue de chacun). Textes dans `frontend/lib/i18n/ns/*` (l'anglais a les mêmes clés que le français, vérifié par TypeScript) ; l'API traduit ses messages d'erreur, l'email de réinitialisation et les pseudos d'invités (`backend/app/i18n.py`, en-tête `x-lang` posé par le relais) |

## Architecture

```
navigateur ─► Next.js (app/api/[...path]/route.ts : relais, clé d'API, cookie de session)
                └─► FastAPI  backend/app/
                      engine/   règles pures, sans I/O (spec : RULES.md)
                      bot/      alpha-beta itératif borné en temps
                      services/ store.py (Postgres + LISTEN/NOTIFY, caches), games.py
                                (coups, pendules, fin, revanche), workers.py (échéances,
                                bots, analyses), lobby.py (matchmaking), accounts.py,
                                rating.py (Glicko-2), realtime.py (SSE)
                      db.py     schéma ; migrations/ = Alembic
```

Le moteur Python est la seule source de vérité : l'API renvoie l'état **et les coups
légaux** ; le front n'implémente aucune règle.

**Backend sans état.** Postgres est la source de vérité ; toutes les instances sont
équivalentes :

- **Modifier une partie** = une transaction qui verrouille sa ligne (`SELECT … FOR UPDATE`,
  `store.locked_game()`), écrit les nouveaux coups et la partie, et émet un `NOTIFY`.
  Deux coups simultanés, reçus par deux instances, sont sérialisés par Postgres.
- **Temps réel** : chaque instance écoute le canal `traversal` (`LISTEN`) sur une
  connexion dédiée ; une notification réveille ses flux SSE, quelle que soit l'instance
  qui a joué le coup.
- **Caches** (parties, joueurs, sessions) : de simples accélérateurs, validés par la
  version de la partie et invalidés par notification. Une partie absente est relue en
  base et reconstruite en **rejouant ses coups**.
- **Pendules et bots** : des échéances en base (`games.deadline_at`, table `bot_jobs`)
  traitées par les workers de n'importe quelle instance (`FOR UPDATE SKIP LOCKED`). Pas de
  sondage serré : chaque worker dort jusqu'à sa prochaine échéance connue et est réveillé
  par les notifications (réveil de secours toutes les 60 s) — la base peut se suspendre.
- **Analyses** (table `analysis_jobs`) et **matchmaking** (table `seeks`, appariement dans
  une transaction) : partagés de la même façon.

Nouvelle migration : modifier `app/db.py`, puis
`DATABASE_URL=… alembic revision --autogenerate -m "…"` depuis `backend/`.

## Déployer (Scaleway)

Tout est à Traversal (voir le `Makefile`) : registre d'images `traversal-<projet>`, namespace de
containers `traversal`, base Lampion **`traversal-prod`** (le dev garde `traversal`), état
Terraform sur Object Storage (`traversal-tfstate-<projet>`, privé, versionné).

```bash
make deploy TAG=$(git rev-parse --short HEAD)   # 1re fois et ensuite
make output                                     # URLs
make db-prod                                    # URL de la base de prod
```

Emails de réinitialisation : renseigner `PUBLIC_URL`, `MAIL_FROM`, `TEM_PROJECT_ID`,
`TEM_SECRET_KEY` dans `./.env.deploy` (domaine vérifié dans Scaleway TEM), puis `make apply`.
Coûts : voir [`SCALING.md`](./SCALING.md).

## Tests

```bash
cd backend && pip install -e ../packages/revkit -e ".[test]"
# Postgres local JETABLE (le schéma est effacé) — sans lui, seuls les tests purs tournent :
docker run -d --rm --name trav-pg -e POSTGRES_PASSWORD=pg -e POSTGRES_DB=trav -p 55432:5432 postgres:17
TEST_DATABASE_URL=postgresql://postgres:pg@localhost:55432/trav pytest
```

242 tests : règles, rangs, bilan de partie, terrain, parties aléatoires, API, comptes (mot
de passe oublié, expiration des sessions, ménage, blocage après échecs, limites partagées), persistance (reprise après redémarrage,
classements, historique) et **multi-instance** (`test_multi_instance.py` : pendules
balayées sans requête, coups concurrents sérialisés, et deux vrais serveurs uvicorn sur la
même base — flux SSE, bot et matchmaking d'une instance à l'autre).

## Emails (mot de passe oublié)

Envoyés via **Scaleway Transactional Email** si `MAIL_FROM`, `TEM_SECRET_KEY` et
`TEM_PROJECT_ID` sont définis (variables Terraform `mail_from`, `tem_secret_key`,
`tem_project_id`, plus `public_url` pour les liens). Il faut un domaine vérifié dans TEM
et une clé IAM **dédiée**, limitée à TEM. Sans cette configuration (dev local), rien
n'est envoyé : le lien de réinitialisation apparaît dans les logs du backend
(`docker compose logs backend | grep reset?token`).

## Passage au cloud (prochaine étape)

`infra/` est prêt (backend `max_scale = 1` obligatoire, `DATABASE_URL` Lampion injecté
en secret) : `make deploy`. À vérifier une fois en ligne : le passage des
flux SSE à travers Scaleway (durée max, buffering).
