"use client";

import { useEffect, useRef } from "react";
import type { MoveClass, MoveRecord } from "@/lib/types";
import { useT } from "@/lib/i18n/client";
import { ClassBadge } from "./AnalysisPanel";

/** Liste des coups en 2 colonnes (rouge | bleu), comme sur chess.com. Cliquable. */
export function MoveList({
  moves,
  viewPly,
  onSelect,
  compact,
  marks,
}: {
  moves: MoveRecord[];
  viewPly: number;
  onSelect: (ply: number) => void;
  compact?: boolean;
  /** Appréciations du bilan de partie, par numéro de coup. */
  marks?: Record<number, MoveClass>;
}) {
  const t = useT();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current?.querySelector(".current");
    el?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [viewPly, moves.length]);

  const rows: [MoveRecord | null, MoveRecord | null][] = [];
  for (const m of moves) {
    if (m.side === 1 || rows.length === 0) rows.push([m.side === 1 ? m : null, m.side === 2 ? m : null]);
    else if (rows[rows.length - 1][1] === null) rows[rows.length - 1][1] = m;
    else rows.push([null, m]);
  }

  const cell = (m: MoveRecord | null) =>
    m ? (
      <button className={`mv ${m.kind} ${m.ply === viewPly ? "current" : ""}`} onClick={() => onSelect(m.ply)}>
        {m.notation}
        {marks?.[m.ply] && marks[m.ply] !== "good" && marks[m.ply] !== "forced" && <ClassBadge c={marks[m.ply]} />}
      </button>
    ) : (
      <span className="mv empty">…</span>
    );

  if (compact) {
    return (
      <div className="moveStrip" ref={ref}>
        {moves.length === 0 && <span className="muted">{t.game.noMovesShort}</span>}
        {rows.map(([a, b], i) => (
          <span key={i} className="pair">
            <span className="num">{i + 1}.</span>
            {cell(a)}
            {b && cell(b)}
          </span>
        ))}
      </div>
    );
  }

  return (
    <div className="moveList" ref={ref}>
      {moves.length === 0 && <p className="muted center">{t.game.noMoves}</p>}
      {rows.map(([a, b], i) => (
        <div key={i} className={`row ${i % 2 ? "odd" : ""}`}>
          <span className="num">{i + 1}.</span>
          {cell(a)}
          {cell(b)}
        </div>
      ))}
    </div>
  );
}
