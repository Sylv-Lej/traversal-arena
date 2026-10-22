"use client";

import { useFullSite } from "./Shell";
import Link from "next/link";
import { useEffect, useId, useState } from "react";
import type { Rank } from "@/lib/types";
import { useT } from "@/lib/i18n/client";
import { nextLabel, rankLabel } from "@/lib/i18n/helpers";

import { TIER_ORDER, type TierKey } from "@/lib/ranks";

export { TIER_ORDER, type TierKey };

const PALETTE: Record<TierKey | "placement", { base: string; dark: string; light: string; glow?: string }> = {
  placement: { base: "#5a5753", dark: "#2c2a28", light: "#9a9894" },
  slate: { base: "#5f6873", dark: "#2f343b", light: "#a3adb8" },
  bronze: { base: "#b8743f", dark: "#5e3216", light: "#efb27a" },
  silver: { base: "#aab5c3", dark: "#566273", light: "#f2f6fa" },
  gold: { base: "#e3b23c", dark: "#82560f", light: "#fff1b8", glow: "#e3b23c" },
  jade: { base: "#2fb38a", dark: "#0b5040", light: "#b3f7de", glow: "#2fb38a" },
  sapphire: { base: "#3f7ef7", dark: "#132c73", light: "#b5d0ff", glow: "#3f7ef7" },
  diamond: { base: "#59d0f0", dark: "#18577f", light: "#ecfcff", glow: "#7fe3ff" },
  master: { base: "#a660f2", dark: "#43197a", light: "#ecd8ff", glow: "#b77bff" },
  legend: { base: "#ff5d3a", dark: "#6e1010", light: "#ffe28c", glow: "#ffb347" },
};
const GOLD = "#e8c25a";


export function tierIndex(tier: string | null | undefined): number {
  return tier ? TIER_ORDER.indexOf(tier as TierKey) : -1;
}

/** Valeur ordonnée d'un rang (pour savoir s'il y a promotion ou relégation). */
export function rankValue(r: Rank | null | undefined): number {
  if (!r || !r.tier) return -1;
  return tierIndex(r.tier) * 10 + (r.division ? 4 - r.division : 4);
}

// Ciel de chaque scène (haut → bas) : de la vallée grise à l'aube au-dessus des nuages.
const SKY: Record<TierKey | "placement", [string, string]> = {
  placement: ["#4a4744", "#2c2a28"],
  slate: ["#8a94a1", "#4a515b"],
  bronze: ["#f6bd86", "#b0602c"],
  silver: ["#d5dde8", "#8392a6"],
  gold: ["#ffe08a", "#ee9a3a"],
  jade: ["#b7f3df", "#4cb898"],
  sapphire: ["#8db9ff", "#2448a8"],
  diamond: ["#f0fdff", "#8edcf2"],
  master: ["#1f1040", "#8a4fd6"],
  legend: ["#170d33", "#ff8a45"],
};

// Blason commun (tous les paliers) et sa découpe pour la scène.
const SHIELD = "M60 14 L94 28 L94 66 Q94 92 60 108 Q26 92 26 66 L26 28 Z";
const INNER = "M60 22 L87 33 L87 65 Q87 86 60 99 Q33 86 33 65 L33 33 Z";

function Pine({ x, y, s = 1, fill }: { x: number; y: number; s?: number; fill: string }) {
  return (
    <path
      d={`M${x} ${y - 14 * s} L${x + 5 * s} ${y - 6 * s} L${x + 3 * s} ${y - 6 * s} L${x + 7 * s} ${y} L${x - 7 * s} ${y} L${x - 3 * s} ${y - 6 * s} L${x - 5 * s} ${y - 6 * s} Z`}
      fill={fill}
    />
  );
}

function Sparkle({ x, y, r = 4 }: { x: number; y: number; r?: number }) {
  return (
    <path
      d={`M${x} ${y - r} L${x + r * 0.25} ${y - r * 0.25} L${x + r} ${y} L${x + r * 0.25} ${y + r * 0.25} L${x} ${y + r} L${x - r * 0.25} ${y + r * 0.25} L${x - r} ${y} L${x - r * 0.25} ${y - r * 0.25} Z`}
      fill="#fff"
    />
  );
}

const STARS = [
  [40, 30, 0.9], [52, 24, 0.7], [78, 28, 1], [86, 40, 0.7], [70, 22, 0.6], [36, 44, 0.6], [62, 34, 0.5],
] as const;

