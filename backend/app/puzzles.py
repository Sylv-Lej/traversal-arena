"""Génération de puzzles (comme sur chess.com), à partir de parties bot contre bot.

Un puzzle naît d'une erreur : l'adversaire vient de jouer un coup, et il existe alors pour
le joueur au trait UN coup nettement meilleur que tous les autres :

- **gain** : le coup gagne la partie (sortie de la Sentinelle en premier, sortie décisive
  au score…) alors qu'aucun autre ne gagne ;
- **sauvetage** : tous les coups perdent, sauf un (bloquer ou abattre la pièce qui allait
  sortir…) ;
- **avantage** : le coup prend un avantage décisif (combat gagné, sortie qui scelle le
  score…) avec un écart net sur le 2ᵉ meilleur coup.

Pour un « gain », la solution est le chemin le PLUS RAPIDE vers la victoire ; au dernier
coup, toute sortie qui gagne immédiatement est acceptée (comme les mats sur chess.com).

La solution enchaîne jusqu'à 5 coups du joueur, avec la meilleure réponse adverse entre
eux ; chaque coup du joueur doit être le seul bon (sinon le puzzle s'arrête avant). Plus
la solution est longue, plus le puzzle est classé haut : il faut voir loin. Comme
sur chess.com, le puzzle commence par le coup de l'adversaire (l'erreur), joué
automatiquement. Pur et déterministe (graine) : `python -m app.puzzles` régénère le jeu de
puzzles livré avec le site.
"""

import gzip
import json
import math
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

from app import bot
from app.bot import WIN, Level, _negamax, _ordered, _Timeout, evaluate
from app.engine import GameState, Move, Piece, apply_move, generate_terrain, legal_moves, new_game
from app.engine import config as C

DATA_FILE = Path(__file__).resolve().parent / "puzzles_data.json.gz"

MATE = WIN // 2
SEARCH = Level("Puzzle", depth=4, beam=12, noise=0.0, budget_s=20.0)
DEPTH = 4  # vérification (plis)
QUICK_DEPTH = 2  # premier tri, peu coûteux
ADV_GAP = 160  # écart minimal (centièmes de point) entre le meilleur et le 2ᵉ coup
ADV_MIN = 120  # avantage minimal après le coup (point de vue du joueur)
CONT_GAP = 90  # écart suffisant pour PROLONGER une ligne déjà lancée (le 1er coup reste à ADV_GAP)
MAX_PLAYER_MOVES = 5
MIN_CHOICES = 4  # pas de puzzle quand il n'y a presque rien à choisir


@dataclass
class Puzzle:
    id: str
    terrain: str
    start: dict  # position AVANT le coup de l'adversaire
    solution: list[dict]  # coup adverse, puis coups du joueur et réponses, en alternance
    themes: list[str]
    rating: float
    side: int  # camp du joueur
    meta: dict = field(default_factory=dict)
    tree: list[dict] | None = None  # variantes acceptées (voir `_grow`)


# --- Positions <-> JSON -------------------------------------------------------------------


def _pieces(ps) -> list[dict]:
    return [{"id": p.id, "owner": p.owner, "kind": p.kind, "sq": p.sq} for p in ps]


def state_to_json(s: GameState) -> dict:
    return {"heights": list(s.heights), "pieces": _pieces(s.pieces), "toMove": s.to_move, "ply": s.ply,
            "scores": list(s.scores), "finished": _pieces(s.finished), "captured": _pieces(s.captured),
            "moveLimit": s.move_limit}


def state_from_json(d: dict) -> GameState:
    def ps(items):
        return tuple(Piece(p["id"], p["owner"], p["kind"], p["sq"]) for p in items)

    return GameState(heights=tuple(d["heights"]), pieces=ps(d["pieces"]), to_move=d["toMove"], ply=d["ply"],
                     scores=tuple(d["scores"]), finished=ps(d["finished"]), captured=ps(d["captured"]),
                     move_limit=d["moveLimit"])


def move_key(m: Move) -> dict:
    return {"pieceId": m.piece_id, "kind": m.kind, "to": m.to}


def same(m: Move, d: dict) -> bool:
    return m.piece_id == d["pieceId"] and m.kind == d["kind"] and m.to == d["to"]


# --- Recherche ----------------------------------------------------------------------------


