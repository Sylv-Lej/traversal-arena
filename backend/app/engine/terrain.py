"""Génération de plateaux (R2).

Garanties, par construction :
- **équité** : le relief est symétrique par rotation de 180° (la case (x, y) a la même
  hauteur que (9-x, 9-y)) ; chaque camp voit donc exactement le même plateau ;
- **franchissable** : deux cases adjacentes diffèrent d'au plus `MAX_STEP` ;
- **reproductible** : même `(mode, seed)` → même plateau.

Variété : chaque biome (le `mode`, qui fixe l'ambiance visuelle) tire une **forme** parmi
plusieurs (massif, crête, canyon, mesas, rivière…), dont tous les paramètres (position,
orientation, hauteur, largeur, nombre de reliefs) sont aléatoires ; s'y ajoutent des
retouches globales (bruit, déformation du domaine, symétrie miroir, terrasses).
"""

import math
import random
from typing import Callable

from app.engine.config import MAX_HEIGHT, MAX_STEP, MIN_HEIGHT, SIZE, SQUARES

MODES = ("random", "mountains", "valleys", "highlands", "woodlands", "desert")

Fn = Callable[[float, float], float]
C = (SIZE - 1) / 2  # centre du plateau (4.5)


# --- Briques ------------------------------------------------------------------------------


def _noise(rng: random.Random, cells: int) -> Fn:
    """Bruit de valeur lissé, échantillonnable en coordonnées continues (0..9)."""
    grid = [[rng.random() for _ in range(cells + 2)] for _ in range(cells + 2)]

    def f(x: float, y: float) -> float:
        gx = min(max(x, 0.0), SIZE - 1) / (SIZE - 1) * cells
        gy = min(max(y, 0.0), SIZE - 1) / (SIZE - 1) * cells
        ix, iy = int(gx), int(gy)
        fx, fy = gx - ix, gy - iy
        sx, sy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
        top = grid[iy][ix] * (1 - sx) + grid[iy][ix + 1] * sx
        bot = grid[iy + 1][ix] * (1 - sx) + grid[iy + 1][ix + 1] * sx
        return top * (1 - sy) + bot * sy

    return f


def _fbm(rng: random.Random) -> Fn:
    """Bruit fractal (0..1) aux octaves tirées au sort : grain plus ou moins fin."""
    octaves = [(rng.choice((2, 3)), 0.6), (rng.choice((4, 5)), 0.3), (rng.choice((6, 7, 8)), rng.uniform(0.05, 0.2))]
    layers = [(_noise(rng, cells), w) for cells, w in octaves]
    total = sum(w for _, w in octaves)
    return lambda x, y: sum(n(x, y) * w for n, w in layers) / total


def _radius(x: float, y: float) -> float:
    """Distance au centre, normalisée (≈ 1 au milieu d'un bord)."""
    return math.hypot(x - C, y - C) / C


def _bump(px: float, py: float, h: float, w: float) -> Fn:
    return lambda x, y: h * math.exp(-((x - px) ** 2 + (y - py) ** 2) / w)


def _line_dist(angle: float, offset: float = 0.0) -> Fn:
    """Distance (en cases) à une droite d'orientation `angle` passant près du centre."""
    s, c = math.sin(angle), math.cos(angle)
    return lambda x, y: abs((x - C) * s - (y - C) * c - offset)


def _along(angle: float) -> Fn:
    """Abscisse le long de la droite d'orientation `angle` (pour les méandres)."""
    s, c = math.sin(angle), math.cos(angle)
    return lambda x, y: (x - C) * c + (y - C) * s


def _spot(rng: random.Random, margin: float = 1.0) -> tuple[float, float]:
    return rng.uniform(margin, SIZE - 1 - margin), rng.uniform(margin, SIZE - 1 - margin)


def _pits(rng: random.Random, n: int, depth: tuple[float, float], width: tuple[float, float]) -> Fn:
    """Creux posés par paires opposées : la symétrie (qui garde le plus haut des deux
    cases opposées) effacerait un creux isolé."""
    pits = []
    for _ in range(n):
        (px, py), d, w = _spot(rng), rng.uniform(*depth), rng.uniform(*width)
        pits += [_bump(px, py, d, w), _bump(SIZE - 1 - px, SIZE - 1 - py, d, w)]
    return lambda x, y: sum(p(x, y) for p in pits)