/** La scène de montagne propre à chaque palier : on monte de la vallée vers le sommet. */
function Scene({ k }: { k: TierKey | "placement" }) {
  switch (k) {
    case "slate": // La vallée : les sommets sont encore loin ; un torrent, des éboulis.
      return (
        <>
          <path d="M26 70 L40 50 L48 58 L60 40 L72 56 L80 48 L94 70 Z" fill="#a7b0bb" opacity="0.75" />
          <path d="M20 76 Q40 62 62 72 Q82 60 100 68 L100 120 L20 120 Z" fill="#646d78" />
          <path d="M20 86 Q40 76 56 82 Q78 72 100 84 L100 120 L20 120 Z" fill="#3c424a" />
          <path d="M60 80 Q52 88 62 94 Q72 100 58 108" fill="none" stroke="#b9c8d6" strokeWidth="3" strokeLinecap="round" />
          <ellipse cx="42" cy="93" rx="6" ry="3.2" fill="#8f99a5" />
          <ellipse cx="78" cy="94" rx="7" ry="3.6" fill="#7b8592" />
          <ellipse cx="48" cy="100" rx="4" ry="2.4" fill="#a3adb8" />
        </>
      );
    case "bronze": // Les contreforts : un sentier qui serpente.
      return (
        <>
          <path d="M24 86 L46 58 L58 70 L74 50 L96 82 Z" fill="#8a4f26" />
          <path d="M74 50 L68 58 L73 56 L76 60 L80 55 Z" fill="#f2c79a" />
          <path d="M20 92 Q52 76 100 88 L100 120 L20 120 Z" fill="#5a2f14" />
          <path d="M50 106 Q60 98 53 92 Q46 86 58 82 Q68 78 62 72" fill="none" stroke="#efb27a" strokeWidth="1.8" strokeDasharray="2.5 2.5" strokeLinecap="round" />
          <Pine x={79} y={92} s={0.9} fill="#3d4f2a" />
          <Pine x={40} y={95} s={0.7} fill="#3d4f2a" />
        </>
      );
    case "silver": // La forêt : la montagne nue derrière les sapins.
      return (
        <>
          <circle cx="42" cy="34" r="5" fill="#f4f7fb" />
          <path d="M26 84 L48 46 L58 60 L72 38 L94 84 Z" fill="#7d8899" />
          <path d="M72 38 L94 84 L80 84 Z" fill="#5f6a7b" />
          {[30, 38, 46, 54, 62, 70, 78, 86].map((x, i) => (
            <Pine key={x} x={x} y={i % 2 ? 94 : 92} s={i % 3 === 0 ? 1 : 0.8} fill={i % 2 ? "#2f4b3c" : "#25402f"} />
          ))}
          <rect x="20" y="92" width="80" height="30" fill="#1f3427" />
        </>
      );
    case "gold": // L'alpage : le soleil se lève derrière le sommet.
      return (
        <>
          <circle cx="60" cy="60" r="17" fill="#fff4c4" opacity="0.95" />
          <circle cx="60" cy="60" r="24" fill="#fff4c4" opacity="0.25" />
          <path d="M24 88 L46 56 L58 68 L72 46 L96 88 Z" fill="#7d4f12" />
          <path d="M72 46 L66 56 L71 53 L74 58 L79 52 Z" fill="#fff4c4" />
          <path d="M20 90 Q60 80 100 92 L100 120 L20 120 Z" fill="#8aa83a" />
          <path d="M20 98 Q60 90 100 100 L100 120 L20 120 Z" fill="#6c8a2a" />
        </>
      );
    case "jade": // Le lac d'altitude : le sommet se reflète.
      return (
        <>
          <path d="M28 76 L48 46 L58 58 L70 36 L92 76 Z" fill="#14594a" />
          <path d="M70 36 L64 46 L69 44 L72 48 L76 43 Z" fill="#e9fff6" />
          <path d="M48 46 L44 53 L48 51 L51 54 Z" fill="#e9fff6" />
          <rect x="20" y="76" width="80" height="44" fill="#2fb38a" />
          <path d="M28 76 L48 106 L58 94 L70 116 L92 76 Z" fill="#14594a" opacity="0.35" />
          <path d="M34 84 H56 M62 90 H82 M42 96 H62" stroke="#c8fbe9" strokeWidth="1" opacity="0.7" />
          <Pine x={30} y={78} s={0.8} fill="#0c3d31" />
          <Pine x={90} y={78} s={0.8} fill="#0c3d31" />
        </>
      );
    case "sapphire": // Le glacier : glace bleue et crevasses.
      return (
        <>
          <path d="M24 92 L44 52 L56 64 L68 34 L96 92 Z" fill="#d6e6ff" />
          <path d="M68 34 L96 92 L74 92 L66 60 Z" fill="#7fa8ef" />
          <path d="M44 52 L56 64 L50 72 Z" fill="#9fbdf3" />
          <path d="M52 78 L58 72 L62 80 M66 86 L72 78 L76 88 M40 86 L46 80" fill="none" stroke="#2448a8" strokeWidth="1.6" strokeLinejoin="round" />
          <path d="M20 96 Q60 88 100 98 L100 120 L20 120 Z" fill="#a9c8ff" />
        </>
      );
    case "diamond": // Le sommet : drapeau planté au-dessus de la mer de nuages, en plein jour.
      return (
        <>
          <path d="M32 94 L52 52 L60 60 L66 32 L88 94 Z" fill="#5aa9cf" />
          <path d="M66 32 L88 94 L72 94 L64 58 Z" fill="#2f7fa8" />
          <path d="M66 32 L59 47 L65 44 L68 49 L73 43 Z" fill="#ffffff" />
          <path d="M52 52 L48 60 L52 58 L55 61 Z" fill="#ffffff" />
          <path d="M66 32 V18" stroke="#ffffff" strokeWidth="1.6" />
          <path d="M66 18 L77 21.5 L66 25 Z" fill="#ff5a4f" />
          <Sparkle x={42} y={34} r={3.4} />
          <path d="M18 86 Q30 78 42 84 Q54 76 66 84 Q80 76 102 84 L102 120 L18 120 Z" fill="#ffffff" />
          <path d="M18 95 Q36 87 54 94 Q74 87 102 95 L102 120 L18 120 Z" fill="#dff7ff" />
        </>
      );
    case "master": // Les neiges éternelles : arêtes vives sous un ciel étoilé.
      return (
        <>
          {STARS.map(([x, y, r]) => (
            <circle key={`${x}-${y}`} cx={x} cy={y} r={r} fill="#fff" />
          ))}
          <path d="M24 94 L38 60 L48 72 L62 30 L74 64 L84 50 L96 94 Z" fill="#efe2ff" />
          <path d="M62 30 L74 64 L64 94 L56 60 Z" fill="#b99be8" />
          <path d="M84 50 L96 94 L84 94 L80 66 Z" fill="#b99be8" />
          <path d="M38 60 L48 72 L40 80 Z" fill="#d8c6f5" />
          <Sparkle x={46} y={44} r={3.4} />
          <Sparkle x={82} y={40} r={2.8} />
          <path d="M20 96 Q60 90 100 98 L100 120 L20 120 Z" fill="#d9c8f5" />
        </>
      );
    case "legend": // Au-dessus du monde : le soleil se lève derrière le plus haut sommet.
      return (
        <>
          {STARS.map(([x, y, r]) => (
            <circle key={`${x}-${y}`} cx={x} cy={y - 4} r={r} fill="#fff" />
          ))}
          <circle cx="60" cy="82" r="22" fill="#ffd27a" opacity="0.9" />
          <path d="M30 94 L50 54 L58 62 L64 30 L90 94 Z" fill="#4a1410" />
          <path d="M64 30 L57 45 L63 42 L66 47 L71 41 Z" fill="#fff1d0" />
          <path d="M64 30 V16" stroke="#fff1d0" strokeWidth="1.6" />
          <path d="M64 16 L77 20 L64 24 Z" fill="#ffe28c" />
          <path d="M18 90 Q30 82 42 88 Q54 80 66 88 Q80 80 102 88 L102 120 L18 120 Z" fill="#ffb27a" />
          <path d="M18 98 Q36 90 54 97 Q74 90 102 98 L102 120 L18 120 Z" fill="#ff8a5c" />
        </>
      );
    default: // Placement : la montagne dans le brouillard.
      return (
        <>
          <path d="M26 88 L48 54 L58 66 L72 46 L94 88 Z" fill="#3e3b38" />
          <rect x="20" y="70" width="80" height="50" fill="#5a5753" opacity="0.55" />
        </>
      );
  }
}

