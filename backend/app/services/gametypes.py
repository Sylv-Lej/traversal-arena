"""Types de partie et classements.

- **Bullet** : 1 min + 1 s par coup. Classé.
- **Classique** : 5 min par joueur. Classé.
- **Tactique** : un MATCH en 2 manches de 2 min par joueur, avec bans et choix du type
  de carte avant chaque manche ; à égalité, manche décisive en bullet sur une carte
  tirée au sort (voir `matches.py`). Classé sur le résultat du match.

Un classement par type (`ratings.time_class`). Hors ligne (bot, local) : mêmes types,
plus « sans pendule », jamais classés pour le joueur.

Chaque **bot** a son propre classement (`BOT_CLASS`), qui bouge avec ses résultats contre
les joueurs (parties avec pendule) — voir `store._rate_bot`.
"""

GAME_TYPES: dict[str, tuple[int, int]] = {  # type -> (temps initial ms, incrément ms)
    "bullet": (60_000, 1_000),
    "classic": (300_000, 0),
    "tactic": (120_000, 0),
}
RATED_CLASSES = ("bullet", "classic", "tactic")
DEFAULT_CLASS = "classic"
CASUAL = "casual"  # sans pendule
BOT_CLASS = "bot"  # classement d'un bot contre les joueurs
BOT_START_RD = 150.0  # incertitude de départ : le classement d'un bot s'ajuste vite au début
BOT_MIN_PLY = 6  # partie trop courte (abandon immédiat…) : ne compte pas pour le bot
BOT_DAILY_CAP = 5  # parties comptées par joueur et par bot sur 24 h (perdre exprès en boucle)
DECIDER_TYPE = "bullet"  # cadence de la manche décisive d'un match tactique


def clock_of(game_type: str | None) -> tuple[int | None, int]:
    if game_type is None:
        return None, 0
    return GAME_TYPES[game_type]


def clock_label(initial_ms: int | None, increment_ms: int) -> str | None:
    """« 1+1 », « 5+0 », « 2+0 » (minutes + secondes d'incrément)."""
    if initial_ms is None:
        return None
    return f"{initial_ms // 60_000}+{increment_ms // 1000}"


def display_class(time_class: str) -> str:
    """Classement dont on montre le rang (une partie sans pendule montre le classique)."""
    return time_class if time_class in RATED_CLASSES else DEFAULT_CLASS
