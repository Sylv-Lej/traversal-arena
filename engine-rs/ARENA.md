# Arène des bots

Les joueurs écrivent un bot, l'envoient sur le site (`/arena`), et il est classé contre
les autres en continu. Un bot est un **module WebAssembly** exécuté en bac à sable : même
puissance de calcul pour tous, aucun accès au système, parties reproductibles.

```
navigateur ──► /arena/new ──► backend : arena_bots (pending) + tâche « check »
                                   │ arena_jobs (file)          ▲ coups joués
                                   ▼                            │ (rejoués et vérifiés
        Serverless Job (cron) : traversal-arena work ───────────┘  par le moteur Python)
           wasmtime, fuel, 64 Mo, ni fichiers ni réseau ni horloge
```

| Pièce | Où |
|---|---|
| Format d'un tour (binaire) | `core/src/wire.rs` |
| SDK Rust des bots (`traversal-bot`) | `sdk/` |
| Bot de départ = bot du site borné par le fuel (et les 5 bots maison) | `bots/starter/` |
| Le plus petit bot (exemple de la page « Créer un bot ») | `bots/minimal/` |
| Runner : bac à sable, parties, CLI | `arena/` (`traversal-arena`, son propre `Cargo.lock`) |
| File, vérification, placement, échelle, classement | `backend/app/services/arena.py` |
| API (joueurs / runner) | `backend/app/routes_arena.py` |
| Pages | `frontend/app/arena/` |
| Serverless Job, secret | `infra/main.tf` (`scaleway_job_definition.arena`) |

## SDK public

Les auteurs de bots utilisent le dépôt **<https://github.com/Sylv-Lej/traversal-rust-sdk>**,
un miroir généré depuis ici (`core`, `sdk`, `bots`, `arena`, `boards.json`, plus les
fichiers de `sdk-repo/`) : on n'y édite rien. Ils en dépendent par git, à un tag :

```toml
traversal-bot = { git = "https://github.com/Sylv-Lej/traversal-rust-sdk", tag = "v0.2.0" }
```

| Cible | Effet |
|---|---|
| `make sdk-sync` | régénère `../traversal-rust-sdk` (`SDK_REPO`), sans commit |
| `make sdk-check` | + tests, bots d'exemple en WASM, runner |
| `make sdk-push` | + commit, tag `v<version>`, push |
| `make sdk-publish` | + publication de `traversal-core` et `traversal-bot` sur crates.io (optionnel, `CARGO_REGISTRY_TOKEN`) |

**Nouvelle version** (une règle change, le SDK évolue) : monter `version` dans
`engine-rs/Cargo.toml` (et la dépendance de `sdk/Cargo.toml`), puis `make sdk-push`. Le
tag cité par la page « Créer un bot » est dans `frontend/app/arena/new/page.tsx`.

## Écrire un bot

### En Rust (conseillé)

```toml
# Cargo.toml
[lib]
crate-type = ["cdylib"]

[dependencies]
traversal-bot = { git = "https://github.com/Sylv-Lej/traversal-rust-sdk", tag = "v0.2.0" }
```

```rust
use traversal_bot::core::MoveKind;
use traversal_bot::{bot, Turn};

fn choose(turn: &Turn) -> usize {
    // turn.state : la position (traversal_core::State), turn.moves : les coups légaux,
    // turn.seed : la graine de ce coup, turn.fuel : le budget de ce coup.
    turn.moves.iter().position(|m| m.kind == MoveKind::Exit).unwrap_or(0)
}

bot!(choose);
```

```bash
cargo build --release --target wasm32-unknown-unknown   # -> …/release/mon_bot.wasm
```

Le moteur complet est dans `traversal_bot::core` (coups légaux, `apply_move`, le bot du
site `choose_move` avec son évaluation) : partir de `bots/starter`, c'est partir de Mont
Blanc. `traversal_bot::fuel_left()` dit le fuel restant (c'est l'horloge du bot),
`traversal_bot::log("…")` écrit un message visible avec `duel --verbose`.