# --- Formes, par biome --------------------------------------------------------------------
# Chaque forme renvoie le champ de hauteur continu (avant symétrie et quantification).


def _massif(rng, n):
    h, w, a = rng.uniform(4, 5.4), rng.uniform(0.18, 0.45), rng.uniform(1.4, 2.8)
    return lambda x, y: h * math.exp(-(_radius(x, y) ** 2) / w) + a * n(x, y)


def _peaks(rng, n):
    bumps = [_bump(*_spot(rng), rng.uniform(4, 6), rng.uniform(1.2, 3.2)) for _ in range(rng.randint(1, 3))]
    a = rng.uniform(1, 2.2)
    return lambda x, y: sum(b(x, y) for b in bumps) + a * n(x, y)


def _ridge(rng, n):
    angle, off = rng.uniform(0, math.pi), rng.uniform(-1, 1)
    d, t = _line_dist(angle, off), _along(angle)
    h, w = rng.uniform(4, 5.5), rng.uniform(0.6, 2)
    passes = [rng.uniform(-4, 4) for _ in range(rng.randint(0, 2))]  # cols pour franchir la crête

    def f(x, y):
        v = h * math.exp(-d(x, y) ** 2 / w)
        for p in passes:
            v *= 1 - 0.65 * math.exp(-((t(x, y) - p) ** 2) / 0.8)
        return v + 1.6 * n(x, y)

    return f


def _crown(rng, n):
    k, r, phase = rng.randint(4, 8), rng.uniform(2.4, 3.6), rng.uniform(0, 2 * math.pi)
    h, w = rng.uniform(3.5, 5.5), rng.uniform(0.8, 1.8)
    bumps = [_bump(C + r * math.cos(phase + 2 * math.pi * i / k), C + r * math.sin(phase + 2 * math.pi * i / k), h, w)
             for i in range(k)]
    return lambda x, y: sum(b(x, y) for b in bumps) + 1.4 * n(x, y)


def _rim(rng, n):
    r, w, h = rng.uniform(0.65, 1.0), rng.uniform(0.05, 0.13), rng.uniform(3.8, 5)
    return lambda x, y: h * math.exp(-((_radius(x, y) - r) ** 2) / w) + 1.8 * n(x, y) - 0.8


def _canyon(rng, n):
    angle, base = rng.uniform(0, math.pi), rng.uniform(3, 4.5)
    amp, freq, w = rng.uniform(0, 1.6), rng.uniform(0.4, 1.1), rng.uniform(0.6, 2)
    t, s, c = _along(angle), math.sin(angle), math.cos(angle)

    def f(x, y):
        d = abs((x - C) * s - (y - C) * c - amp * math.sin(freq * t(x, y)))  # canyon sinueux
        return base * (1 - math.exp(-d * d / w)) + 1.4 * n(x, y)

    return f


def _furrows(rng, n):
    angle, k = rng.uniform(0, math.pi), rng.uniform(1.1, 2.2)
    t, h = _along(angle), rng.uniform(3, 5)
    # cos : sillons symétriques par rapport au centre (sinon la symétrie comblerait les creux).
    return lambda x, y: h * (0.5 + 0.5 * math.cos(k * t(x, y))) ** 1.5 + 1.4 * n(x, y) - 0.4


def _basin(rng, n):
    h, p = rng.uniform(4, 6), rng.uniform(1.2, 2.6)
    return lambda x, y: h * min(1.0, _radius(x, y)) ** p + 1.6 * n(x, y) - 0.5


def _crossroads(rng, n):
    a = rng.uniform(0, math.pi)
    d1, d2 = _line_dist(a), _line_dist(a + rng.uniform(math.pi / 3, 2 * math.pi / 3))
    base, w = rng.uniform(3.5, 5), rng.uniform(0.6, 1.4)
    return lambda x, y: base * (1 - math.exp(-d1(x, y) ** 2 / w)) * (1 - math.exp(-d2(x, y) ** 2 / w)) + 1.2 * n(x, y)


def _rugged(rng, n):
    a, b = rng.uniform(6, 8.5), rng.uniform(1, 2.2)
    return lambda x, y: a * n(x, y) - b


