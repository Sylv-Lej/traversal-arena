"use client";

import Link from "next/link";
import { useT } from "@/lib/i18n/client";
import type { PuzzleNote } from "@/lib/types";
import type { usePuzzle } from "./PuzzlePlayer";

type T = ReturnType<typeof useT>;

/** Une explication de coup, en clair. */
function noteText(n: PuzzleNote, t: T): string {
  const N = t.puzzles.notes;
  const piece = (k?: string) => (t.common.pieces as Record<string, { name: string }>)[k ?? ""]?.name ?? "";
  switch (n.code) {
    case "scoreWin": {
      const [s1, s2] = n.score ?? [0, 0];
      return N.scoreWin(n.side === 2 ? s2 : s1, n.side === 2 ? s1 : s2);
    }
    case "exit":
      return N.exit(piece(n.kind), n.points ?? 0);
    case "capture":
      return N.capture(piece(n.kind), piece(n.target), n.attack ?? 0, n.defense ?? 0);
    case "support":
      return N.support(piece(n.kind), n.value ?? 0);
    case "reinforced":
      return N.reinforced(n.count ?? 1);
    case "threatExit":
      return N.threatExit(piece(n.kind));
    case "advance":
      return N.advance(piece(n.kind), n.turns ?? 0);
    default: {
      const f = (N as unknown as Record<string, (() => string) | undefined>)[n.code];
      return f ? f() : "";
    }
  }
}

// Leçon associée à chaque explication, par ordre d'importance.
const LESSON_OF: Record<string, string> = {
  doubleThreat: "doubleThreat", parry: "parry", sentinelFirst: "sentinel", sentinelThreat: "sentinel",
  charge: "charge", support: "support", highGround: "height", lowGround: "height", reinforced: "reinforced",
  leap: "explorer", diag: "explorer", threatExit: "tempo", advance: "tempo", scoreWin: "score", exit: "score",
  capture: "combat",
};
const LESSON_ORDER = ["doubleThreat", "parry", "sentinel", "charge", "support", "height", "reinforced", "explorer", "tempo", "score", "combat"];

function lessonsOf(notes: (PuzzleNote[] | null)[]): string[] {
  const keys = new Set(notes.flatMap((ns) => (ns ?? []).map((n) => LESSON_OF[n.code]).filter(Boolean)));
  return LESSON_ORDER.filter((k) => keys.has(k)).slice(0, 3);
}