/** Piolet (Saphir et au-delà), croisé derrière le blason. */
function IceAxe({ flip, color }: { flip: boolean; color: string }) {
  return (
    <g transform={`rotate(${flip ? 40 : -40} 60 60)`}>
      <rect x="58.2" y="8" width="3.6" height="100" rx="1.6" fill="#6b4a2b" stroke="#2c1d10" strokeWidth="0.8" />
      <path d="M44 12 Q60 4 76 12 L78 16 Q66 11 60 12 Q54 11 42 16 Z" fill={color} stroke="#2c2a28" strokeWidth="0.8" />
      <path d="M58 104 L60 114 L62 104 Z" fill={color} />
    </g>
  );
}

/** Branche de sapin (Or et Jade), de part et d'autre du blason. */
function FirSprig({ color }: { color: string }) {
  return (
    <g>
      <path d="M30 100 Q14 76 22 40" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" />
      {[46, 54, 62, 70, 78, 86, 94].map((y, i) => {
        const x = 22 + (y - 40) * 0.12 - Math.abs(y - 72) * 0.06;
        return (
          <g key={y}>
            <path d={`M${x} ${y} l-7 -4`} stroke={color} strokeWidth="2" strokeLinecap="round" />
            <path d={`M${x} ${y} l6 -5`} stroke={color} strokeWidth="2" strokeLinecap="round" opacity={i % 2 ? 0.8 : 1} />
          </g>
        );
      })}
    </g>
  );
}

