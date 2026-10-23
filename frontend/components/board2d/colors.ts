// Couleurs partagées par les plateaux 2D et 3D (sans dépendance à three.js).

export const TEAM = {
  1: { main: "#e5484d", dark: "#7a1e22", glow: "#ff8a8d" },
  2: { main: "#3e7bfa", dark: "#1a3878", glow: "#8db4ff" },
} as const;

/** Teintes hypsométriques (carte topographique), une par niveau 0..6 : en 2D la hauteur
 * se lit à la couleur, quel que soit le type de terrain. */
const HEIGHTS = ["#1f5f7a", "#3f8f4a", "#c2c64a", "#e39a3c", "#b9563a", "#7d4e6b", "#ecebe6"];

export function heightColor(h: number): string {
  return HEIGHTS[Math.max(0, Math.min(HEIGHTS.length - 1, h))];
}

/** Texte lisible sur la teinte du niveau h. */
export function heightInk(h: number): string {
  const hex = heightColor(h);
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.45 ? "#1d1b18" : "#ffffff";
}
