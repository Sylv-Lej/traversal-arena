import * as THREE from "three";
import { ConvexGeometry, RoundedBoxGeometry, toCreasedNormals } from "three-stdlib";
import type { Kind } from "@/lib/types";

// --- Repère ---------------------------------------------------------------------------
// Case (x, y) -> monde : x vers la droite, rangée 0 (départ rouge) côté +Z.
export const STEP_H = 0.42; // hauteur d'un niveau
export const BASE_H = 0.28; // épaisseur d'une colonne de hauteur 0
// Dessous des colonnes : une case de hauteur 0 dépasse du socle de BASE_H - FLOOR (0,21).
export const FLOOR = 0.07;

export function topY(h: number): number {
  return BASE_H + h * STEP_H;
}

export function sqWorld(sq: number, heights: number[]): THREE.Vector3 {
  const x = sq % 10;
  const y = Math.floor(sq / 10);
  return new THREE.Vector3(x - 4.5, topY(heights[sq] ?? 0), 4.5 - y);
}

// --- Palette ----------------------------------------------------------------------------
const PALETTES: Record<string, string[]> = {
  mountains: ["#3f6b3a", "#4f7d3f", "#6b8f4a", "#8a8f7a", "#a3a39b", "#d9dde3", "#f5f7fa"],
  valleys: ["#2d6e7e", "#3f7f5c", "#5b9150", "#7da35a", "#9b9a6e", "#b8b3a0", "#d8d6cf"],
  highlands: ["#4a6b3a", "#5f7d42", "#727a48", "#86804f", "#8a7388", "#a59d94", "#d6d3cf"],
  woodlands: ["#2f5d2e", "#3d7038", "#4f8443", "#66974e", "#7fa85c", "#98b86b", "#b3c97e"],
  desert: ["#d9bc84", "#d4b07a", "#c99559", "#b87a45", "#a0643a", "#8a5333", "#e3d2b0"],
};

export function topColor(mode: string, h: number): THREE.Color {
  const pal = PALETTES[mode] ?? PALETTES.mountains;
  return new THREE.Color(pal[Math.max(0, Math.min(pal.length - 1, h))]);
}

const ROCK_DARK = new THREE.Color("#2a2420");
const ROCK_MID = new THREE.Color("#5a4c40");

/** Colonne arrondie dont le dessus est à la hauteur h, avec strates colorées sur les flancs. */
export function columnGeometry(mode: string, h: number, colorLevel = h): THREE.BufferGeometry {
  const top = topY(h);
  const height = top - FLOOR;
  // Arêtes arrondies : le biseau accroche la lumière et dessine chaque case.
  const geo = new RoundedBoxGeometry(0.94, height, 0.94, 3, 0.07);
  geo.translate(0, FLOOR + height / 2, 0);
  const pos = geo.getAttribute("position");
  const normal = geo.getAttribute("normal");
  const colors = new Float32Array(pos.count * 3);
  const surface = topColor(mode, colorLevel);
  const c = new THREE.Color();
  for (let i = 0; i < pos.count; i++) {
    const y = pos.getY(i);
    const ny = normal.getY(i);
    if (ny > 0.55 && y > top - 0.09) {
      c.copy(surface);
    } else {
      // Flancs : dégradé roche sombre -> teinte du sol, strates alternées par niveau.
      const t = (y - FLOOR) / Math.max(0.001, height);
      c.copy(ROCK_DARK).lerp(ROCK_MID, t).lerp(surface, Math.pow(t, 3) * 0.55);
      const band = Math.floor((y - FLOOR) / STEP_H);
      c.multiplyScalar(band % 2 === 0 ? 1.0 : 0.86);
    }
    colors[i * 3] = c.r;
    colors[i * 3 + 1] = c.g;
    colors[i * 3 + 2] = c.b;
  }
  geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  return geo;
}

// --- Pièces -----------------------------------------------------------------------------
// Coins de la base = Mouvement, pointes au sommet = Force : la forme dit les règles.