def _mesas(rng, n):
    tops = [(_bump(*_spot(rng), 9, rng.uniform(1.5, 4)), rng.uniform(3.5, 6)) for _ in range(rng.randint(2, 4))]
    a = rng.uniform(1.5, 3)
    return lambda x, y: max([a * n(x, y)] + [min(b(x, y), top) for b, top in tops])


def _terraces(rng, n):
    levels, ramp = rng.randint(3, 5), rng.uniform(0.15, 0.4)

    def f(x, y):
        u = n(x, y) * levels
        k, frac = math.floor(u), u - math.floor(u)
        t = min(1.0, max(0.0, (frac - (1 - ramp)) / ramp))  # palier, puis rampe courte
        return k + t * t * (3 - 2 * t)

    return f


def _plateau(rng, n):
    pits = _pits(rng, rng.randint(1, 3), (3, 5), (0.8, 2.2))
    return lambda x, y: 1.5 * n(x, y) - pits(x, y)


def _rolling(rng, n):
    a, b = rng.uniform(2.6, 4.2), rng.uniform(0, 0.8)
    return lambda x, y: a * n(x, y) - b


def _hillocks(rng, n):
    bumps = [_bump(*_spot(rng, 0.5), rng.uniform(1.8, 3.2), rng.uniform(0.5, 1.3)) for _ in range(rng.randint(5, 10))]
    return lambda x, y: sum(b(x, y) for b in bumps) + 1.2 * n(x, y)


def _river(rng, n):
    angle, base = rng.uniform(0, math.pi), rng.uniform(1.8, 3.2)
    amp, freq = rng.uniform(0.5, 2.2), rng.uniform(0.5, 1.2)
    t, s, c = _along(angle), math.sin(angle), math.cos(angle)

    def f(x, y):
        d = abs((x - C) * s - (y - C) * c - amp * math.sin(freq * t(x, y)))
        return base * min(1.0, d / 1.4) + 1.8 * n(x, y) - 0.3

    return f


def _glades(rng, n):
    holes = _pits(rng, rng.randint(1, 3), (1.5, 3), (1, 2.5))
    return lambda x, y: 1.6 * n(x, y) - holes(x, y)


def _dunes(rng, n):
    peaks = [_bump(rng.uniform(1, 8), rng.uniform(2, 7), rng.uniform(4.5, 6.5), rng.uniform(0.8, 1.6))
             for _ in range(rng.randint(1, 3))]
    return lambda x, y: 1.2 * n(x, y) + sum(p(x, y) for p in peaks)


def _waves(rng, n):
    angle, k, phase = rng.uniform(0, math.pi), rng.uniform(1.2, 2.4), rng.uniform(0, 2 * math.pi)
    t, h = _along(angle), rng.uniform(2.5, 4.5)

    def f(x, y):
        u = (k * t(x, y) + phase) / (2 * math.pi) % 1.0
        return h * (u / 0.7 if u < 0.7 else (1 - u) / 0.3) + 1.2 * n(x, y)  # pente douce, face raide

    return f


def _buttes(rng, n):
    tops = [(_bump(*_spot(rng), 9, rng.uniform(0.6, 1.4)), rng.uniform(4.5, 6)) for _ in range(rng.randint(2, 4))]
    return lambda x, y: max([0.9 * n(x, y)] + [min(b(x, y), top) for b, top in tops])


def _erg(rng, n):
    angle, k = rng.uniform(0, math.pi), rng.uniform(0.8, 1.6)
    t, a = _along(angle), rng.uniform(3, 5)
    return lambda x, y: a * n(x, y) * (0.6 + 0.4 * math.sin(k * t(x, y))) + 0.3


SHAPES: dict[str, tuple[Callable[[random.Random, Fn], Fn], ...]] = {
    "mountains": (_massif, _peaks, _ridge, _crown),
    "valleys": (_rim, _canyon, _furrows, _basin, _crossroads),
    "highlands": (_rugged, _mesas, _terraces, _plateau),
    "woodlands": (_rolling, _hillocks, _river, _glades),
    "desert": (_dunes, _waves, _buttes, _erg),
}

