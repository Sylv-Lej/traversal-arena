"""Sérialisation JSON (camelCase) des objets envoyés au front."""

import time

from app.engine import GameState, Move, Piece, legal_moves
from app.engine import config as C
from app.services import games as svc
from app.services import ranks
from app.services.gametypes import BOT_CLASS, DEFAULT_CLASS, RATED_CLASSES, display_class
from app.services.store import Game, GameSummary, MoveRecord, Player, store


def piece_json(p: Piece) -> dict:
    return {"id": p.id, "owner": p.owner, "kind": p.kind, "sq": p.sq}


def combat_json(move: Move) -> dict | None:
    if not move.combat:
        return None
    c = move.combat
    return {
        "attack": c.attack,
        "defense": c.defense,
        "attackTerms": [{"label": t.label, "value": t.value} for t in c.attack_terms],
        "defenseTerms": [{"label": t.label, "value": t.value} for t in c.defense_terms],
    }


def move_json(m: Move) -> dict:
    return {
        "pieceId": m.piece_id,
        "kind": m.kind,
        "to": m.to,
        "path": list(m.path),
        "cost": m.cost,
        "special": m.special,
        "combat": combat_json(m),
    }


def record_json(r: MoveRecord) -> dict:
    return {
        "ply": r.ply,
        "side": r.side,
        "pieceId": r.piece_id,
        "kind": r.kind,
        "special": r.special,
        "from": r.frm,
        "to": r.to,
        "path": list(r.path),
        "notation": r.notation,
        "combat": r.combat,
        "capturedId": r.captured_id,
        "remainingMs": r.remaining_ms,
    }


def position_json(s: GameState) -> dict:
    return {
        "ply": s.ply,
        "toMove": s.to_move,
        "pieces": [piece_json(p) for p in s.pieces],
        "scores": list(s.scores),
        "finished": [piece_json(p) for p in s.finished],
        "captured": [piece_json(p) for p in s.captured],
    }




def rank_json(p: Player, time_class: str) -> dict | None:
    if p.is_bot:  # un bot a un seul classement, contre les joueurs (jamais « en placement »)
        r = p.ratings.get(BOT_CLASS)
        return ranks.rank_from(r.rating, ranks.PLACEMENT_GAMES) if r else None
    if time_class not in RATED_CLASSES:
        return None
    r = p.ratings.get(time_class)
    return ranks.rank_from(r.rating if r else 1500, r.games if r else 0,
                           legend=p.id in store.legends(time_class))


def player_json(p: Player | None, time_class: str = DEFAULT_CLASS) -> dict | None:
    if p is None:
        return None
    r = p.ratings.get(BOT_CLASS if p.is_bot else time_class)
    return {
        "id": p.id,
        "name": p.name,
        "country": p.country,
        "isBot": p.is_bot,
        "rating": round(r.rating) if r else None,
        "provisional": (r.rd > 110) if r else True,
        "rank": rank_json(p, time_class),
    }


def imported_players(imported: dict) -> list[dict]:
    """Joueurs d'une partie importée : sans compte ici, pseudo et classement d'origine."""
    return [{"id": "", "name": name, "country": None, "isBot": False, "rating": rating,
             "provisional": False, "rank": None}
            for name, rating in zip(imported["names"], imported["ratings"])]


def me_json(p: Player) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "isGuest": p.is_guest,
        "email": p.email,
        "emailVerified": p.email_verified_at is not None,
        "country": p.country,
        "ratings": {
            tc: {"rating": round(r.rating), "games": r.games, "wins": r.wins,
                 "losses": r.losses, "draws": r.draws, "provisional": r.rd > 110,
                 "rank": rank_json(p, tc)}
            for tc, r in p.ratings.items()
        },
    }


# Anti-triche : en partie en ligne, un spectateur voit la partie avec un tour complet de
# retard (2 demi-coups). Un complice qui regarde ne connaît donc jamais la position
# courante. Tout est dévoilé à la fin de la partie.
SPECTATOR_DELAY_PLIES = 2


def spectator_delay(game: Game, viewer: Player | None) -> int:
    """Nombre de demi-coups cachés à ce spectateur (0 pour un joueur)."""
    if game.mode != "online" or game.status != "active" or game.sides_of(viewer.id if viewer else None):
        return 0
    return min(SPECTATOR_DELAY_PLIES, len(game.moves))


def _delayed_clock(game: Game, shown: int) -> list[int]:
    """Pendules telles qu'elles étaient après le dernier coup montré (arrêtées)."""
    out = [game.initial_ms or 0, game.initial_ms or 0]
    for r in game.moves[:shown]:
        if r.remaining_ms is not None:
            out[r.side - 1] = r.remaining_ms
    return out


