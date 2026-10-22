"""Rangs « à la League of Legends » : une vitrine sur le classement Glicko-2.

Le Glicko-2 reste le moteur (appariements équitables, mise à jour après chaque partie
classée). Le rang n'en est qu'une lecture plus parlante :

- 8 paliers (Ardoise → Maître) + Légende (les 3 meilleurs Maîtres) ;
- 4 divisions par palier (IV → I), chacune large de 50 points de classement ;
- des points de ligue (PL) de 0 à 99 dans la division : 50 points de classement = 100 PL ;
- 5 parties de placement avant que le rang ne soit révélé.

Les seuils sont fixes (pas de PL « artificiels ») : ton rang suit exactement ton niveau.
"""

from dataclasses import dataclass

PLACEMENT_GAMES = 5
DIVISION_WIDTH = 50
ROMAN = {4: "IV", 3: "III", 2: "II", 1: "I"}
LEGEND_SLOTS = 3


@dataclass(frozen=True)
class Tier:
    key: str
    name: str
    floor: int  # classement minimum (division IV)


TIERS = (
    Tier("slate", "Ardoise", 800),
    Tier("bronze", "Bronze", 1000),
    Tier("silver", "Argent", 1200),
    Tier("gold", "Or", 1400),
    Tier("jade", "Jade", 1600),
    Tier("sapphire", "Saphir", 1800),
    Tier("diamond", "Diamant", 2000),
    Tier("master", "Maître", 2200),
)
MASTER = TIERS[-1]


def tier_of(rating: float) -> Tier:
    tier = TIERS[0]
    for t in TIERS:
        if rating >= t.floor:
            tier = t
    return tier


def rank_from(rating: float, games: int, legend: bool = False) -> dict:
    """Rang affiché pour un classement donné (et un nombre de parties classées)."""
    if games < PLACEMENT_GAMES:
        return {
            "tier": None,
            "name": "Placement",
            "division": None,
            "label": f"Placement {games}/{PLACEMENT_GAMES}",
            "lp": 0,
            "placement": {"played": games, "total": PLACEMENT_GAMES},
            "next": None,
        }
    tier = tier_of(rating)
    if tier is MASTER:
        lp = int(rating - MASTER.floor)
        key, name = ("legend", "Légende") if legend else (MASTER.key, MASTER.name)
        return {"tier": key, "name": name, "division": None, "label": name, "lp": lp,
                "placement": None, "next": None}
    idx = max(0, min(3, int((rating - tier.floor) // DIVISION_WIDTH)))
    division = 4 - idx
    div_floor = tier.floor + idx * DIVISION_WIDTH
    lp = 0 if rating < tier.floor else int((rating - div_floor) * 100 / DIVISION_WIDTH)
    if division > 1:
        nxt = {"label": f"{tier.name} {ROMAN[division - 1]}", "rating": div_floor + DIVISION_WIDTH,
               "tier": tier.key, "division": division - 1}
    else:
        up = TIERS[TIERS.index(tier) + 1]
        nxt = {"label": up.name if up is MASTER else f"{up.name} IV", "rating": up.floor,
               "tier": up.key, "division": None if up is MASTER else 4}
    return {
        "tier": tier.key,
        "name": tier.name,
        "division": division,
        "label": f"{tier.name} {ROMAN[division]}",
        "lp": max(0, min(99, lp)),
        "placement": None,
        "next": nxt,
    }


def ladder() -> list[dict]:
    """Tableau des paliers (page d'explication)."""
    out = []
    for i, t in enumerate(TIERS):
        ceiling = TIERS[i + 1].floor if i + 1 < len(TIERS) else None
        out.append({"tier": t.key, "name": t.name, "from": t.floor if i else None, "to": ceiling})
    out.append({"tier": "legend", "name": "Légende", "from": MASTER.floor, "to": None})
    return out
