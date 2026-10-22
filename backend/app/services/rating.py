"""Glicko-2 (Glickman, 2012), une partie = une période de notation (comme lichess)."""

import math
from dataclasses import dataclass

SCALE = 173.7178
TAU = 0.5


@dataclass
class Rating:
    rating: float = 1500.0
    rd: float = 350.0
    vol: float = 0.06
    games: int = 0
    wins: int = 0
    losses: int = 0
    draws: int = 0


def _g(phi: float) -> float:
    return 1 / math.sqrt(1 + 3 * phi * phi / math.pi**2)


def update(player: Rating, opponent: Rating, score: float) -> Rating:
    """Nouvelle note de `player` après une partie (score : 1 victoire, 0.5 nulle, 0 défaite)."""
    mu, phi = (player.rating - 1500) / SCALE, player.rd / SCALE
    mu_j, phi_j = (opponent.rating - 1500) / SCALE, opponent.rd / SCALE
    g = _g(phi_j)
    e = 1 / (1 + math.exp(-g * (mu - mu_j)))
    v = 1 / (g * g * e * (1 - e))
    delta = v * g * (score - e)

    a = math.log(player.vol**2)

    def f(x: float) -> float:
        ex = math.exp(x)
        return ex * (delta**2 - phi**2 - v - ex) / (2 * (phi**2 + v + ex) ** 2) - (x - a) / TAU**2

    if delta**2 > phi**2 + v:
        hi = math.log(delta**2 - phi**2 - v)
    else:
        k = 1
        while f(a - k * TAU) < 0:
            k += 1
        hi = a - k * TAU
    lo, hi = a, hi
    f_lo, f_hi = f(lo), f(hi)
    while abs(hi - lo) > 1e-6:
        c = lo + (lo - hi) * f_lo / (f_hi - f_lo)
        f_c = f(c)
        if f_c * f_hi <= 0:
            lo, f_lo = hi, f_hi
        else:
            f_lo /= 2
        hi, f_hi = c, f_c
    vol = math.exp(lo / 2)

    phi_star = math.sqrt(phi**2 + vol**2)
    new_phi = 1 / math.sqrt(1 / phi_star**2 + 1 / v)
    new_mu = mu + new_phi**2 * g * (score - e)
    return Rating(
        rating=new_mu * SCALE + 1500,
        rd=max(45.0, min(350.0, new_phi * SCALE)),
        vol=vol,
        games=player.games + 1,
        wins=player.wins + (score == 1),
        losses=player.losses + (score == 0),
        draws=player.draws + (score == 0.5),
    )


def time_class(initial_s: int | None, increment_s: int) -> str:
    """Cadence estimée sur 40 coups, comme chess.com."""
    if initial_s is None:
        return "casual"
    total = initial_s + 40 * increment_s
    if total < 180:
        return "bullet"
    if total < 600:
        return "blitz"
    return "rapid"
