// Arène des bots : types des réponses de l'API (`backend/app/services/arena.py`).

import type { Dict } from "./i18n/dict";
import type { Rank } from "./types";

export type BotStatus = "pending" | "active" | "rejected" | "retired";

export interface ArenaRating {
  rating: number | null;
  margin: number | null;
  games: number;
  wins: number;
  losses: number;
  draws: number;
  provisional: boolean;
  /** Division (Ardoise IV … Maître), comme les joueurs ; placement pendant les 10 premières parties. */
  tier: Rank | null;
}

export interface Author {
  id: string;
  name: string;
  country: string | null;
}

export interface ArenaRow extends ArenaRating {
  rank: number | null;
  id: string;
  name: string;
  version: number | null;
  /** Niveau d'un bot maison (1 à 5), sinon null. */
  house: number | null;
  author: Author | null;
}

export interface ArenaGame {
  id: string;
  side: 1 | 2;
  opponent: { id: string; name?: string; version?: number | null; house?: number | null };
  result: "win" | "loss" | "draw";
  reason: string | null;
  ply: number;
  endedAt: number;
  terrain: string;
  /** Jouée avec la mise en place actuelle des pièces (sinon : une ancienne). */
  currentSetup: boolean;
}

export interface ArenaBot extends ArenaRating {
  id: string;
  name: string;
  version: number | null;
  house: number | null;
  status: BotStatus;
  error?: string | null;
  size?: number;
  sha256?: string;
  createdAt?: number;
  queued?: number;
  author: Author | null;
  versions: { id: string; version: number; status: BotStatus; createdAt: number; rating: number | null; games: number }[];
  recent: ArenaGame[];
}

export interface MyBot extends ArenaRating {
  id: string;
  name: string;
  version: number;
  status: BotStatus;
  error: string | null;
  createdAt: number;
}

export interface ArenaInfo {
  /** Parties de l'arène consultables (relecture, rejeu sur l'accueil) ; sinon, résultats seuls. */
  replays: boolean;
  fuelPerMove: number;
  maxWasmKb: number;
  memoryMb: number;
  maxLiveBots: number;
  placementGames: number;
  dailyGames: number;
}

/** Nom affiché : les bots maison sont traduits, les autres portent leur version. */
export function arenaName(b: { name?: string; version?: number | null; house?: number | null }, t: Dict): string {
  if (b.house) return t.common.bots[b.house]?.name ?? b.name ?? "";
  return b.version ? `${b.name} ${t.arena.version(b.version)}` : b.name ?? "";
}
