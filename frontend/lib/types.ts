// Miroir des vues JSON de l'API (backend/app/services/views.py).

export type Side = 1 | 2;
export type Kind = "explorer" | "vanguard" | "sentinel";
export type MoveKind = "move" | "attack" | "exit" | "pass";

export interface PieceT {
  id: string;
  owner: Side;
  kind: Kind;
  sq: number;
}

export interface Term {
  label: string;
  value: number;
}

export interface CombatT {
  attack: number;
  defense: number;
  attackTerms: Term[];
  defenseTerms: Term[];
}

export interface LegalMove {
  pieceId: string;
  kind: MoveKind;
  to: number | null;
  path: number[];
  cost: number;
  special: "diag" | "leap" | null;
  combat: CombatT | null;
}

export interface MoveRecord {
  ply: number;
  side: Side;
  pieceId: string;
  kind: MoveKind;
  special: "diag" | "leap" | null;
  from: number | null;
  to: number | null;
  path: number[];
  notation: string;
  combat: CombatT | null;
  capturedId: string | null;
  remainingMs: number | null;
}

export interface Position {
  ply: number;
  toMove: Side;
  pieces: PieceT[];
  scores: [number, number];
  finished: PieceT[];
  captured: PieceT[];
}

/** Rang « à la LoL » calculé par l'API à partir du classement Glicko-2. */
export interface Rank {
  tier: string | null; // slate … master | legend ; null pendant le placement
  name: string;
  division: number | null; // 4 (IV) … 1 (I) ; null pour Maître / Légende / placement
  label: string;
  lp: number;
  placement: { played: number; total: number } | null;
  next: { label: string; rating: number; tier: string; division: number | null } | null;
}

export interface PlayerCard {
  id: string;
  name: string;
  country?: string | null; // ISO 3166-1 alpha-2 : drapeau
  isBot: boolean;
  rating: number | null;
  provisional: boolean;
  rank?: Rank | null;
}

export type GameStatus = "waiting" | "active" | "finished" | "aborted";
export type GameMode = "local" | "bot" | "online" | "arena";

export interface GameView {
  id: string;
  mode: GameMode;
  status: GameStatus;
  version: number;
  terrain: { mode: string; seed: number; heights: number[] };
  position: Position;
  moveLimit: number;
  players: (PlayerCard | null)[];
  you: Side[];
  createdBy: string;
  botLevel: number | null;
  timeControl: string | null;
  timeClass: string;
  rated: boolean;
  clock: { remaining: [number, number]; running: Side | null; incrementMs: number } | null;
  moves: MoveRecord[];
  legalMoves: LegalMove[];
  result: { winner: Side | null; reason: string } | null;
  drawOffer: Side | null;
  rematchOffer: Side | null;
  rematchId: string | null;
  ratingChange: [number, number] | null;
  rankChange: { before: Rank; after: Rank }[] | null;
  /** Demi-coups cachés à ce spectateur (anti-triche) ; 0 pour un joueur. */
  delay: number;
  spectators: number;
  /** Manche d'un match tactique (sinon null). */
  match: MatchBrief | null;
}

export interface MatchBrief {
  id: string;
  round: number;
  status: MatchStatus;
  players: (string | null)[]; // joueur 1, joueur 2
  score: [number, number];
  rated: boolean;
  winner: 1 | 2 | null;
}

export type MatchStatus = "waiting" | "veto" | "playing" | "finished" | "aborted";

export interface MatchRound {
  round: number;
  picker: 1 | 2 | null; // null : manche décisive (carte tirée au sort)
  red: 1 | 2; // joueur qui a les Rouges
  bans: { by: 1 | 2; map: string }[];
  pick: string | null;
  gameId: string | null;
  winner: 0 | 1 | 2 | null; // 0 : nulle
  done: boolean;
}

/** Match tactique (Bo2 + bans / choix de carte). */
export interface MatchView {
  id: string;
  mode: GameMode;
  status: MatchStatus;
  version: number;
  players: (PlayerCard | null)[];
  you: (1 | 2)[];
  createdBy: string;
  botLevel: number | null;
  round: number;
  rounds: MatchRound[];
  maps: string[];
  step: { action: "ban" | "pick"; by: 1 | 2 } | null;
  available: string[];
  deadlineMs: number | null;
  vetoMs: number;
  currentGameId: string | null;
  score: [number, number];
  winner: 1 | 2 | null;
  rated: boolean;
  ratingChange: [number, number] | null;
  rankChange: { before: Rank; after: Rank }[] | null;
}

