// Constantes et libellés du jeu côté interface (les règles, elles, sont dans le backend).

import type { Kind, Rank } from "./types";

export const SIZE = 10;
export const LETTERS = "abcdefghij";

// Données du jeu côté interface. Les TEXTES (noms, descriptions) sont dans le
// dictionnaire : `t.common.pieces[kind]`, `t.common.terrains[key]`, `t.common.bots[level]`…
export const PIECES: Record<Kind, { movement: number; strength: number }> = {
  explorer: { movement: 5, strength: 1 },
  vanguard: { movement: 4, strength: 2 },
  sentinel: { movement: 3, strength: 3 },
};

export const TERRAINS: Record<string, { swatch: string[] }> = {
  random: { swatch: ["#5b8c4a", "#9a8f7a", "#c9a46a"] },
  mountains: { swatch: ["#4f7d3f", "#a3a39b", "#f5f7fa"] },
  valleys: { swatch: ["#2d6e7e", "#5b9150", "#b8b3a0"] },
  highlands: { swatch: ["#5f7d42", "#86804f", "#8a7388"] },
  woodlands: { swatch: ["#2f5d2e", "#4f8443", "#98b86b"] },
  desert: { swatch: ["#d4b07a", "#b87a45", "#8a5333"] },
};

/** Types de partie (classements). Libellés : `t.common.timeClasses[type]`,
 * descriptions : `t.common.typeDesc[type]`. Le tactique se joue en match (Bo2 + bans). */
export type GameType = "bullet" | "classic" | "tactic";
export const GAME_TYPES: { type: GameType; clock: string }[] = [
  { type: "bullet", clock: "1+1" },
  { type: "classic", clock: "5+0" },
  { type: "tactic", clock: "2+0" },
];
export const CLASSES: GameType[] = ["bullet", "classic", "tactic"];
/** Types de carte jouables en match tactique (bans / choix). */
export const MAP_TYPES = ["mountains", "valleys", "highlands", "woodlands", "desert"];

// Chaque bot a un rang (son emblème). Nom et description : `t.common.bots[level]`.
// Valeurs de DÉPART (tournoi entre bots, ancré sur Galet = 920 : `start_rating` de
// `bot.LEVELS`) : en jeu, on affiche le classement en direct (`/lobby`, cartes joueurs),
// qui bouge avec les résultats des bots contre les joueurs. Ceci sert de repli.
export const BOTS: { level: number; rating: number; rank: Rank }[] = [
  { level: 1, rating: 920, rank: botRank("slate", 2) },
  { level: 2, rating: 1090, rank: botRank("bronze", 3) },
  { level: 3, rating: 1520, rank: botRank("gold", 2) },
  { level: 4, rating: 1645, rank: botRank("jade", 4) },
  { level: 5, rating: 1730, rank: botRank("jade", 2) },
];

function botRank(tier: string, division: number | null): Rank {
  // `name` / `label` ne servent pas à l'affichage : voir `rankLabel()` (lib/i18n/helpers).
  return { tier, name: tier, division, label: tier, lp: 0, placement: null, next: null };
}

export function squareName(sq: number): string {
  return `${LETTERS[sq % SIZE]}${Math.floor(sq / SIZE) + 1}`;
}

export function formatClock(ms: number): string {
  const total = Math.max(0, ms);
  if (total < 20_000) {
    const s = Math.floor(total / 1000);
    const t = Math.floor((total % 1000) / 100);
    return `0:${String(s).padStart(2, "0")}.${t}`;
  }
  const s = Math.ceil(total / 1000);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}