### Dans un autre langage

Le module doit **exporter** :

- `memory` ;
- `traversal_buffer() -> i32` : adresse d'un tampon d'au moins 16 Ko, où l'arène écrit
  chaque tour ;
- `traversal_move(len: i32) -> i32` : lit le tour (`len` octets) et renvoie l'indice du
  coup choisi dans la liste.

Il ne peut **importer** que `traversal.fuel_left() -> i64` et
`traversal.log(ptr: i32, len: i32)`. Tout autre import (WASI compris) est refusé. Format
du tour (petit-boutiste, version 1) : voir l'en-tête de `core/src/wire.rs`.

## Règles du bac à sable

- **Fuel** : `FUEL_PER_MOVE` = 2 milliards par coup (≈ instructions WebAssembly, les
  `local.get`/`set` comptent aussi), remis à neuf à chaque coup. À zéro, la partie est
  perdue (« au temps »). Mont Blanc en utilise ~0,8 milliard ; ordre de grandeur : ~28
  milliards par seconde sur un Mac M, 3 à 4 fois moins sur un vCPU Scaleway.
- **Mémoire** : 64 Mo, une seule mémoire, pas de threads. **Module** : 1 Mo, compilé en
  120 s de CPU au plus.
- **Déterminisme** : pas d'horloge ni de hasard du système ; NaN canoniques, pas de SIMD
  « relâché ». Une graine est fournie à chaque coup : une partie se rejoue à l'identique.
- **Fautes** (partie perdue, raison « forfeit ») : plantage (trap, panique), indice de
  coup hors de la liste, module invalide.
- La mémoire du bot persiste d'un coup à l'autre pendant une partie (une instance neuve
  par partie).

## Tester en local

```bash
docker build -f engine-rs/arena/Dockerfile -t traversal-arena engine-rs
docker run --rm -v "$PWD":/w traversal-arena check /w/mon_bot.wasm            # valide ? (comme en production)
docker run --rm -v "$PWD":/w traversal-arena duel /w/mon_bot.wasm sommet --games 20 [--verbose]
```

Un adversaire est un `.wasm` ou un bot maison (`galet` … `montblanc`). Chaque carte est
jouée deux fois, couleurs inversées ; la sortie donne l'écart d'Elo et le fuel moyen.

Site complet en local : `make dev`, puis `make arena-dev`
(runner en boucle contre le backend local).

## Ce que fait le site

1. **Envoi** (compte requis, 5 envois par jour, 2 bots en lice) : version `pending`,
   tâche de validation. Le backend ne compile ni n'exécute jamais le module.
2. **Validation** par le runner : une partie de chaque couleur contre Galet, sans faute
   (perdre est permis). Sinon `rejected`, avec la raison.
3. **Placement** : une paire de parties contre chacun des 5 bots maison. Une nouvelle
   version (envoi en « mise à jour », `replaces`) remplace l'ancienne (`retired`,
   module effacé).
4. **Échelle** : quand la file est vide, `schedule()` tire des paires — les bots qui ont
   le moins joué sur 24 h d'abord, contre un des 3 participants de classement le plus
   proche — au plus 40 parties par bot et par 24 h (coût du runner borné). Deux bots du
   même joueur peuvent se rencontrer. Une fois pour toutes, 20 parties entre bots maison
   voisins calent l'échelle.
5. **Vérification** : le runner rend les coups, jamais le résultat. Le backend rejoue
   avec le moteur Python ; coup illégal ou partie inachevée = refusée. Une faute déclarée
   doit tomber sur le camp au trait.
6. **Classement** : Bradley-Terry (Elo) sur toutes les parties de l'arène, ancré sur
   Galet = 920 (comme `bot.LEVELS`), avec un adversaire fictif à 1500 (1 victoire,
   1 défaite) pour qu'un bot invaincu reste fini. Marge à 95 % affichée ; provisoire
   sous 10 parties. Recalculé au plus une fois par minute et à chaque fin de lot.

