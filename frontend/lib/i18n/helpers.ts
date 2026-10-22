// Petits libellés calculés (rangs, bots, cadences) : partagés serveur / client.
import type { Dict } from "./dict";
import type { PlayerCard, Rank } from "../types";

const ROMAN = ["", "I", "II", "III", "IV"];

/** « Or II », « Maître », « Placement 3/5 »… dans la langue du dictionnaire. */
export function rankLabel(rank: Rank | null | undefined, t: Dict): string {
  if (!rank) return t.common.unranked;
  if (rank.placement) return t.common.placement(rank.placement.played, rank.placement.total);
  return tierLabel(rank.tier, rank.division, t);
}

export function tierLabel(tier: string | null | undefined, division: number | null | undefined, t: Dict): string {
  const name = (tier && t.common.tiers[tier]) || t.common.unranked;
  return division ? `${name} ${ROMAN[division]}` : name;
}

/** Libellé du prochain palier (le serveur donne son palier et sa division). */
export function nextLabel(rank: Rank, t: Dict): string | null {
  return rank.next ? tierLabel(rank.next.tier, rank.next.division, t) : null;
}

/** Nom affiché d'un joueur : les bots portent un nom traduit (« Galet » / « Pebble »). */
export function playerName(p: Pick<PlayerCard, "id" | "name" | "isBot"> | null | undefined, t: Dict): string {
  if (!p) return "?";
  const m = p.isBot ? /^bot(\d)$/.exec(p.id) : null;
  return m ? (t.common.bots[Number(m[1])]?.name ?? p.name) : p.name;
}

/** Bot par id (`bot3`) quand on n'a que l'id. */
export function botNameById(id: string | null | undefined, t: Dict): string | null {
  const m = id ? /^bot(\d)$/.exec(id) : null;
  return m ? (t.common.bots[Number(m[1])]?.name ?? null) : null;
}

/** Remplace `{clé}` par sa valeur. */
export function fmt(s: string, vars: Record<string, string | number>): string {
  return s.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? `{${k}}`));
}