/**
 * Emblème d'un palier : un blason qui encadre une scène de montagne, de la vallée
 * (Ardoise) jusqu'au-dessus des nuages (Légende). Les ornements suivent l'ascension :
 * corde, branches de sapin, piolets croisés, couronne de sommets, rayons de l'aube.
 */
export function RankEmblem({ rank, size = 64, animated = true }: { rank: Rank | null; size?: number; animated?: boolean }) {
  const tr = useT();
  const uid = useId().replace(/:/g, "");
  const key = (rank?.tier ?? "placement") as TierKey | "placement";
  const p = PALETTE[key];
  const t = tierIndex(rank?.tier);
  const roman = rank?.division ? ["", "I", "II", "III", "IV"][rank.division] : null;
  const g = (n: string) => `${n}${uid}`;
  const [skyTop, skyBottom] = SKY[key];

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 120 120"
      className={`emblem tier-${key} ${animated && t >= 7 ? "emblemAnim" : ""}`}
      role="img"
      aria-label={rankLabel(rank, tr)}
    >
      <defs>
        <linearGradient id={g("sky")} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={skyTop} />
          <stop offset="1" stopColor={skyBottom} />
        </linearGradient>
        <linearGradient id={g("rim")} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={p.light} />
          <stop offset="0.5" stopColor={p.base} />
          <stop offset="1" stopColor={p.dark} />
        </linearGradient>
        <radialGradient id={g("aura")}>
          <stop offset="0" stopColor={p.glow ?? p.base} stopOpacity="0.55" />
          <stop offset="1" stopColor={p.glow ?? p.base} stopOpacity="0" />
        </radialGradient>
        <clipPath id={g("clip")}>
          <path d={SHIELD} />
        </clipPath>
      </defs>

      {t >= 3 && <circle cx="60" cy="60" r={t >= 7 ? 58 : 50} fill={`url(#${g("aura")})`} />}

      {/* Rayons de l'aube (Légende) */}
      {t >= 8 &&
        Array.from({ length: 12 }, (_, i) => (
          <path key={i} d="M60 60 L57 4 L63 4 Z" fill={GOLD} opacity={0.5} transform={`rotate(${i * 30} 60 60)`} />
        ))}

      {/* Piolets croisés (Saphir et au-delà) */}
      {t >= 5 && (
        <>
          <IceAxe flip={false} color={t >= 7 ? GOLD : "#d7dde5"} />
          <IceAxe flip color={t >= 7 ? GOLD : "#d7dde5"} />
        </>
      )}

      {/* Branches de sapin (Or, Jade) */}
      {(t === 3 || t === 4) &&
        [-1, 1].map((s) => (
          <g key={s} transform={`translate(60 0) scale(${s} 1) translate(-60 0)`}>
            <FirSprig color={t === 3 ? GOLD : "#7fd9b4"} />
          </g>
        ))}

      {/* Couronne de sommets enneigés (Maître, Légende) */}
      {t >= 7 && (
        <g>
          <path d="M38 24 L45 8 L52 18 L60 2 L68 18 L75 8 L82 24 Z" fill={GOLD} stroke="#8a6512" strokeWidth="1.2" strokeLinejoin="round" />
          <path d="M45 8 L42.5 14 L47.5 14 Z M60 2 L57 9 L63 9 Z M75 8 L72.5 14 L77.5 14 Z" fill="#fff" />
        </g>
      )}

      {/* Scène de montagne, découpée dans le blason */}
      <g clipPath={`url(#${g("clip")})`}>
        <rect x="0" y="0" width="120" height="120" fill={`url(#${g("sky")})`} />
        <Scene k={key} />
      </g>

      {/* Cadre du blason ; corde à partir d'Argent */}
      <path d={SHIELD} fill="none" stroke={t >= 1 ? `url(#${g("rim")})` : p.light} strokeWidth={t >= 1 ? 4.5 : 3} strokeLinejoin="round" />
      {t >= 2 && (
        <path d={INNER} fill="none" stroke={p.light} strokeOpacity="0.7" strokeWidth="1.6" strokeDasharray="3 2" strokeLinecap="round" />
      )}

      {!rank?.tier && (
        <text x="60" y="72" textAnchor="middle" fontSize="38" fontWeight="900" fill="#d6d3ce">
          ?
        </text>
      )}

      {/* Division : panneau de sentier */}
      {roman && (
        <g>
          <path d="M42 104 L78 104 L75 117 L45 117 Z" fill={p.dark} stroke={p.light} strokeWidth="1.5" />
          <text x="60" y="114.5" textAnchor="middle" fontSize="11" fontWeight="900" fill="#fff" letterSpacing="1">
            {roman}
          </text>
        </g>
      )}
    </svg>
  );
}

