"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n/client";
import type { LegalMove, MoveRecord, Position, PuzzleAttempt } from "@/lib/types";

const Board3D = dynamic(() => import("@/components/board3d/Board3D"), {
  ssr: false,
  loading: () => <div className="board3d loadingBoard" />,
});

const STEP_MS = 650; // entre deux coups animés (coup adverse, réponse…)

type Frame = { position: Position; lastMove: MoveRecord | null };

/**
 * Plateau d'un puzzle : anime le coup de l'adversaire au départ, puis chaque coup joué et
 * sa réponse, le coup raté, et la solution pas à pas. Envoie les coups au serveur, qui
 * vérifie (la solution n'est jamais connue du navigateur avant la fin).
 */
export function usePuzzle(initial: PuzzleAttempt | null) {
  const [att, setAtt] = useState<PuzzleAttempt | null>(initial);
  const [frame, setFrame] = useState<Frame | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hintPiece, setHintPiece] = useState<string | null>(null);
  const [solIdx, setSolIdx] = useState<number | null>(null); // relecture de la solution
  const shown = useRef<{ id: string; count: number } | null>(null);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => setAtt(initial), [initial]);

  // File d'animation : on montre les coups qui n'ont pas encore été vus, un par un.
  useEffect(() => {
    if (!att) return;
    timers.current.forEach(clearTimeout);
    timers.current = [];
    const fresh = shown.current?.id !== att.id;
    const from = fresh ? 0 : shown.current!.count;
    const frames: Frame[] = [];
    if (fresh) frames.push({ position: att.positions[0], lastMove: null });
    for (let k = Math.max(1, from + 1); k < att.positions.length; k++) {
      frames.push({ position: att.positions[k], lastMove: att.moves[k - 1] });
    }
    if (att.wrong && att.wrongPosition) frames.push({ position: att.wrongPosition, lastMove: att.wrong });
    // Nouveau puzzle : la position de départ, puis le coup adverse après une courte pause.
    // Ensuite : le coup du joueur tout de suite, puis la réponse adverse.
    frames.forEach((f, i) => {
      const delay = fresh ? (i === 0 ? 0 : 450 + (i - 1) * STEP_MS) : i * STEP_MS;
      timers.current.push(setTimeout(() => setFrame(f), delay));
    });
    shown.current = { id: att.id, count: att.positions.length - 1 };
    if (fresh) {
      setHintPiece(null);
      setSolIdx(null);
    }
    return () => timers.current.forEach(clearTimeout);
  }, [att]);

  // Relecture de la solution : position après `solIdx` coups.
  useEffect(() => {
    if (solIdx === null || !att?.solutionPositions || !att.solution) return;
    setFrame({ position: att.solutionPositions[solIdx], lastMove: solIdx > 0 ? att.solution[solIdx - 1] : null });
  }, [solIdx, att]);

  const atCurrent = !!att && !!frame && frame.position === att.positions[att.positions.length - 1];
  const playing = att?.status === "playing";

  const play = useCallback(
    async (m: LegalMove) => {
      if (!att || busy) return;
      setBusy(true);
      setError(null);
      // Le coup du joueur s'affiche tout de suite (avant la réponse du serveur).
      setHintPiece(null);
      try {
        const next = await api<PuzzleAttempt>(`puzzles/attempts/${att.id}/move`, {
          body: { pieceId: m.pieceId, kind: m.kind, to: m.to },
        });
        setAtt(next);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setBusy(false);
      }
    },
    [att, busy],
  );

  const hint = useCallback(async () => {
    if (!att) return;
    const h = await api<{ pieceId: string; sq: number }>(`puzzles/attempts/${att.id}/hint`, { method: "POST" });
    setHintPiece(h.pieceId);
    setAtt({ ...att, hinted: true });
  }, [att]);

  const reveal = useCallback(async () => {
    if (!att) return;
    const next = await api<PuzzleAttempt>(`puzzles/attempts/${att.id}/solution`, { method: "POST" });
    setAtt(next);
    setSolIdx(1);
  }, [att]);

  return { att, setAtt, frame, play, hint, reveal, busy, error, hintPiece, solIdx, setSolIdx, atCurrent, playing };
}

export function PuzzleBoard({ p }: { p: ReturnType<typeof usePuzzle> }) {
  const t = useT();
  const { att, frame, solIdx } = p;
  const legal = useMemo(
    () => (att && p.playing && p.atCurrent && !p.busy ? att.legalMoves : []),
    [att, p.playing, p.atCurrent, p.busy],
  );
  if (!att || !frame) return <div className="board3d loadingBoard" aria-label={t.puzzles.loading} />;
  // Relecture : le prochain coup de la solution est tracé en doré.
  const nextSol = solIdx !== null && att.solution && solIdx < att.solution.length ? att.solution[solIdx] : null;
  return (
    <Board3D
      heights={att.terrain.heights}
      terrainMode={att.terrain.mode}
      pieces={frame.position.pieces}
      orientation={att.side}
      legalMoves={legal}
      lastMove={frame.lastMove}
      animate
      interactive={legal.length > 0}
      intro
      autoSelect={p.hintPiece}
      hint={nextSol ? { path: nextSol.path, kind: nextSol.kind, owner: nextSol.side } : null}
      onMove={(m) => void p.play(m)}
    />
  );
}
