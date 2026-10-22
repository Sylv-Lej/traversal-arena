import type { Kind, Side } from "@/lib/types";

type P = { size?: number; className?: string };

export const Logo = ({ size = 28 }: P) => (
  <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
    <defs>
      <linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stopColor="#9be07a" />
        <stop offset="1" stopColor="#4c9a2a" />
      </linearGradient>
    </defs>
    <path d="M2 26 L11 10 L16 17 L21 7 L30 26 Z" fill="url(#lg)" />
    <path d="M21 7 L24.5 14 L21.5 12.5 L19 15 Z" fill="#fff" opacity=".85" />
    <rect x="2" y="26" width="28" height="3" rx="1.5" fill="#e5484d" />
  </svg>
);

const I = (d: string) =>
  function Icon({ size = 22, className }: P) {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d={d} />
      </svg>
    );
  };

export const IconPuzzle = I("M10 3h4v3a2 2 0 1 0 4 0V3h3v7h-3a2 2 0 1 0 0 4h3v7h-7v-3a2 2 0 1 0-4 0v3H3v-7h3a2 2 0 1 0 0-4H3V3h7z");
export const IconEye = I("M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z");
export const IconPlay = I("M4 20 L10 8 L13 13 L16 6 L20 20 Z");
export const IconBot = I("M8 8h8a3 3 0 0 1 3 3v5a3 3 0 0 1-3 3H8a3 3 0 0 1-3-3v-5a3 3 0 0 1 3-3zM12 4v4M9 13h.01M15 13h.01M2 13v2M22 13v2");
export const IconTrophy = I("M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0V4zM7 6H4a3 3 0 0 0 3 4M17 6h3a3 3 0 0 1-3 4");
export const IconBook = I("M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2V5zM4 19a2 2 0 0 1 2-2h13");
export const IconHome = I("M3 11l9-8 9 8v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1v-9z");
export const IconUser = I("M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0");
export const IconFlag = I("M5 21V4M5 4h11l-2 4 2 4H5");
export const IconHandshake = I("M3 12l4-4 4 3 3-2 7 6M7 16l2 2M10 14l3 3M13 12l3 3");
export const IconFlip = I("M7 4v13M7 17l-3-3M7 17l3-3M17 20V7M17 7l-3 3M17 7l3 3");
export const IconTop = I("M3 7l9-4 9 4-9 4-9-4zM3 12l9 4 9-4M3 17l9 4 9-4");
export const IconCenter = I("M12 3v3M12 18v3M3 12h3M18 12h3M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z");
export const IconGear = I("M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z");
export const IconLink = I("M10 14a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1M14 10a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1");
export const IconPrev = I("M15 18l-6-6 6-6");
export const IconNext = I("M9 18l6-6-6-6");
export const IconFirst = I("M11 18l-6-6 6-6M18 18l-6-6 6-6");
export const IconLast = I("M13 18l6-6-6-6M6 18l6-6-6-6");
export const IconClose = I("M6 6l12 12M18 6L6 18");
// Arène des bots : un bloc de code entre chevrons.
export const IconArena = I("M8 7l-5 5 5 5M16 7l5 5-5 5M14 4l-4 16");
export const IconPeople = I("M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM2 21a7 7 0 0 1 14 0M17 3a4 4 0 0 1 0 8M22 21a7 7 0 0 0-4-6.3");

const TEAM_FILL: Record<Side, [string, string]> = { 1: ["#e5484d", "#7a1e22"], 2: ["#3e7bfa", "#1a3878"] };

/** Silhouette 2D d'une pièce (coins de la base = Mouvement, pointes = Force). */
export function PieceIcon({ kind, side = 1, size = 22 }: { kind: Kind; side?: Side; size?: number }) {
  const [fill, dark] = TEAM_FILL[side];
  const shape =
    kind === "explorer"
      ? <path d="M12 2 L21 19 L16 22 L8 22 L3 19 Z" />
      : kind === "vanguard"
        ? <path d="M7 4 L17 4 L22 18 L12 22 L2 18 Z" />
        : <path d="M5 5 L12 2 L19 5 L21 21 L3 21 Z" />;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-label={kind}>
      <g fill={fill} stroke={dark} strokeWidth="1.5" strokeLinejoin="round">
        {shape}
      </g>
    </svg>
  );
}
