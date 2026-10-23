"""Analyse d'une partie terminée (« bilan de partie », comme sur chess.com).

Pour chaque coup joué : le moteur cherche le meilleur coup de la position et évalue le coup
joué avec la MÊME recherche ; la différence, convertie en chances de gagner perdues, donne
une appréciation (meilleur … gaffe) et une précision. Pur et synchrone : le service le
lance dans un thread, position par position, pour publier l'avancement.

Moteur : le bot « orque » (`engine-rs/analysis`), avec un budget de NŒUDS fixe et sans
limite de temps — même bilan sur toute machine, ~profondeur 8. Sans le module Rust (dev
local), repli sur le bot Python de référence, bien plus faible et borné en temps.

Bilan par l'arène (`analysis_jobs`, `arena.py`) : le n°1 du classement des bots propose
le meilleur coup de chaque position, orque note ce coup et le coup joué ; le runner rend
ces notes (`results`) et ce module en tire le même bilan, signé du bot (`engine`).
"""

import math
import time
from dataclasses import dataclass

from app.bot import WIN, Level, _negamax, _ordered, _Timeout, evaluate, native
from app.engine import GameState, Move, apply_move, legal_moves

# Moteur Rust (orque) : nœuds par recherche. 60 000 : profondeur 8 en moyenne, ~0,17 s par
# position sur un Mac M (orque en explore ~14 000 par coup dans l'arène).
ANALYSIS_NODES = 60_000
# Repli Python (sans module Rust) : bot de référence, budget temps en garde-fou.
LEVEL = Level("Analyse", depth=4, beam=9, noise=0.0, budget_s=1.5)
VERSION = 4  # un bilan d'une version antérieure (autre moteur) est recalculé
CAP = 1500  # au-delà, l'avantage est « décisif » : on borne pour les graphes et la précision
MATE = WIN // 2

# Probabilité de gain d'un avantage v (point de vue du joueur au trait) :
# 1 / (1 + e^(-(v + WIN_OFFSET) / WIN_SCALE)). MESURÉES (`python -m app.analysis_calibration`,
# 22/10/2026, moteur orque à 60 000 nœuds) : 200 parties entre bots du site, 7 585 positions
# évaluées par l'analyse elle-même, ajustées sur le résultat final (log-loss 0,596, contre
# 0,632 avec l'ancien barème). Le décalage : à évaluation nulle, le camp au trait gagne ~47 %
# des parties. À refaire si le moteur, son budget ou l'évaluation change.
WIN_SCALE = 107.0
WIN_OFFSET = -18.0

# Appréciation selon les chances de gagner perdues par le coup (en points de %), comme
# lichess : au-delà de 20 %, c'est une gaffe.
THRESHOLDS = (("excellent", 2.0), ("good", 5.0), ("inaccuracy", 10.0), ("mistake", 20.0))


@dataclass
class PositionResult:
    best: Move
    best_score: float  # du point de vue du joueur au trait
    played_score: float
    depth: int
    forced: bool


def _same(a: Move, b: Move) -> bool:
    return a.piece_id == b.piece_id and a.kind == b.kind and a.to == b.to


def analyse_position(state: GameState, played: Move) -> PositionResult:
    forced = len([m for m in legal_moves(state) if m.kind != "pass"]) <= 1
    if native.ENABLED:
        return _analyse_native(state, played, forced)
    return _analyse_python(state, played, forced)


def _analyse_native(state: GameState, played: Move, forced: bool) -> PositionResult:
    piece = next((i for i, p in enumerate(state.pieces) if p.id == played.piece_id), -1)
    (bp, bk, bt), best_score, played_score, depth = native.traversal_rs.analyse_deep(
        native.pack(state), (piece, played.kind, -1 if played.to is None else played.to), ANALYSIS_NODES)
    best = native.to_move(state, bp, bk, bt)
    if _same(best, played):
        best = played  # garde le chemin et le coup spécial réellement joués
    return PositionResult(best, float(best_score), float(played_score), depth, forced)


def _analyse_python(state: GameState, played: Move, forced: bool) -> PositionResult:
    moves = _ordered(state)
    deadline = time.monotonic() + LEVEL.budget_s
    best, best_score, depth_done = moves[0], -math.inf, 0
    for depth in range(1, LEVEL.depth + 1):
        try:
            alpha = -math.inf
            cur: dict[int, float] = {}
            for i, m in enumerate(moves):
                child = apply_move(state, m)
                s = evaluate(child, state.to_move) if depth == 1 else -_negamax(
                    child, depth - 1, -math.inf, -alpha + 1e-9, LEVEL, deadline)
                cur[i] = s
                alpha = max(alpha, s)
        except _Timeout:
            break
        depth_done = depth
        order = sorted(cur, key=lambda i: cur[i], reverse=True)
        best, best_score = moves[order[0]], cur[order[0]]
        moves = [moves[i] for i in order]  # meilleure coupe à l'itération suivante
    if _same(best, played):
        played_score = best_score
    else:
        # Fenêtre complète : le score exact du coup joué (pas une borne).
        child = apply_move(state, played)
        d = max(1, depth_done)
        played_score = evaluate(child, state.to_move) if d == 1 else -_negamax(
            child, d - 1, -math.inf, math.inf, LEVEL, math.inf)
        played_score = min(played_score, best_score)  # le meilleur coup est le meilleur
    return PositionResult(best, best_score, played_score, depth_done, forced)


