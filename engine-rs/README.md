# engine-rs — moteur et bot Traversal en Rust

Miroir rapide (~80 à 90× par coup) du moteur Python (`backend/app/engine`) et du bot
(`backend/app/bot`). Le Python reste la **référence** : API, notation, détail des combats.

| Crate | Rôle |
|---|---|
| `core/` | règles (coups légaux, application, fin de partie) + bot (évaluation, alpha-beta). Sans dépendance. |
| `py/` | module Python `traversal_rs`, appelé par le backend (`app/bot/native.py`). |
| `cli/` | simulations : tournois entre niveaux (Elo), mesure de vitesse. |
| `analysis/` | moteur de l'analyse de partie : le bot « orque » (bot personnel du dépôt du SDK, non publié), à budget de nœuds fixe. |
| `sdk/`, `bots/`, `arena/` | arène des bots WebAssembly des joueurs : SDK, bots d'exemple, runner en bac à sable. Voir [`ARENA.md`](ARENA.md). |

## Comment le backend l'utilise

`bot.choose_move` passe par `traversal_rs` dès qu'il est installé (image Docker de prod,
compilé par le `Dockerfile` du backend). Les niveaux (`bot.LEVELS`) restent définis en
Python et sont passés à Rust à chaque appel. Rust renvoie `(pièce, type, case)`, et le
coup complet est reconstruit par le moteur Python.

- `BOT_ENGINE=python` force le bot Python.
- Sans le module (dev local `make dev`, image Python standard), le bot Python prend le
  relais tout seul. Le log de démarrage indique `bot Rust` ou `bot Python`.

## Équivalence avec le Python

`backend/tests/test_engine_rs.py` compare les deux moteurs sur plus de 3000 positions :
coups légaux (coût, coup spécial, forces du combat), position après chaque coup, fins de
partie, évaluation du bot, constantes de `config.py`. **Toute règle modifiée en Python
doit l'être ici aussi**, sinon ce test échoue. Il est sauté si le module n'est pas
installé : il tourne dans l'image du backend.

```bash
# depuis la racine du repo
docker build -f backend/Dockerfile -t traversal-backend .
docker run --rm -v "$PWD/backend":/src/backend -w /src/backend traversal-backend \
  sh -c "pip install -q pytest pytest-asyncio && python -m pytest -q tests/test_engine_rs.py"
```

## Simulations

```bash
cd engine-rs
docker run --rm -v "$PWD":/w -v trav-cargo:/usr/local/cargo/registry -v trav-target:/w/target -w /w \
  rust:1.83-slim sh -c "cargo build --release && \
  ./target/release/traversal-cli tournament --a sommet --b montblanc --games 400 && \
  ./target/release/traversal-cli bench --level depth=6,beam=10,noise=0,ms=1800"
```

Un niveau est un nom (`galet` … `montblanc`, copies de `bot.LEVELS`) ou une spec
`depth=…,beam=…,noise=…,ms=…`. Chaque plateau est joué deux fois, couleurs inversées.
Les plateaux viennent de `boards.json` (générateur Python, régénérable avec
`scripts/export_boards.py`) ou de `--boards fichier.json`.

## Ce que chaque bot « comprend »

(Mont Blanc s'appelait Everest : le nom est gardé pour un futur bot plus fort.)

Galet et Sentier jouent le bot de référence (identique au Python). À partir de Crête,
chaque niveau ajoute une notion du jeu (`Level.insight`, cumulatif) — Rust seulement :

| Bot | Comprend en plus | Gain sur son ancienne version |
|---|---|---|
| **Crête** | **les échanges** : au bout de son horizon, il suit les captures et les sorties jusqu'au calme (plus de coup joué au milieu d'un échange, ni de sortie adverse ignorée parce qu'elle tombe juste après l'horizon) | +90 ± 36 |
| **Sommet** | **+ le terrain et les parades** : la distance à la sortie tient compte des pièces (une Sentinelle adverse est un mur, une autre pièce se franchit en l'abattant, une alliée doit s'écarter) ; les coups qui barrent le chemin du coureur adverse sont toujours examinés | +102 ± 37 |
| **Mont Blanc** | **+ la course des Sentinelles** (R8.2) : personne n'est sorti — qui sortira sa Sentinelle le premier, sachant qu'une sortie adverse quelconque, même d'un Explorateur, annule cette victoire | +46 ± 35 |

Les poids de ces notions (`Tuning` dans `core/src/bot.rs`) se règlent depuis la CLI, ex.
`montblanc,srace=300,blend=50`. Écartées après mesure (elles faisaient perdre) : bonus
statique pour les menaces de sortie, bonus de course générique (pièce la plus rapide,
quelle qu'elle soit), tri des parades en tête de liste (elles chassaient les bonnes
avancées des 7 coups qu'Mont Blanc examine).

Environ 75 % des parties entre bots finissent par une Sentinelle sortie la première : c'est
la notion qui compte le plus pour la suite.

## Mesures (400 parties par duel, 21/10/2026)

| Duel | Avant (bot de référence) | Après |
|---|---|---|
| Sentier → Crête | +326 ± 46 | +384 ± 51 |
| Crête → Sommet | +194 ± 38 | +138 ± 35 |
| Sommet → Mont Blanc | +97 ± 35 | +96 ± 35 |
| Galet → Sentier | +163 ± 36 | (inchangés) |
| Mont Blanc → profondeur 6 | +32 ± 34 | |

Chaque niveau a gagné un cran : le nouveau Crête vaut presque l'ancien Sommet (−27 ± 34),
le nouveau Sommet presque l'ancien Mont Blanc (−37 ± 34).

## Classement des bots

Chaque bot a un classement contre les joueurs (`ratings`, `time_class = "bot"`), créé au
démarrage avec une valeur de **départ** mesurée par un tournoi complet entre les 5 niveaux
(10 duels × 400 parties, ajustement d'Elo sur tous les résultats, ancré sur Galet = 920) :

| Bot | Départ | Rang |
|---|---|---|
| Galet | 920 | Ardoise II |
| Sentier | 1090 | Bronze III |
| Crête | 1520 | Or II |
| Sommet | 1645 | Jade IV |
| Mont Blanc | 1730 | Jade II |

Ensuite il **bouge** avec ses résultats (Glicko-2, `store._rate_bot`) : chaque partie avec
pendule contre un joueur le met à jour, face au classement du joueur dans cette cadence ;
le joueur, lui, reste non classé. Garde-fous : une partie de moins de 6 demi-coups ne
compte pas, et au plus 5 parties par joueur et par bot sur 24 h (`gametypes.py`). Les
valeurs de départ sont dans `bot.LEVELS` (`start_rating`) et, en repli d'affichage, dans
`frontend/lib/game.ts`. Si un bot change beaucoup, refaire le tournoi pour les recaler.
