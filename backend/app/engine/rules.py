"""Application des coups et fin de partie (R4.7, R6, R7, R8)."""

from dataclasses import replace

from app.engine import config as C
from app.engine.movegen import legal_moves, rows_to_go
from app.engine.types import GameState, Move, Piece

LETTERS = "abcdefghij"
INITIALS = {C.EXPLORER: "E", C.VANGUARD: "V", C.SENTINEL: "S"}


class IllegalMove(ValueError):
    pass


def new_game(heights: tuple[int, ...], move_limit: int = C.MOVE_LIMIT, setup: str = C.SETUP) -> GameState:
    """R3.2 Mise en place symétrique sur les colonnes 2..7 des rangées de départ (`setup` :
    une des `C.SETUPS`, celle du début de la partie)."""
    pieces: list[Piece] = []
    counters: dict[str, int] = {}
    for owner, row in ((1, 0), (2, C.SIZE - 1)):
        for col, kind in zip(C.SETUP_COLUMNS, C.SETUPS[setup]):
            # Le joueur 2 voit le plateau tourné de 180° : même ordre, colonnes miroir.
            x = col if owner == 1 else C.SIZE - 1 - col
            key = f"{owner}{kind}"
            counters[key] = counters.get(key, 0) + 1
            pid = f"{'rb'[owner - 1]}{INITIALS[kind].lower()}{counters[key]}"
            pieces.append(Piece(pid, owner, kind, row * C.SIZE + x))
    return GameState(
        heights=tuple(heights),
        pieces=tuple(pieces),
        to_move=C.FIRST_PLAYER,
        move_limit=move_limit,
    )


def square_name(square: int) -> str:
    return f"{LETTERS[square % C.SIZE]}{square // C.SIZE + 1}"


def notation(state: GameState, move: Move) -> str:
    if move.kind == "pass":
        return "—"
    piece = state.piece(move.piece_id)
    assert piece is not None
    head = f"{INITIALS[piece.kind]}{square_name(piece.sq)}"
    if move.kind == "exit":
        return f"{head}↑"
    sep = "x" if move.kind == "attack" else "-"
    mark = {"diag": "◇", "leap": "»"}.get(move.special or "", "")
    return f"{head}{sep}{square_name(move.to)}{mark}"


def find_move(state: GameState, piece_id: str, kind: str, to: int | None) -> Move:
    for move in legal_moves(state):
        if move.kind == kind and move.piece_id == piece_id and move.to == to:
            return move
    raise IllegalMove("Coup illégal.")


def adjudicate(state: GameState) -> int | None:
    """R8.3 Départage à la limite de coups. Renvoie le vainqueur (ou None = nulle)."""
    s1, s2 = state.scores
    if s1 or s2:
        return 1 if s1 > s2 else 2 if s2 > s1 else None
    best: dict[int, tuple[int, int]] = {}
    for p in state.pieces:
        key = (rows_to_go(p.owner, p.sq), -C.STRENGTH[p.kind])
        if p.owner not in best or key < best[p.owner]:
            best[p.owner] = key
    if 1 not in best or 2 not in best:
        return 1 if 1 in best else 2 if 2 in best else None
    if best[1] == best[2]:
        return None
    return 1 if best[1] < best[2] else 2


def apply_move(state: GameState, move: Move) -> GameState:
    """Applique un coup supposé légal (vérifier via `find_move` côté service)."""
    if state.over:
        raise IllegalMove("La partie est terminée.")
    other = 2 if state.to_move == 1 else 1
    pieces = list(state.pieces)
    scores = list(state.scores)
    finished = state.finished
    captured = state.captured
    over, winner, reason = False, None, None

    if move.kind != "pass":
        idx = next(i for i, p in enumerate(pieces) if p.id == move.piece_id)
        piece = pieces[idx]
        if move.kind == "exit":
            # R6.2 La pièce quitte le plateau et marque sa Force.
            del pieces[idx]
            finished = finished + (replace(piece, sq=move.path[-1]),)
            scores[piece.owner - 1] += C.STRENGTH[piece.kind]
            if len(finished) == 1 and piece.kind == C.SENTINEL:
                over, winner, reason = True, piece.owner, "sentinel"  # R8.2
            elif len(finished) >= C.FINISHERS_TO_END:
                s1, s2 = scores
                over, reason = True, "score"  # R8.1
                winner = 1 if s1 > s2 else 2 if s2 > s1 else None
        else:
            if move.kind == "attack":
                # R7.2 La pièce vaincue sort du plateau, sans marquer.
                tidx = next(i for i, p in enumerate(pieces) if p.sq == move.to)
                captured = captured + (pieces[tidx],)
                del pieces[tidx]
                idx = next(i for i, p in enumerate(pieces) if p.id == move.piece_id)
            pieces[idx] = replace(piece, sq=move.to)

    nxt = GameState(
        heights=state.heights,
        pieces=tuple(pieces),
        to_move=other,
        ply=state.ply + 1,
        scores=(scores[0], scores[1]),
        finished=finished,
        captured=captured,
        over=over,
        winner=winner,
        reason=reason,
        move_limit=state.move_limit,
    )
    if not over and nxt.ply >= state.move_limit:
        nxt = replace(nxt, over=True, winner=adjudicate(nxt), reason="move_limit", _index=None)
    return nxt


def end_game(state: GameState, winner: int | None, reason: str) -> GameState:
    """Fin hors plateau : abandon, temps écoulé, nulle par accord…"""
    return replace(state, over=True, winner=winner, reason=reason, _index=None)