def rank_moves(state: GameState, depth: int, deadline: float) -> list[tuple[float, Move]]:
    """Score EXACT (fenêtre complète) de chaque coup, du point de vue du joueur au trait."""
    out = []
    for m in _ordered(state):
        child = apply_move(state, m)
        s = evaluate(child, state.to_move) if depth <= 1 else -_negamax(
            child, depth - 1, -math.inf, math.inf, SEARCH, deadline)
        out.append((s, m))
    out.sort(key=lambda t: t[0], reverse=True)
    return out


def _choices(state: GameState) -> int:
    return len([m for m in legal_moves(state) if m.kind != "pass"])


def kind_of(ranked: list[tuple[float, Move]]) -> str | None:
    """Type de puzzle de la position (None : pas de coup qui se détache)."""
    if len(ranked) < 2:
        return None
    best, second = ranked[0][0], ranked[1][0]
    if best >= MATE:
        return "win" if best > second else None  # plus rapide que tout autre coup
    if second <= -MATE < best:
        return "save"  # tous les autres coups perdent
    if best >= ADV_MIN and best - second >= ADV_GAP:
        return "advantage"
    return None


def _unique(ranked: list[tuple[float, Move]], state: GameState) -> bool:
    """Le meilleur coup se détache-t-il (seul bon coup) ? Une sortie qui gagne tout de
    suite est toujours acceptée (au jeu, toute victoire immédiate est un bon coup)."""
    if apply_move(state, ranked[0][1]).over:
        return True
    best, second = ranked[0][0], ranked[1][0]
    if best >= MATE:
        return best > second
    return best >= ADV_MIN and best - second >= CONT_GAP


def _threat(state: GameState, deadline: float) -> bool:
    """L'adversaire gagnerait-il si on « passait » ? (thème parade)"""
    other = 2 if state.to_move == 1 else 1
    flipped = GameState(heights=state.heights, pieces=state.pieces, to_move=other, ply=state.ply,
                        scores=state.scores, finished=state.finished, captured=state.captured,
                        move_limit=state.move_limit)
    ranked = rank_moves(flipped, 2, deadline)
    return bool(ranked) and ranked[0][0] >= MATE


MAX_ALTS = 3  # coups équivalents acceptés à une même étape (au-delà : étape sans intérêt)


def _good_moves(ranked: list[tuple[float, Move]], state: GameState, first: bool) -> list[Move]:
    """Coups acceptés à cette étape : le seul bon coup, ou (gain en cours, après le 1er coup)
    les quelques coups qui gagnent exactement aussi vite — deux chemins vers la même sortie
    se valent, refuser l'un des deux serait injuste."""
    if len(ranked) < 2:
        return []
    best = ranked[0][0]
    if first or best < MATE or apply_move(state, ranked[0][1]).over:
        # Dernier coup gagnant : toute victoire immédiate est acceptée au jeu (pas d'arbre).
        return [ranked[0][1]] if _unique(ranked, state) else []
    tied = [m for sc, m in ranked if sc == best]
    return tied if len(tied) <= MAX_ALTS else []


def _grow(s: GameState, side: int, k: int, deadline: float) -> tuple[list[dict], int, bool, list[Move], GameState] | None:
    """Arbre des coups acceptés depuis `s` (joueur au trait, k-ième coup du joueur).

    Renvoie (nœud, longueur, victoire, ligne principale, position finale) ; toutes les
    branches d'un nœud ont la même longueur et la même issue (sinon None : la ligne
    s'arrête au coup précédent). Nœud = [{"m": coup, "r": réponse, "next": nœud}, …],
    le premier élément étant la ligne principale.
    """
    goods = _good_moves(rank_moves(s, DEPTH, deadline), s, first=k == 0)
    if not goods:
        return None
    node, shape, main = [], None, None
    for m in goods:
        a = apply_move(s, m)
        opt: dict = {"m": move_key(m)}
        if a.over:
            if a.winner != side:
                return None
            res = (1, True, [m], a)
        else:
            res = (1, False, [m], a)
            if k + 1 < MAX_PLAYER_MOVES:
                reply = rank_moves(a, DEPTH - 1, deadline)[0][1]
                b = apply_move(a, reply)
                sub = None if b.over else _grow(b, side, k + 1, deadline)
                if sub:
                    opt.update(r=move_key(reply), next=sub[0])
                    res = (1 + sub[1], sub[2], [m, reply] + sub[3], sub[4])
        if shape is None:
            shape, main = res[:2], res
        elif res[:2] != shape:
            return None  # variantes de longueur ou d'issue différentes : étape ambiguë
        node.append(opt)
    return node, shape[0], shape[1], main[2], main[3]