function ring(n: number, r: number, y: number, phase = 0): THREE.Vector3[] {
  return Array.from({ length: n }, (_, i) => {
    const a = phase + (i / n) * Math.PI * 2;
    return new THREE.Vector3(Math.cos(a) * r, y, Math.sin(a) * r);
  });
}

export interface PieceShape {
  base: THREE.Vector3[]; // coins de la base (= Mouvement)
  tips: THREE.Vector3[]; // pointes du sommet (= Force)
  height: number;
}

export const PIECE_SHAPES: Record<Kind, PieceShape> = {
  // Cône pentagonal : 5 coins, 1 pointe.
  explorer: { base: ring(5, 0.32, 0, -Math.PI / 2), tips: [new THREE.Vector3(0, 0.84, 0)], height: 0.84 },
  // Coin en losange : 4 coins, une arête faîtière à 2 pointes.
  vanguard: {
    base: ring(4, 0.35, 0),
    tips: [new THREE.Vector3(0.19, 0.72, 0), new THREE.Vector3(-0.19, 0.72, 0)],
    height: 0.72,
  },
  // Prisme triangulaire légèrement effilé : 3 coins, 3 pointes.
  sentinel: { base: ring(3, 0.36, 0, Math.PI / 2), tips: ring(3, 0.25, 0.64, Math.PI / 2), height: 0.64 },
};

export const PIECE_HEIGHT: Record<Kind, number> = {
  explorer: PIECE_SHAPES.explorer.height,
  vanguard: PIECE_SHAPES.vanguard.height,
  sentinel: PIECE_SHAPES.sentinel.height,
};

/**
 * Enveloppe convexe « arrondie » (somme de Minkowski avec une petite sphère) : arêtes et
 * sommets légèrement adoucis, faces planes conservées grâce aux normales « pliées »
 * (lissées seulement sur les arrondis).
 */
function roundedHull(points: THREE.Vector3[], radius: number): THREE.BufferGeometry {
  const ball = new THREE.IcosahedronGeometry(radius, 2).getAttribute("position");
  const cloud: THREE.Vector3[] = [];
  const v = new THREE.Vector3();
  for (const p of points) {
    for (let i = 0; i < ball.count; i++) {
      v.fromBufferAttribute(ball, i);
      cloud.push(p.clone().add(v));
    }
  }
  const hull = new ConvexGeometry(cloud);
  return toCreasedNormals(hull, Math.PI / 5);
}

const BEVEL = 0.014;

/** Corps de la pièce : facettes nettes avec un micro-biseau (reflets sur les arêtes). */
export function pieceGeometry(kind: Kind, bevel = BEVEL): THREE.BufferGeometry {
  const shape = PIECE_SHAPES[kind];
  const g = roundedHull([...shape.base, ...shape.tips], bevel);
  g.translate(0, bevel, 0);
  return g;
}

/** Arêtes vives de la forme (liseré lumineux), légèrement agrandies pour ne pas clignoter. */
export function pieceEdges(kind: Kind): THREE.BufferGeometry {
  const shape = PIECE_SHAPES[kind];
  const hull = new ConvexGeometry([...shape.base, ...shape.tips]);
  const e = new THREE.EdgesGeometry(hull, 20);
  e.scale(1 + BEVEL * 2.2, 1 + BEVEL * 0.6, 1 + BEVEL * 2.2);
  e.translate(0, BEVEL * 0.6, 0);
  return e;
}

/** Socle tourné : disque chanfreiné, plus large en bas. */
export const PEDESTAL = (() => {
  const pts = [
    new THREE.Vector2(0, 0),
    new THREE.Vector2(0.41, 0),
    new THREE.Vector2(0.43, 0.015),
    new THREE.Vector2(0.43, 0.04),
    new THREE.Vector2(0.39, 0.075),
    new THREE.Vector2(0.37, 0.085),
    new THREE.Vector2(0, 0.085),
  ];
  const g = new THREE.LatheGeometry(pts, 64);
  g.computeVertexNormals();
  return g;
})();

export const TEAM = {
  1: { main: "#e5484d", dark: "#7a1e22", glow: "#ff8a8d" },
  2: { main: "#3e7bfa", dark: "#1a3878", glow: "#8db4ff" },
} as const;
