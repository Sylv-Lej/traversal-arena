// Annotations du plateau, comme sur chess.com : clic droit glissé d'une case à une autre =
// flèche, clic droit sur une case = cercle, clic gauche = tout effacer. Maj / Ctrl / Alt
// changent la couleur. Purement visuel : rien n'est envoyé au serveur.

export type AnnColor = "orange" | "green" | "red" | "blue";

export const ANN_COLORS: Record<AnnColor, string> = {
  orange: "#ffaa00",
  green: "#9fcf3f",
  red: "#ff5a4f",
  blue: "#48c1f9",
};

export interface Annotations {
  arrows: { from: number; to: number; color: AnnColor }[];
  circles: { sq: number; color: AnnColor }[];
}

export const NO_ANNOTATIONS: Annotations = { arrows: [], circles: [] };

export function annColor(e: { shiftKey: boolean; ctrlKey: boolean; metaKey: boolean; altKey: boolean }): AnnColor {
  if (e.shiftKey) return "green";
  if (e.ctrlKey || e.metaKey) return "red";
  if (e.altKey) return "blue";
  return "orange";
}

/** Ajoute la flèche (ou le cercle si from === to) ; la redessiner à l'identique l'efface,
 * dans une autre couleur la recolore. */
export function toggleAnnotation(a: Annotations, from: number, to: number, color: AnnColor): Annotations {
  if (from === to) {
    const hit = a.circles.find((c) => c.sq === from);
    const circles = a.circles.filter((c) => c.sq !== from);
    if (!hit || hit.color !== color) circles.push({ sq: from, color });
    return { ...a, circles };
  }
  const hit = a.arrows.find((x) => x.from === from && x.to === to);
  const arrows = a.arrows.filter((x) => !(x.from === from && x.to === to));
  if (!hit || hit.color !== color) arrows.push({ from, to, color });
  return { ...a, arrows };
}

export function hasAnnotations(a: Annotations | undefined): boolean {
  return !!a && (a.arrows.length > 0 || a.circles.length > 0);
}