def build_line(state: GameState, deadline: float) -> tuple[str, list[Move], GameState, list[dict]] | None:
    """Solution à partir de `state` (joueur au trait) ; None si pas de puzzle.

    La ligne se prolonge tant que le coup du joueur reste le seul bon (ou l'un des rares
    coups équivalents d'un gain), jusqu'à la victoire ou `MAX_PLAYER_MOVES` coups ; elle
    finit toujours sur un coup du joueur. Type : « win » si elle mène à la victoire, sinon
    celui du premier coup (sauvetage / avantage). Renvoie aussi l'arbre des variantes.
    """
    side = state.to_move
    ranked = rank_moves(state, DEPTH, deadline)
    if len(ranked) < 2:
        return None
    # Premier coup : écart net (sauvetage, avantage, gain)… ou, à défaut, un écart plus
    # modeste mais seulement si la ligne finit par la victoire : elle se prouve alors
    # d'elle-même, c'est ainsi qu'on trouve les gains en 3, 4, 5 coups.
    kind = kind_of(ranked)
    if kind is None and not _unique(ranked, state):
        return None
    if sum(1 for sc, m in ranked if sc >= MATE and apply_move(state, m).over) > 1:
        return None  # plusieurs sorties gagnent tout de suite : trop facile
    grown = _grow(state, side, 0, deadline)
    if grown is None:
        return None
    tree, _, won, line, end = grown
    if won:
        return "win", line, end, tree
    if kind in (None, "win"):
        return None  # un « gain » doit aller jusqu'à la victoire
    return kind, line, end, tree


def themes_of(state: GameState, kind: str, line: list[Move], end: GameState, threat: bool) -> list[str]:
    side = state.to_move
    mine = line[0::2]
    tags = set()
    s = state
    for i, m in enumerate(line):
        if i % 2 == 0:
            p = s.piece(m.piece_id)
            if m.kind == "exit":
                tags.add("exit")
                if p.kind == C.SENTINEL and not s.finished:
                    tags.add("sentinel")
            if m.kind == "attack":
                tags.add("combat")
                if m.combat and any(t.label == "charge" for t in m.combat.attack_terms):
                    tags.add("charge")
            if m.special in ("diag", "leap"):
                tags.add("explorer")
        s = apply_move(s, m)
    if threat or kind == "save":
        tags.add("defense")
    if end.over and end.winner == side:
        tags.add(f"winIn{len(mine)}")
    elif kind == "save":
        tags.add("save")
    else:
        tags.add("advantage")
    tags.add({1: "oneMove", 2: "short"}.get(len(mine), "long"))
    return sorted(tags)


# Classement de base selon le nombre de coups du joueur : c'est la longueur de la ligne à
# calculer qui fait la difficulté (les retouches ci-dessous ne changent pas de palier).
BASE_RATING = {1: 750, 2: 1150, 3: 1500, 4: 1800, 5: 2050}


def estimate_rating(state: GameState, kind: str, line: list[Move], tags: list[str]) -> float:
    n = len(line[0::2])
    r = BASE_RATING[min(n, MAX_PLAYER_MOVES)]
    r += {"win": 0, "save": 60, "advantage": 90}[kind]  # sans victoire au bout : plus dur à voir
    r += max(-60, min(90, (_choices(state) - 20) * 4))
    r += 50 * ("defense" in tags) + 40 * ("explorer" in tags) + 40 * ("charge" in tags)
    return float(r)


# --- Explications (le « pourquoi » de chaque coup de la solution) ------------------------


def _flip(state: GameState) -> GameState:
    """Même position, l'autre camp au trait (pour lire ses menaces)."""
    return GameState(heights=state.heights, pieces=state.pieces, to_move=2 if state.to_move == 1 else 1,
                     ply=state.ply, scores=state.scores, finished=state.finished, captured=state.captured,
                     move_limit=state.move_limit)


def _winning_exits(state: GameState) -> list[Move]:
    """Sorties qui donneraient la victoire tout de suite au camp au trait."""
    out = []
    for m in legal_moves(state):
        if m.kind == "exit":
            after = apply_move(state, m)
            if after.over and after.winner == state.to_move:
                out.append(m)
    return out


