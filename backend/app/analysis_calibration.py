"""Calibre l'analyse : à quelles chances de gagner correspond une évaluation ?

    python -m app.analysis_calibration [parties] [processus]   # module Rust requis

Fait jouer des parties entre les bots du site (Crête, Sommet, Mont Blanc, appariés au
hasard) sur des cartes tirées au sort, évalue chaque position AVEC L'ANALYSE ELLE-MÊME
(même moteur, même budget), puis ajuste `WIN_SCALE` (`app/analysis.py`) par maximum de
vraisemblance : P(le camp au trait gagne) = 1 / (1 + e^(-(v + WIN_OFFSET) / WIN_SCALE)),
nulle = ½. `WIN_OFFSET` corrige un biais de l'évaluation pour le camp au trait.
Affiche aussi le temps d'analyse par position.
"""

import math
import random
import sys
import time
from multiprocessing import Pool

from app import bot
from app.analysis import ANALYSIS_NODES, CAP, MATE, analyse_position
from app.bot import native
from app.engine import apply_move, generate_terrain, legal_moves, new_game

LEVELS = (3, 4, 5)
SKIP_PLIES = 2  # l'ouverture ne dit pas grand-chose


def play(seed: int) -> tuple[list[tuple[float, float]], float, int]:
    """Une partie ; renvoie (évaluation, résultat pour le camp au trait) par position."""
    rng = random.Random(seed)
    _, _, heights = generate_terrain("random", seed)
    s = new_game(heights)
    levels = {1: rng.choice(LEVELS), 2: rng.choice(LEVELS)}
    samples, spent, n = [], 0.0, 0
    while not s.over:
        if s.ply >= SKIP_PLIES:
            t = time.perf_counter()
            score = analyse_position(s, legal_moves(s)[0]).best_score
            spent += time.perf_counter() - t
            n += 1
            samples.append((s.to_move, float(score)))
        s = apply_move(s, bot.choose_move(s, levels[s.to_move], rng))
    out = []
    for side, v in samples:
        y = 0.5 if s.winner is None else 1.0 if s.winner == side else 0.0
        out.append((v, y))
    return out, spent, n


def model(v: float, scale: float, offset: float) -> float:
    return 1 / (1 + math.exp(-(max(-CAP, min(CAP, v)) + offset) / scale))


def log_loss(scale: float, data: list[tuple[float, float]], offset: float = 0.0) -> float:
    total = 0.0
    for v, y in data:
        p = model(v, scale, offset)
        p = min(max(p, 1e-6), 1 - 1e-6)
        total -= y * math.log(p) + (1 - y) * math.log(1 - p)
    return total / len(data)


def golden(f, lo: float, hi: float) -> float:
    """Minimum d'une fonction unimodale sur [lo, hi] (section dorée)."""
    g = (math.sqrt(5) - 1) / 2
    for _ in range(50):
        a, b = hi - g * (hi - lo), lo + g * (hi - lo)
        if f(a) < f(b):
            hi = b
        else:
            lo = a
    return (lo + hi) / 2


def fit(data: list[tuple[float, float]]) -> tuple[float, float]:
    """(échelle, décalage) par descente coordonnée ; l'échelle cherchée en log sur [20, 5000]."""
    scale, offset = 300.0, 0.0
    for _ in range(6):
        scale = math.exp(golden(lambda x: log_loss(math.exp(x), data, offset), math.log(20), math.log(5000)))
        offset = golden(lambda b: log_loss(scale, data, b), -300, 300)
    return scale, offset


def fit_scale_only(data: list[tuple[float, float]]) -> float:
    return math.exp(golden(lambda x: log_loss(math.exp(x), data), math.log(20), math.log(5000)))


def main() -> None:
    if not native.ENABLED:
        sys.exit("module Rust (traversal_rs) requis")
    games = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    procs = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    t0 = time.time()
    with Pool(procs) as pool:
        results = pool.map(play, range(10_000, 10_000 + games))
    data = [x for r in results for x in r[0] if abs(x[0]) < MATE]
    spent = sum(r[1] for r in results)
    n = sum(r[2] for r in results)
    scale, offset = fit(data)
    print(f"{games} parties, {len(data)} positions (hors gains forcés), {time.time() - t0:.0f} s")
    print(f"analyse : {ANALYSIS_NODES} nœuds, {1000 * spent / n:.0f} ms par position en moyenne")
    print(f"WIN_SCALE ≈ {scale:.0f}, WIN_OFFSET ≈ {offset:.0f}  (log-loss {log_loss(scale, data, offset):.4f} ;"
          f" sans décalage {log_loss(fit_scale_only(data), data):.4f} ; ancien barème 300 : {log_loss(300, data):.4f})")
    # Contrôle : taux de gain observé par tranche d'évaluation, contre le modèle.
    for lo, hi in ((-1500, -600), (-600, -250), (-250, -80), (-80, 80), (80, 250), (250, 600), (600, 1500)):
        part = [y for v, y in data if lo <= v < hi]
        if part:
            mid = (lo + hi) / 2
            print(f"  éval [{lo:>5}, {hi:>5}[ : {len(part):>5} positions, gain observé {100 * sum(part) / len(part):5.1f} %,"
                  f" modèle {100 * model(mid, scale, offset):5.1f} %")


if __name__ == "__main__":
    main()