/** Partie en ligne en cours (page « Regarder »). */
export interface LiveGame {
  id: string;
  players: (PlayerCard | null)[];
  timeControl: string | null;
  timeClass: string;
  rated: boolean;
  terrain: string;
  ply: number;
  spectators: number;
  match: MatchBrief | null;
  createdAt: number;
}

export interface Me {
  id: string;
  name: string;
  isGuest: boolean;
  email: string | null;
  /** Adresse confirmée (lien reçu par email) : exigée pour inscrire un bot. */
  emailVerified: boolean;
  country: string | null;
  ratings: Record<
    string,
    { rating: number; games: number; wins: number; losses: number; draws: number; provisional: boolean; rank?: Rank | null }
  >;
}

export interface GameSummary {
  id: string;
  mode: GameMode;
  status: GameStatus;
  terrain: string;
  timeControl: string | null;
  players: (PlayerCard | null)[];
  you: Side[];
  result: { winner: Side | null; reason: string } | null;
  scores: [number, number];
  ply: number;
  createdAt: number;
}

export interface LobbyInfo {
  online: number;
  playing: number;
  seeking: Record<string, number>;
  types: string[];
  terrains: string[];
  /** Classement de chaque bot contre les joueurs (il bouge avec ses résultats). */
  bots: { level: number; name: string; rating: number | null; games: number; rank: Rank | null }[];
}

// --- Bilan de partie (analyse moteur) -----------------------------------------------

export type MoveClass = "best" | "excellent" | "good" | "inaccuracy" | "mistake" | "blunder" | "forced";

/** Évaluation côté Rouge, en points de score (+ = avantage Rouge) ; `win` = victoire forcée. */
export interface Eval {
  score: number;
  win: Side | null;
}

export interface AnalyzedMove {
  ply: number;
  side: Side;
  notation: string;
  class: MoveClass;
  accuracy: number;
  eval: Eval;
  loss: number;
  best: { pieceId: string; kind: string; to: number | null; path: number[]; special: string | null; notation: string; eval: Eval } | null;
}

export interface Analysis {
  version: number;
  depth: number;
  initialEval: Eval;
  moves: AnalyzedMove[];
  accuracy: [number | null, number | null];
  counts: [Partial<Record<MoveClass, number>>, Partial<Record<MoveClass, number>>];
}

export interface AnalysisStatus {
  status: "none" | "queued" | "running" | "done" | "error";
  done: number;
  total: number;
  result?: Analysis;
}

// --- Puzzles -----------------------------------------------------------------------------

export interface PuzzleAttempt {
  id: string;
  puzzleId: string;
  mode: "rated" | "retry" | "daily" | "rush";
  status: "playing" | "solved" | "failed";
  rated: boolean;
  hinted: boolean;
  revealed: boolean;
  side: Side;
  terrain: { mode: string; heights: number[] };
  start: Position;
  moves: MoveRecord[]; // coups joués jusqu'ici (le 1er : celui de l'adversaire)
  positions: Position[]; // position après chaque coup (0 = départ)
  position: Position;
  legalMoves: LegalMove[];
  playerMoves: number;
  goal: "win" | "save" | "advantage";
  wrong: MoveRecord | null;
  wrongPosition?: Position;
  playerRating: number;
  daily: string | null;
  solution?: MoveRecord[];
  solutionPositions?: Position[];
  /** Explication de chaque coup de la solution (null : coup adverse). */
  notes?: (PuzzleNote[] | null)[];
  puzzle?: { rating: number; themes: string[]; plays: number; solves: number };
  ratingChange?: { before: number; after: number };
  rushId?: string;
}

export interface PuzzleNote {
  code: string;
  kind?: string;
  target?: string;
  attack?: number;
  defense?: number;
  points?: number;
  value?: number;
  count?: number;
  turns?: number;
  score?: [number, number];
  side?: Side;
}

export interface PuzzleRush {
  id: string;
  mode: string;
  status: "running" | "over";
  score: number;
  strikes: number;
  maxStrikes: number;
  maxPuzzles: number;
  remainingMs: number | null;
  attempt: PuzzleAttempt | null;
  best: number;
  history: { solved: boolean; rating: number; puzzleId: string }[];
}

export interface PuzzleStats {
  rating: number;
  provisional: boolean;
  rated: number;
  solved: number;
  rank: Rank;
  tried: number;
  rushBest: Record<string, number>;
  total: number;
}