# Plage de hauteurs visée par biome : (plancher, amplitude), chacun tiré dans un intervalle.
# Le champ est recalé dessus : jamais de carte plate, jamais de mur uniforme à 6.
RELIEF = {
    "mountains": ((0.0, 1.0), (4.5, 6.0)),
    "valleys": ((0.0, 1.0), (3.5, 5.5)),
    "highlands": ((1.0, 2.2), (3.2, 4.4)),
    "woodlands": ((0.0, 1.2), (2.6, 4.0)),
    "desert": ((0.0, 0.8), (2.6, 5.0)),
}

# Formes faites uniquement de reliefs : une symétrie miroir (par le max) ne peut rien y
# effacer. Les autres ont des creux, qu'elle comblerait.
MIRRORABLE = {_massif, _peaks, _crown, _hillocks, _buttes, _mesas, _dunes}


def _field(mode: str, rng: random.Random) -> list[list[float]]:
    """Champ de hauteur continu (avant quantification) : forme du biome + retouches."""
    if mode not in SHAPES:
        raise ValueError(mode)
    make = rng.choice(SHAPES[mode])
    shape = make(rng, _fbm(rng))
    # Déformation du domaine : courbe les lignes droites (crêtes, canyons, vagues). Elle est
    # antisymétrique (D(opposé) = -D) : une forme symétrique le reste, ses creux aussi.
    warp = rng.uniform(0, 1.6)
    nx, ny = _noise(rng, 3), _noise(rng, 3)
    def wx(x, y): return nx(x, y) - nx(SIZE - 1 - x, SIZE - 1 - y)
    def wy(x, y): return ny(x, y) - ny(SIZE - 1 - x, SIZE - 1 - y)
    (b0, b1), (a0, a1) = RELIEF[mode]
    base, span = rng.uniform(b0, b1), rng.uniform(a0, a1)
    mirror = make in MIRRORABLE and rng.random() < 0.35  # symétrie miroir en plus : cartes plus « architecturées »
    f = [[0.0] * SIZE for _ in range(SIZE)]
    for y in range(SIZE):
        for x in range(SIZE):
            f[y][x] = shape(x + warp * wx(x, y), y + warp * wy(x, y))
    if mirror:
        f = [[max(row[x], row[SIZE - 1 - x]) for x in range(SIZE)] for row in f]
    # Recalage : minimum → plancher, maximum → plancher + amplitude (la forme est gardée).
    lo, hi = min(min(row) for row in f), max(max(row) for row in f)
    k = span / max(hi - lo, 0.3)
    return [[base + (v - lo) * k for v in row] for row in f]


def _lipschitz(h: list[int]) -> list[int]:
    """Relève les cases jusqu'à ce que deux voisines diffèrent d'au plus MAX_STEP.

    On relève (plutôt qu'abaisser) pour garder les pics : un sommet isolé devient un cône
    franchissable au lieu d'être rasé. Résultat = la plus petite fonction ≥ h qui respecte
    la contrainte : elle est unique, donc une entrée symétrique donne une sortie symétrique.
    """
    h = h[:]
    changed = True
    while changed:
        changed = False
        for i in range(SQUARES):
            x, y = i % SIZE, i // SIZE
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if 0 <= nx < SIZE and 0 <= ny < SIZE:
                    floor = h[ny * SIZE + nx] - MAX_STEP
                    if h[i] < floor:
                        h[i] = floor
                        changed = True
    return h


def generate(mode: str = "random", seed: int | None = None) -> tuple[str, int, tuple[int, ...]]:
    """Renvoie (mode effectif, seed, hauteurs[100])."""
    if mode not in MODES:
        raise ValueError(f"mode de terrain inconnu : {mode}")
    if seed is None:
        seed = random.SystemRandom().randrange(2**31)
    rng = random.Random(seed)
    effective = rng.choice(MODES[1:]) if mode == "random" else mode
    f = _field(effective, rng)
    flat: list[int] = []
    for y in range(SIZE):
        for x in range(SIZE):
            # Symétrie centrale : on garde le plus haut des deux reliefs opposés (une
            # moyenne écraserait de moitié chaque pic isolé).
            v = max(f[y][x], f[SIZE - 1 - y][SIZE - 1 - x])
            flat.append(max(MIN_HEIGHT, min(MAX_HEIGHT, round(v))))
    return effective, seed, tuple(_lipschitz(flat))