def explain(state: GameState, move: Move) -> list[dict]:
    """Ce qu'enseigne un coup : codes (traduits par le front) avec leurs paramètres.

    sentinelFirst / scoreWin / exit, capture (+ highGround, lowGround, support, charge,
    reinforced), leap / diag, parry (menace adverse neutralisée), doubleThreat /
    sentinelThreat / threatExit (sortie possible au prochain tour), advance.
    """
    side = state.to_move
    piece = state.piece(move.piece_id)
    after = apply_move(state, move)
    notes: list[dict] = []
    if move.kind == "exit":
        if after.over and after.reason == "sentinel":
            notes.append({"code": "sentinelFirst"})
        elif after.over:
            notes.append({"code": "scoreWin", "score": list(after.scores), "side": side})
        else:
            notes.append({"code": "exit", "kind": piece.kind, "points": C.STRENGTH[piece.kind]})
        return notes
    if move.kind == "attack" and move.combat:
        target = state.occupancy()[move.to]
        notes.append({"code": "capture", "kind": piece.kind, "target": target.kind,
                      "attack": move.combat.attack, "defense": move.combat.defense})
        for t in move.combat.attack_terms:
            if t.label == "height":
                notes.append({"code": "highGround" if t.value > 0 else "lowGround"})
            elif t.label == "charge":
                notes.append({"code": "charge"})
            elif t.label.startswith("ally:"):
                notes.append({"code": "support", "kind": t.label[5:], "value": t.value})
        reinforced = sum(1 for t in move.combat.defense_terms if t.label.startswith("reinforcement"))
        if reinforced:
            notes.append({"code": "reinforced", "count": reinforced})
    if move.special in ("diag", "leap"):
        notes.append({"code": move.special})
    if after.over:
        return notes
    # Menace adverse : l'adversaire gagnait au prochain tour si l'on n'avait rien fait.
    if _winning_exits(_flip(state)) and not _winning_exits(after):
        notes.append({"code": "parry"})
    # Nos menaces de sortie au prochain tour (si l'adversaire ne fait rien).
    threats = {m.piece_id for m in legal_moves(_flip(after)) if m.kind == "exit"}
    if len(threats) >= 2:
        notes.append({"code": "doubleThreat"})
    elif move.piece_id in threats:
        sentinel_wins = piece.kind == C.SENTINEL and not after.finished
        notes.append({"code": "sentinelThreat" if sentinel_wins else "threatExit", "kind": piece.kind})
    elif move.kind == "move":
        costs = bot.exit_costs(state.heights, side)
        before_t = math.ceil(costs[piece.sq] / C.MOVEMENT[piece.kind])
        after_t = math.ceil(costs[move.to] / C.MOVEMENT[piece.kind])
        if after_t < before_t:
            notes.append({"code": "advance", "kind": piece.kind, "turns": after_t})
    return notes


# --- Génération ---------------------------------------------------------------------------

PAIRINGS = ((1, 3), (2, 3), (2, 4), (3, 3), (3, 4), (2, 2), (3, 5), (4, 4))


def _quick_candidate(state: GameState, deadline: float) -> bool:
    if state.over or _choices(state) < MIN_CHOICES or state.ply > state.move_limit - 12:
        return False
    ranked = rank_moves(state, QUICK_DEPTH, deadline)
    if len(ranked) < 2:
        return False
    best, second = ranked[0][0], ranked[1][0]
    return (best >= MATE and best > second) or (second <= -MATE < best) or (
        best - second >= ADV_GAP * 0.8 and best >= ADV_MIN * 0.8)


ENDGAME_PLIES = 30  # fenêtre, avant la fin de partie, où l'on cherche les lignes longues


def _puzzle_at(game_no: int, mode: str, levels, before: GameState, move: Move, deadline: float) -> Puzzle | None:
    """Puzzle commençant par `move` (l'erreur adverse) joué depuis `before`, s'il y en a un."""
    after = apply_move(before, move)
    res = build_line(after, deadline)
    if not res:
        return None
    kind, line, end, tree = res
    tags = themes_of(after, kind, line, end, _threat(after, deadline))
    return Puzzle(
        id=f"q{game_no:04d}{after.ply:03d}", terrain=mode, start=state_to_json(before),
        solution=[move_key(move)] + [move_key(m) for m in line], themes=tags,
        rating=estimate_rating(after, kind, line, tags), side=after.to_move, meta={"levels": list(levels)},
        tree=tree,
    )


