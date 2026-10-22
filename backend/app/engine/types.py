from dataclasses import dataclass, field

from app.engine.config import SIZE


def sq(x: int, y: int) -> int:
    return y * SIZE + x


def xy(square: int) -> tuple[int, int]:
    return square % SIZE, square // SIZE


@dataclass(frozen=True, slots=True)
class Piece:
    id: str
    owner: int  # 1 = rouge (part de y=0), 2 = bleu (part de y=9)
    kind: str
    sq: int


@dataclass(frozen=True, slots=True)
class Term:
    """Une ligne du détail d'un calcul de force (affichée dans l'aperçu de combat)."""

    label: str
    value: int


@dataclass(frozen=True, slots=True)
class Combat:
    attack: int
    defense: int
    attack_terms: tuple[Term, ...]
    defense_terms: tuple[Term, ...]


@dataclass(frozen=True, slots=True)
class Move:
    piece_id: str
    # move | attack | exit | pass
    kind: str
    # Case d'arrivée ; None pour une sortie ou une passe.
    to: int | None
    # Cases traversées, départ inclus, arrivée incluse (sortie : dernière case du plateau).
    path: tuple[int, ...] = ()
    cost: int = 0
    # None (déplacement normal) | diag | leap (coups spéciaux de l'Explorateur)
    special: str | None = None
    combat: Combat | None = None


@dataclass(frozen=True, slots=True)
class GameState:
    heights: tuple[int, ...]
    pieces: tuple[Piece, ...]
    to_move: int
    ply: int = 0
    scores: tuple[int, int] = (0, 0)
    # Pièces sorties (dans l'ordre) et capturées, avec leur dernière case.
    finished: tuple[Piece, ...] = ()
    captured: tuple[Piece, ...] = ()
    over: bool = False
    winner: int | None = None
    # score | sentinel | move_limit (+ resign / timeout / agreement, posés par le service)
    reason: str | None = None
    move_limit: int = 200
    _index: dict = field(default=None, compare=False, repr=False, hash=False)

    def occupancy(self) -> dict[int, Piece]:
        idx = self._index
        if idx is None:
            idx = {p.sq: p for p in self.pieces}
            object.__setattr__(self, "_index", idx)
        return idx

    def piece(self, piece_id: str) -> Piece | None:
        for p in self.pieces:
            if p.id == piece_id:
                return p
        return None