/** Emblème + libellé + PL, en ligne (barres de joueurs, classement). */
export function RankChip({ rank, size = 22 }: { rank: Rank | null | undefined; size?: number }) {
  const t = useT();
  if (!rank) return null;
  const label = rankLabel(rank, t);
  return (
    <span
      className="rankChip"
      title={rank.placement ? t.ranks.chip.placementTitle(rank.placement.played, rank.placement.total) : `${label} · ${rank.lp} ${t.common.lpShort}`}
    >
      <RankEmblem rank={rank} size={size} animated={false} />
      <span className="rankChipLabel">{rank.placement ? `${rank.placement.played}/${rank.placement.total}` : label}</span>
    </span>
  );
}

/** Barre de PL dans la division (animée d'une valeur à l'autre). */
export function LpBar({ from, to, label }: { from?: number; to: number; label?: string }) {
  const tr = useT();
  const [w, setW] = useState(from ?? to);
  useEffect(() => {
    const t = setTimeout(() => setW(to), 350);
    return () => clearTimeout(t);
  }, [to]);
  return (
    <div className="lpBar" aria-label={tr.ranks.lpAria(to)}>
      <div className="lpFill" style={{ width: `${Math.max(2, w)}%` }} />
      <span>{label ?? `${to} ${tr.common.lpShort}`}</span>
    </div>
  );
}

/** Carte de rang (profil) : grand emblème, rang, PL, prochain palier. */
export function RankCard({ rank, title }: { rank: Rank | null | undefined; title: string }) {
  const t = useT();
  const fullSite = useFullSite();
  const next = rank ? nextLabel(rank, t) : null;
  return (
    <div className={`rankCard tier-${rank?.tier ?? "placement"}`}>
      <span className="rankCardTitle">{title}</span>
      <RankEmblem rank={rank ?? null} size={84} />
      <b className="rankCardLabel">{rankLabel(rank, t)}</b>
      {rank?.tier && t.common.zones[rank.tier] && (
        <span className="rankZone">
          {t.common.zones[rank.tier]}
        </span>
      )}
      {rank?.placement ? (
        <span className="muted small">
          {t.ranks.card.placementLeft(rank.placement.total - rank.placement.played)}
        </span>
      ) : rank ? (
        <>
          {rank.division ? <LpBar to={rank.lp} /> : <span className="small">{rank.lp} {t.common.lpShort}</span>}
          {next && <span className="muted small">{t.ranks.card.next} {next}</span>}
        </>
      ) : (
        <span className="muted small">
          {fullSite ? <Link href="/play">{t.ranks.card.playRanked}</Link> : t.ranks.card.playRanked}
        </span>
      )}
    </div>
  );
}
