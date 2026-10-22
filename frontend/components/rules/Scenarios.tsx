"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { CombatCard } from "@/components/game/CombatCard";
import { useT } from "@/lib/i18n/client";
import { LazyMount } from "./LazyMount";
import type { Kind, LegalMove, MoveRecord, PieceT, Position, Side } from "@/lib/types";

function LoadingBoard() {
  const t = useT();
  return <div className="board3d scenario3d loadingBoard">{t.common.actions.loading}</div>;
}

const Board3D = dynamic(() => import("@/components/board3d/Board3D"), {
  ssr: false,
  loading: () => <LoadingBoard />,
});
const PieceViewer = dynamic(() => import("./PieceViewer"), { ssr: false, loading: () => <div className="pieceViewer" /> });

/** Pièce en 3D pour les cartes de la page Règles (montée seulement quand visible). */
export function PieceShowcase({ kind }: { kind: Kind }) {
  return (
    <LazyMount minHeight={150}>
      <PieceViewer kind={kind} />
    </LazyMount>
  );
}

// --- Situations de jeu ---------------------------------------------------------------

const sq = (x: number, y: number) => y * 10 + x;

function terrain(base: number, bumps: [number, number, number][]): number[] {
  const h = Array(100).fill(base);
  for (const [x, y, v] of bumps) h[sq(x, y)] = v;
  return h;
}

const P = (id: string, owner: Side, kind: Kind, x: number, y: number): PieceT => ({ id, owner, kind, sq: sq(x, y) });

// Titre et texte de chaque situation : `t.rules.situations.list[id]`.
interface Situation {
  id: string;
  heights: number[];
  pieces: PieceT[];
  select: string;
  preview?: number;
  focus: { x: number; y: number; radius: number };
  mode: string;
}

const SITUATIONS: Situation[] = [
  {
    id: "relief",
    heights: terrain(1, [[4, 4, 3], [5, 4, 3], [3, 4, 2], [5, 3, 2], [4, 5, 3], [3, 5, 2], [5, 5, 2]]),
    pieces: [P("rs", 1, "sentinel", 4, 3), P("bs", 2, "sentinel", 6, 8)],
    select: "rs",
    focus: { x: 4, y: 4, radius: 3.6 },
    mode: "mountains",
  },
  {
    id: "explorer",
    heights: terrain(1, [
      [4, 3, 0], [4, 4, 2], [4, 2, 2], [3, 3, 2], [5, 3, 2],
      [3, 4, 4], [5, 4, 4], [3, 2, 4], [5, 2, 4], [4, 5, 4], [6, 3, 4], [2, 3, 4], [4, 1, 4],
    ]),
    pieces: [P("re", 1, "explorer", 4, 3), P("rv", 1, "vanguard", 3, 3), P("bs", 2, "sentinel", 7, 8)],
    select: "re",
    focus: { x: 4, y: 3.5, radius: 3.4 },
    mode: "mountains",
  },
  {
    id: "hill",
    heights: terrain(1, [[4, 3, 2], [3, 3, 2], [5, 3, 2]]),
    pieces: [P("rv", 1, "vanguard", 4, 3), P("bv", 2, "vanguard", 4, 4), P("be", 2, "explorer", 5, 4)],
    select: "rv",
    preview: sq(4, 4),
    focus: { x: 4.5, y: 3.8, radius: 3.8 },
    mode: "valleys",
  },
  {
    id: "assault",
    heights: terrain(1, []),
    pieces: [P("re", 1, "explorer", 4, 2), P("rv", 1, "vanguard", 5, 4), P("bs", 2, "sentinel", 4, 4)],
    select: "re",
    preview: sq(4, 4),
    focus: { x: 4.5, y: 3.4, radius: 3.8 },
    mode: "woodlands",
  },
  {
    id: "charge",
    heights: terrain(1, []),
    pieces: [P("rv", 1, "vanguard", 4, 1), P("bs", 2, "sentinel", 4, 5), P("bt", 2, "sentinel", 6, 2)],
    select: "rv",
    preview: sq(4, 5),
    focus: { x: 4.8, y: 3, radius: 3.6 },
    mode: "desert",
  },
  {
    id: "exit",
    heights: terrain(1, [[3, 8, 2], [5, 9, 2]]),
    pieces: [P("rs", 1, "sentinel", 4, 7), P("bv", 2, "vanguard", 7, 6)],
    select: "rs",
    focus: { x: 4.5, y: 8, radius: 3.4 },
    mode: "mountains",
  },
];

interface SandboxState {
  position: Position;
  legalMoves: LegalMove[];
  lastMove: MoveRecord | null;
}

function SituationBoard({ s }: { s: Situation }) {
  const t = useT();
  const [state, setState] = useState<SandboxState | null>(null);
  const [preview, setPreview] = useState<LegalMove | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [round, setRound] = useState(0);

  const load = useCallback(
    async (pieces: PieceT[], ply: number, move?: LegalMove) => {
      setError(null);
      try {
        const r = await api<SandboxState>("sandbox", {
          body: {
            heights: s.heights,
            pieces,
            side: 1,
            ply,
            move: move ? { pieceId: move.pieceId, kind: move.kind, to: move.to } : undefined,
          },
        });
        setState(r);
      } catch (e) {
        setError((e as Error).message);
      }
    },
    [s.heights],
  );

  useEffect(() => {
    setState(null);
    void load(s.pieces, 0);
  }, [s.pieces, load, round]);

  const moved = (state?.position.ply ?? 0) > 0;
  const lastMove = useMemo(() => state?.lastMove ?? null, [state]);

  return (
    <div className="situationPlay">
      <div className="scenarioFrame">
        {state ? (
          <Board3D
            className="board3d scenario3d"
            heights={s.heights}
            terrainMode={s.mode}
            pieces={state.position.pieces}
            orientation={1}
            legalMoves={state.legalMoves}
            lastMove={lastMove}
            interactive
            focus={s.focus}
            autoSelect={moved ? null : s.select}
            autoPreview={moved ? null : s.preview ?? null}
            onMove={(m) => void load(state.position.pieces, state.position.ply, m)}
            onPreview={setPreview}
          />
        ) : (
          <LoadingBoard />
        )}
        {moved && (
          <button className="btn small replayBtn" onClick={() => setRound((r) => r + 1)}>
            {t.rules.situations.replay}
          </button>
        )}
      </div>
      {preview?.combat ? (
        <CombatCard combat={preview.combat} />
      ) : (
        <p className="muted small scenarioHint">
          {moved ? t.rules.situations.hintMoved : t.rules.situations.hintStart}
        </p>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  );
}

export function Situations() {
  const t = useT();
  return (
    <div className="situations">
      {SITUATIONS.map((s, i) => (
        <article key={s.id} className="situation">
          <div className="situationText">
            <span className="situationNum">{i + 1}</span>
            <h3>{t.rules.situations.list[s.id].title}</h3>
            <p>{t.rules.situations.list[s.id].text}</p>
          </div>
          <LazyMount minHeight={260}>
            <SituationBoard s={s} />
          </LazyMount>
        </article>
      ))}
    </div>
  );
}