def game_view(game: Game, viewer: Player | None, spectators: int = 0, match: dict | None = None) -> dict:
    delay = spectator_delay(game, viewer)
    shown = len(game.moves) - delay  # coups visibles par ce lecteur
    s = game.states[shown] if delay else game.state
    you = game.sides_of(viewer.id if viewer else None)
    legal = []
    if game.status == "active" and s.to_move in you:
        legal = [move_json(m) for m in legal_moves(s)]
    tc_class = display_class(game.time_class)
    players = [player_json(store.players.get(pid) if pid else None, tc_class) for pid in game.players]
    if game.imported:
        players = imported_players(game.imported)
    # Partie amicale, bot ou locale : le rang du joueur n'est pas en jeu (une manche de
    # match tactique en ligne, si : c'est le match qui est classé). Un bot garde le sien :
    # c'est son emblème, et son classement bouge avec ses résultats.
    if not game.rated and not (match and match.get("rated")):
        for pj in players:
            if pj and not pj["isBot"]:
                pj["rank"] = None
    if game.rating_before:
        for i, pj in enumerate(players):
            if pj:
                pj["rating"] = round(game.rating_after[i]) if game.status == "finished" else round(game.rating_before[i])
    return {
        "id": game.id,
        "mode": game.mode,
        "status": game.status,
        "version": game.version,
        "terrain": {"mode": game.terrain_mode, "seed": game.seed, "heights": list(s.heights)},
        "position": position_json(s),
        "moveLimit": s.move_limit,
        "players": players,
        "you": you,
        "createdBy": game.created_by,
        "botLevel": game.bot_level,
        "timeControl": (game.imported or {}).get("timeControl") or svc.time_control_label(game),
        "source": {"site": game.imported["site"], "url": game.imported["url"]} if game.imported else None,
        "timeClass": game.time_class,
        "rated": game.rated,
        "clock": ({
            "remaining": svc.remaining_now(game),
            "running": s.to_move if svc.clock_running(game) else None,
            "incrementMs": game.increment_ms,
        } if not delay else {
            "remaining": _delayed_clock(game, shown),
            "running": None,
            "incrementMs": game.increment_ms,
        }) if game.timed else None,
        "moves": [record_json(r) for r in game.moves[:shown]],
        "legalMoves": legal,
        "result": {"winner": s.winner, "reason": s.reason} if s.over else None,
        "drawOffer": None if delay else game.draw_offer,
        "delay": delay,
        "spectators": spectators,
        "match": match,
        "rematchOffer": game.rematch_offer,
        "rematchId": game.rematch_id,
        "rankChange": game.rank_change,
        "ratingChange": [
            round(a - b) for a, b in zip(game.rating_after, game.rating_before)
        ] if game.rating_after else None,
        "rules": {
            "movement": C.MOVEMENT,
            "strength": C.STRENGTH,
            "finishersToEnd": C.FINISHERS_TO_END,
        },
    }


def game_summary(g: GameSummary, viewer_id: str | None = None) -> dict:
    tc = None
    if g.initial_ms is not None:
        tc = f"{g.initial_ms // 60_000}+{g.increment_ms // 1000}"
    return {
        "id": g.id,
        "mode": g.mode,
        "status": g.status,
        "terrain": g.terrain_mode,
        "timeControl": tc,
        "players": [player_json(store.players.get(pid) if pid else None) for pid in g.players],
        "you": g.sides_of(viewer_id),
        "result": {"winner": g.winner, "reason": g.reason} if g.reason else None,
        "scores": list(g.scores),
        # Partie en ligne en cours vue par un tiers : même retard que la vue de la partie.
        "ply": max(0, g.ply - SPECTATOR_DELAY_PLIES)
        if g.mode == "online" and g.status == "active" and not g.sides_of(viewer_id) else g.ply,
        "createdAt": g.created_at,
    }


# --- Matchs tactiques ------------------------------------------------------------------


def match_brief(m) -> dict:
    """Résumé d'un match, joint à la vue de chacune de ses manches."""
    return {"id": m.id, "round": m.round, "status": m.status, "players": list(m.players),
            "score": m.score, "rated": m.rated, "winner": m.winner}


def match_view(m, viewer: Player | None) -> dict:
    from app.services import matches

    st = matches.next_step(m)
    players = [player_json(store.players.get(pid) if pid else None, "tactic") for pid in m.players]
    if not m.rated:
        for pj in players:
            if pj and not pj["isBot"]:
                pj["rank"] = None
    if m.rating_before:
        for i, pj in enumerate(players):
            if pj:
                pj["rating"] = round(m.rating_after[i]) if m.status == "finished" else round(m.rating_before[i])
    cur = m.current
    return {
        "id": m.id,
        "mode": m.mode,
        "status": m.status,
        "version": m.version,
        "players": players,
        "you": m.sides_of(viewer.id if viewer else None),
        "createdBy": m.created_by,
        "botLevel": m.bot_level,
        "round": m.round,
        "rounds": m.rounds,
        "maps": list(matches.MAPS),
        "step": {"action": st[0], "by": st[1]} if st else None,
        "available": matches.available(m),
        "deadlineMs": max(0, int((m.deadline_at - time.time()) * 1000)) if m.deadline_at else None,
        "vetoMs": int(matches.VETO_S * 1000),
        "currentGameId": cur["gameId"] if cur and m.status == "playing" else None,
        "score": m.score,
        "winner": m.winner,
        "rated": m.rated,
        "ratingChange": [round(a - b) for a, b in zip(m.rating_after, m.rating_before)] if m.rating_after else None,
        "rankChange": m.rank_change,
    }
