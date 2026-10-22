// Habillages des pièces des bots, aux couleurs de leur rang (emblème) :
// Galet = Ardoise, Sentier = Bronze, Crête = Or, Sommet = Jade, Mont Blanc = Maître (rangs
// de départ : les classements des bots bougent depuis, les habillages restent).
// La FORME ne change jamais (coins de la base = Mouvement, pointes = Force) ; seuls la
// matière, les arêtes et les pics changent. Le socle et son anneau gardent la couleur du
// camp : on sait toujours qui est qui.

export type SkinId = "team" | "bot1" | "bot2" | "bot3" | "bot4" | "bot5";

export interface Skin {
  name: string;
  color: string;
  roughness: number;
  metalness: number;
  clearcoat: number;
  emissive?: string;
  emissiveIntensity?: number;
  /** Variation d'émission (min, max) : la pièce « respire ». */
  pulse?: [number, number];
  edgeColor?: string; // liseré des arêtes
  edgeOpacity: number;
  edgeGlow?: boolean;
  bevel: number; // arrondi des arêtes (galet très arrondi, cristal très vif)
  /** Pics prolongeant chaque pointe du sommet (longueur). */
  tipSpikes?: number;
  /** Pics sortant des arêtes latérales : longueur, et nombre par arête. */
  sideSpikes?: number;
  sideCount?: number;
  aura?: string; // halo pulsant sous le socle
  float?: boolean; // la pièce lévite doucement
}

export const SKINS: Record<Exclude<SkinId, "team">, Skin> = {
  // Ardoise : pierre de schiste mate, arrondie comme un galet.
  bot1: {
    name: "Galet",
    color: "#6c7682",
    roughness: 0.88,
    metalness: 0,
    clearcoat: 0,
    edgeColor: "#a3adb8",
    edgeOpacity: 0.35,
    bevel: 0.055,
  },
  // Bronze : métal patiné.
  bot2: {
    name: "Sentier",
    color: "#b8743f",
    roughness: 0.42,
    metalness: 0.75,
    clearcoat: 0.3,
    edgeColor: "#efb27a",
    edgeOpacity: 0.6,
    bevel: 0.025,
  },
  // Or : métal poli, premières pointes.
  bot3: {
    name: "Crête",
    color: "#e8b93f",
    roughness: 0.3,
    metalness: 0.55,
    clearcoat: 0.8,
    // Un métal très poli reflète surtout le fond sombre : un peu d'éclat propre le garde doré.
    emissive: "#e3b23c",
    emissiveIntensity: 0.14,
    edgeColor: "#fff1b8",
    edgeOpacity: 0.8,
    bevel: 0.012,
    tipSpikes: 0.14,
  },
  // Jade : pierre verte polie et lumineuse, pics au sommet et sur les arêtes.
  bot4: {
    name: "Sommet",
    color: "#24a07b",
    roughness: 0.16,
    metalness: 0.15,
    clearcoat: 1,
    emissive: "#2fb38a",
    emissiveIntensity: 0.12,
    edgeColor: "#b3f7de",
    edgeOpacity: 0.95,
    edgeGlow: true,
    bevel: 0.008,
    tipSpikes: 0.2,
    sideSpikes: 0.13,
    sideCount: 1,
  },
  // Maître : améthyste sombre qui pulse, hérissée, auréolée, en lévitation.
  bot5: {
    name: "Mont Blanc",
    color: "#3a1670",
    roughness: 0.08,
    metalness: 0.35,
    clearcoat: 1,
    emissive: "#a660f2",
    emissiveIntensity: 0.25,
    pulse: [0.12, 0.55],
    edgeColor: "#ecd8ff",
    edgeOpacity: 1,
    edgeGlow: true,
    bevel: 0.006,
    tipSpikes: 0.28,
    sideSpikes: 0.17,
    sideCount: 2,
    aura: "#b77bff",
    float: true,
  },
};

export function botSkin(level: number | null | undefined): SkinId {
  return level && level >= 1 && level <= 5 ? (`bot${level}` as SkinId) : "team";
}