def puzzles_from_game(rng: random.Random, game_no: int, per_game: int = 3) -> list[Puzzle]:
    """Joue une partie bot contre bot, puis y cherche des puzzles.

    1. **Fin de partie, à rebours de la victoire** : depuis chaque position du vainqueur
       des `ENDGAME_PLIES` derniers demi-coups, la plus ANCIENNE qui donne une ligne forcée
       donne le puzzle le plus long (gagner en 3, 4, 5 coups au lieu d'1).
    2. **Milieu de partie** : erreurs qui offrent un coup unique (sauvetage, avantage).
    """
    mode = rng.choice(("mountains", "valleys", "highlands", "woodlands", "desert"))
    _, _, heights = generate_terrain(mode, rng.randrange(2**31))
    levels = rng.choice(PAIRINGS)
    if rng.random() < 0.5:
        levels = levels[::-1]
    s = new_game(heights)
    history: list[tuple[GameState, Move]] = []
    while not s.over:
        move = bot.choose_move(s, levels[s.to_move - 1], rng)
        history.append((s, move))
        s = apply_move(s, move)
    found: list[Puzzle] = []
    taken: set[int] = set()  # demi-coups déjà couverts par un puzzle

    def add(i: int, pz: Puzzle) -> None:
        found.append(pz)
        taken.update(range(i - 1, i + len(pz.solution)))

    winner = s.winner
    first = max(1, len(history) - ENDGAME_PLIES)
    for i in range(first, len(history)):
        before, move = history[i - 1]
        if winner is None or before.to_move == winner or i in taken:
            continue  # le puzzle commence par un coup du perdant (son erreur)
        try:
            pz = _puzzle_at(game_no, mode, levels, before, move, time.monotonic() + SEARCH.budget_s)
        except _Timeout:
            continue
        if pz:
            add(i, pz)
            break  # le plus ancien est le plus long ; les suivants en sont des sous-lignes
    for i in range(1, first):
        if len(found) >= per_game:
            break
        before, move = history[i - 1]
        after = history[i][0]
        if any(j in taken for j in range(i - 1, i + 6)):
            continue
        deadline = time.monotonic() + SEARCH.budget_s
        try:
            if _quick_candidate(after, deadline):
                pz = _puzzle_at(game_no, mode, levels, before, move, deadline)
                if pz:
                    add(i, pz)
        except _Timeout:
            pass
    return found


def _game_job(game_no: int) -> list[dict]:
    rng = random.Random(1_000_003 * game_no + 17)  # chaque partie a sa graine : reproductible
    return [p.__dict__ for p in puzzles_from_game(rng, game_no)]


# Part de chaque longueur de solution (coups du joueur) dans le jeu livré.
SHARE = {1: 0.2, 2: 0.3, 3: 0.25, 4: 0.15, 5: 0.1}


def select(pool: list[dict], count: int, seed: int = 7) -> list[dict]:
    """Mélange équilibré par longueur de solution : les puzzles longs (durs) ne sont pas
    noyés sous les puzzles en 1 coup. Une longueur en manque est complétée par les autres."""
    rng = random.Random(seed)
    by_len: dict[int, list[dict]] = {}
    for p in pool:
        by_len.setdefault(len(p["solution"][1::2]), []).append(p)
    for items in by_len.values():
        rng.shuffle(items)
    chosen: list[dict] = []
    for n, share in SHARE.items():
        chosen += by_len.get(n, [])[: int(count * share)]
    taken = {p["id"] for p in chosen}
    rest = [p for n in sorted(by_len, reverse=True) for p in by_len[n] if p["id"] not in taken]
    chosen += rest[: count - len(chosen)]
    return sorted(chosen, key=lambda p: p["rating"])


def generate(games: int, count: int, workers: int = 8, log=print) -> list[dict]:
    """Joue `games` parties bot contre bot (en parallèle) et garde `count` puzzles."""
    from concurrent.futures import ProcessPoolExecutor

    pool: list[dict] = []
    t0 = time.time()
    with ProcessPoolExecutor(workers) as ex:
        for i, found in enumerate(ex.map(_game_job, range(1, games + 1), chunksize=8), 1):
            pool.extend(found)
            if i % 100 == 0:
                log(f"{i}/{games} parties, {len(pool)} puzzles, {time.time() - t0:.0f} s")
    return select(pool, count)


def save(puzzles: list[dict], path: Path = DATA_FILE) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(puzzles, f, separators=(",", ":"))


def load(path: Path = DATA_FILE) -> list[dict]:
    if not path.exists():
        return []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    import collections
    import sys

    games = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 600
    ps = generate(games, count)
    save(ps)
    themes = collections.Counter(t for p in ps for t in p["themes"])
    print(f"{len(ps)} puzzles -> {DATA_FILE}")
    print(themes.most_common())