def _cap(v: float) -> float:
    return max(-CAP, min(CAP, v))


def win_prob(v: float) -> float:
    """Probabilité de gain estimée (0..1) d'un avantage `v` (point de vue du joueur)."""
    if v >= MATE:
        return 1.0
    if v <= -MATE:
        return 0.0
    return 1 / (1 + math.exp(-(_cap(v) + WIN_OFFSET) / WIN_SCALE))


def accuracy(best: float, played: float) -> float:
    """Précision d'un coup (0..100), formule de lichess sur la chute de probabilité de gain."""
    drop = max(0.0, win_prob(best) - win_prob(played)) * 100
    return max(0.0, min(100.0, 103.1668 * math.exp(-0.04354 * drop) - 3.1669))


def classify(r: PositionResult, same: bool = False) -> str:
    """`same` : le coup joué est celui que le moteur préfère."""
    if r.forced:
        return "forced"
    if same or r.played_score >= r.best_score:
        return "best"
    if r.best_score >= MATE > r.played_score:
        return "blunder"  # victoire forcée manquée
    drop = (win_prob(r.best_score) - win_prob(r.played_score)) * 100
    for name, limit in THRESHOLDS:
        if drop <= limit:
            return name
    return "blunder"


def eval_json(v_red: float) -> dict:
    """Évaluation côté Rouge : en points (100 = 1 point de score) ou victoire forcée."""
    if abs(v_red) >= MATE:
        return {"score": CAP / 100 if v_red > 0 else -CAP / 100, "win": 1 if v_red > 0 else 2}
    return {"score": round(_cap(v_red) / 100, 2), "win": None}


def move_json(m: Move) -> dict:
    return {"pieceId": m.piece_id, "kind": m.kind, "to": m.to, "path": list(m.path), "special": m.special}


def analyse_game(states: list[GameState], records: list, progress=None,
                 results: list[PositionResult] | None = None, engine: dict | None = None) -> dict:
    """Bilan complet. `records` : coups joués (piece_id, kind, to, path, special, side,
    ply, notation) ; `progress(i, n)` est appelé après chaque position analysée.
    `results` : les positions déjà notées (bilan par l'arène), une par coup ; `engine` :
    le bot qui a proposé les meilleurs coups (None : orque seul)."""
    from app.engine import notation

    out_moves = []
    depths: list[int] = []
    acc: dict[int, list[float]] = {1: [], 2: []}
    counts: dict[int, dict[str, int]] = {1: {}, 2: {}}
    initial = evaluate(states[0], 1) if not states[0].over else 0.0
    if results and results[0]:
        initial = results[0].best_score if states[0].to_move == 1 else -results[0].best_score
    elif not states[0].over:
        initial = analyse_position(states[0], _ordered(states[0])[0]).best_score
        initial = initial if states[0].to_move == 1 else -initial
    for i, rec in enumerate(records):
        state = states[i]
        played = Move(rec.piece_id, rec.kind, rec.to, tuple(rec.path), 0, rec.special)
        if rec.kind == "pass":
            r = PositionResult(played, 0.0, 0.0, 0, True)
            after_red = out_moves[-1]["_red"] if out_moves else initial
        else:
            r = results[i] if results else analyse_position(state, played)
            after_red = r.played_score if rec.side == 1 else -r.played_score
            best_red = r.best_score if rec.side == 1 else -r.best_score
        cls = "forced" if rec.kind == "pass" else classify(r, _same(r.best, played))
        a = 100.0 if cls == "forced" else accuracy(r.best_score, r.played_score)
        if cls != "forced":
            acc[rec.side].append(a)
        counts[rec.side][cls] = counts[rec.side].get(cls, 0) + 1
        entry = {
            "ply": rec.ply,
            "side": rec.side,
            "notation": rec.notation,
            "class": cls,
            "accuracy": round(a, 1),
            "eval": eval_json(after_red),
            "_red": after_red,
            "loss": round(max(0.0, _cap(r.best_score) - _cap(r.played_score)) / 100, 2),
            "best": None,
        }
        if r.depth:
            depths.append(r.depth)
        if rec.kind != "pass" and not _same(r.best, played):
            entry["best"] = {**move_json(r.best), "notation": notation(state, r.best),
                             "eval": eval_json(best_red)}
        out_moves.append(entry)
        if progress:
            progress(i + 1, len(records))
    for e in out_moves:
        del e["_red"]
    return {
        "version": VERSION,
        "engine": engine,
        # Profondeur moyenne atteinte (budget de nœuds : elle varie d'une position à l'autre).
        "depth": round(sum(depths) / len(depths)) if depths else LEVEL.depth,
        "initialEval": eval_json(initial),
        "moves": out_moves,
        "accuracy": [round(sum(v) / len(v), 1) if v else None for v in (acc[1], acc[2])],
        "counts": [counts[1], counts[2]],
    }
