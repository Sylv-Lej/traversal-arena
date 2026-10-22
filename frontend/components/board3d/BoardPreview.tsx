"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { PieceT } from "@/lib/types";
import type { SkinId } from "./skins";

const Board3D = dynamic(() => import("./Board3D"), { ssr: false, loading: () => <div className="board3d loadingBoard" /> });

// Mise en place (R3.2) : de la plus rapide au centre à la plus lente sur les côtés.
const SETUP: [number, PieceT["kind"]][] = [
  [2, "sentinel"],
  [3, "vanguard"],
  [4, "explorer"],
  [5, "explorer"],
  [6, "vanguard"],
  [7, "sentinel"],
];

export const START_PIECES: PieceT[] = [
  ...SETUP.map(([x, kind], i) => ({ id: `r${i}`, owner: 1 as const, kind, sq: x })),
  ...SETUP.map(([x, kind], i) => ({ id: `b${i}`, owner: 2 as const, kind, sq: 90 + 9 - x })),
];

/** Plateau décoratif (accueil, choix du terrain) : position de départ, rotation lente. */
export function BoardPreview({
  mode = "mountains",
  seed,
  className,
  autoRotate = true,
  skins,
}: {
  mode?: string;
  seed?: number;
  className?: string;
  autoRotate?: boolean;
  skins?: Partial<Record<1 | 2, SkinId>>;
}) {
  const [terrain, setTerrain] = useState<{ mode: string; heights: number[] } | null>(null);
  useEffect(() => {
    let alive = true;
    api<{ mode: string; heights: number[] }>(`terrain?mode=${mode}${seed !== undefined ? `&seed=${seed}` : ""}`)
      .then((t) => alive && setTerrain(t))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [mode, seed]);
  if (!terrain) return <div className={`${className ?? "board3d"} loadingBoard`} />;
  return (
    <Board3D
      key={`${terrain.mode}-${terrain.heights.join("")}`}
      className={className}
      heights={terrain.heights}
      terrainMode={terrain.mode}
      pieces={START_PIECES}
      orientation={1}
      autoRotate={autoRotate}
      skins={skins}
      intro
    />
  );
}