/** Panneau d'un puzzle : consigne, résultat, indice / solution, relecture, thèmes. */
export function PuzzlePanel({
  p,
  onNext,
  nextLabel,
  onRetry,
  blockOnFail,
  footer,
}: {
  p: ReturnType<typeof usePuzzle>;
  onNext?: () => void;
  nextLabel?: string;
  onRetry?: () => void;
  /** Raté : pas de puzzle suivant, il faut le rejouer (`onNext` ramène le même). */
  blockOnFail?: boolean;
  footer?: React.ReactNode;
}) {
  const t = useT();
  const att = p.att;
  if (!att) return <p className="muted">{t.puzzles.loading}</p>;
  const done = att.status !== "playing";
  const progressed = att.moves.length > 1; // au moins un bon coup déjà joué
  const delta = att.ratingChange ? att.ratingChange.after - att.ratingChange.before : null;
  const sol = att.solution;
  const blocked = done && att.status === "failed" && blockOnFail;
  const shown = sol ? (p.solIdx ?? sol.length) - 1 : -1; // dernier coup affiché de la solution
  const why = done && att.notes && shown >= 0 ? att.notes[shown] : undefined;
  const lessons = done && att.notes ? lessonsOf(att.notes) : [];
  return (
    <div className="stack puzzlePanel">
      {!done && (
        <div className={`puzzleStatus side${att.side}`}>
          <span className={`teamDot side${att.side}`} />
          <div>
            <strong>{progressed ? t.puzzles.keepGoing : t.puzzles.yourTurn(t.common.sides[att.side])}</strong>
            <small className="muted">{t.puzzles.goal[att.goal]?.(att.playerMoves) ?? t.puzzles.movesToFind(att.playerMoves)}</small>
          </div>
        </div>
      )}
      {done && (
        <div className={`puzzleResult ${att.status}`}>
          <strong>{att.status === "solved" ? `✓ ${t.puzzles.solvedTitle}` : `✗ ${t.puzzles.failedTitle}`}</strong>
          {delta !== null && <span className={`delta ${delta >= 0 ? "up" : "down"}`}>{t.puzzles.ratingDelta(delta)}</span>}
          {att.wrong && <small>{t.puzzles.wrongMove}</small>}
          {!att.rated && att.mode === "retry" && <small className="muted">{t.puzzles.notRated}</small>}
        </div>
      )}
      {!done && (
        <div className="row2">
          <button className="btn" onClick={() => void p.hint()} disabled={att.hinted || p.busy} title={att.rated ? t.puzzles.hintRated : undefined}>
            💡 {t.puzzles.hint}
          </button>
          <button className="btn ghost" onClick={() => void p.reveal()} disabled={p.busy}>
            {t.puzzles.showSolution}
          </button>
        </div>
      )}
      {!done && att.rated && att.hinted && <p className="muted small">{t.puzzles.hintRated}</p>}
      {blocked && <p className="small">{t.puzzles.blocked}</p>}
      {done && onNext && (
        <button className="btn primary big" onClick={onNext}>
          {blocked ? t.puzzles.retry : (nextLabel ?? t.puzzles.next)}
        </button>
      )}
      {done && sol && (
        <div className="solutionNav">
          <span className="muted small">
            {t.puzzles.solution} · {t.puzzles.step(p.solIdx ?? sol.length, sol.length)}
          </span>
          <div className="row2">
            <button className="btn small" onClick={() => p.setSolIdx(Math.max(0, (p.solIdx ?? sol.length) - 1))}>
              ‹
            </button>
            <button className="btn small" onClick={() => p.setSolIdx(Math.min(sol.length, (p.solIdx ?? sol.length) + 1))}>
              ›
            </button>
          </div>
        </div>
      )}
      {why !== undefined && (
        <div className="puzzleWhy">
          <strong>{t.puzzles.why}</strong>
          {why === null ? (
            <small className="muted">{t.puzzles.opponentMove}</small>
          ) : (
            <ul>
              {why.map((n, i) => (
                <li key={i}>{noteText(n, t)}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      {lessons.length > 0 && (
        <div className="puzzleLessons">
          <strong>{t.puzzles.lessonsTitle}</strong>
          {lessons.map((k) => (
            <div key={k}>
              <b>{t.puzzles.lessons[k][0]}</b>
              <p className="small muted">{t.puzzles.lessons[k][1]}</p>
            </div>
          ))}
        </div>
      )}
      {done && onRetry && !blocked && (
        <button className="btn" onClick={onRetry}>
          {t.puzzles.retry}
        </button>
      )}
      {done && att.puzzle && (
        <div className="puzzleInfo">
          <span>{t.puzzles.puzzleRating(att.puzzle.rating)}</span>
          <small className="muted">{t.puzzles.successRate(att.puzzle.solves, att.puzzle.plays)}</small>
          <div className="chips">
            {att.puzzle.themes
              .filter((th) => t.puzzles.themes[th])
              .map((th) => (
                <span key={th} className="chip">
                  {t.puzzles.themes[th]}
                </span>
              ))}
          </div>
        </div>
      )}
      {p.error && <p className="error">{p.error}</p>}
      {footer}
      <p className="small">
        <Link href="/puzzles/daily">{t.puzzles.daily}</Link> · <Link href="/puzzles/rush">{t.puzzles.rush}</Link>
      </p>
    </div>
  );
}