Les parties sont des parties ordinaires (`games`, mode `arena`). Leur **relecture est
fermée par défaut** : on voit les résultats (fiche d'un bot), pas les parties — l'API de
partie répond 404, l'accueil montre un plateau décoratif. `ARENA_REPLAYS=1` (variable
Terraform `arena_replays`) ouvre relecture, bilan et rejeu sur l'accueil.

## Sécurité

Deux barrières indépendantes entre un bot et le reste :

1. **Bac à sable WebAssembly** (`sandbox.rs`) : le bot ne voit que ce qu'on lui écrit en
   mémoire ; pas de WASI, deux fonctions de l'hôte. Ressources bornées (fuel, 64 Mo,
   1 Mo de module, pile 1 Mo). Une instance neuve par bot et par partie : les deux bots
   d'une partie ne partagent rien.
2. **Un processus enfant par tâche** (`isolate.rs`) : le runner ne compile ni n'exécute
   aucun bot lui-même. Chaque partie ou validation passe dans `traversal-arena play`,
   qui reçoit **seulement les deux modules de sa partie** (entrée standard), avec un
   **environnement vide** (pas d'`ARENA_TOKEN`), des limites `setrlimit` (CPU 300 s,
   ou 120 s pour une validation ; 400 Mo de données ; ni fichier core ni fichier écrit),
   puis un **filtre seccomp** : mémoire, lecture/écriture sur les descripteurs déjà
   ouverts, signaux, sortie, et rien d'autre (ni fichier, ni réseau, ni processus). Le
   parent le tue au-delà du délai. Une évasion de wasmtime ne donnerait donc accès ni au
   jeton, ni au code des autres bots.

La compilation se fait aussi dans l'enfant, sous ces limites : un module construit pour
épuiser le compilateur fait échouer sa propre validation (« limites dépassées »). Une
partie dont l'enfant ne rend rien n'est pas rapportée : le backend la reprend, puis
l'abandonne après 3 essais.

**Autotest** (`traversal-arena selftest`, et au début de chaque `work`) : l'enfant tente
d'ouvrir un fichier, une socket et un processus, et doit échouer partout ; puis une
partie Galet contre Galet doit aller au bout. Sinon le runner refuse de démarrer, au lieu
de faire perdre ou refuser des bots qui n'y sont pour rien. La liste d'appels système
autorisés est vérifiée en arm64 ; en amd64 (Scaleway), regarder les logs du premier
passage du Job — l'émulation amd64 sur Mac ne peut pas installer de filtre seccomp x86.

Autour :

- Le runner tourne **hors du backend** (Serverless Job), avec pour seuls accès l'URL du
  backend et `ARENA_TOKEN` (Secret Manager). Ce jeton n'ouvre que `/api/arena/runner/*`,
  pas le reste de l'API ; le relais du front n'expose pas ces routes.
- Le runner vérifie l'empreinte SHA-256 de chaque module téléchargé.
- **Fuite d'`ARENA_TOKEN`** (il permettrait de télécharger les bots en lice et de rendre
  des parties truquées faites de coups légaux) : `make arena-rotate-token`
  tire un nouveau jeton et le pose partout en un `apply` ; l'ancien ne vaut plus rien.
- Même un runner compromis ne peut pas écrire de résultat : seulement proposer des coups,
  que le backend rejoue.
- Requêtes HTTP plafonnées à 2 Mo avant lecture du corps, dans le relais du front et dans
  l'API (`backend/app/bodylimit.py`).

## Production

`make deploy` construit et pousse aussi l'image `traversal-arena`, et crée
le Job (`*/30 * * * *`, `arena_schedule`). Chaque passage joue jusqu'à vider la file
(25 min au plus) puis s'arrête : 0 € entre deux passages. Ordre de grandeur : une partie
≈ 5 s de vCPU, 40 parties par bot et par jour.

**Changer une règle** : le runner (Rust) et le backend (Python) doivent rester d'accord,
sinon les parties sont refusées (`partie d'arène … refusée` dans les logs du backend) —
même contrainte que le bot natif (`backend/tests/test_engine_rs.py`).
