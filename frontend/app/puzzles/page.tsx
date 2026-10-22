"use client";

import { useCallback, useEffect, useState } from "react";
import { PuzzlePanel } from "@/components/puzzles/PuzzlePanel";
import { PuzzleBoard, usePuzzle } from "@/components/puzzles/PuzzlePlayer";
import { RankChip } from "@/components/ui/Rank";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n/client";
import { useMe } from "@/lib/me";
import type { PuzzleAttempt, PuzzleStats } from "@/lib/types";

/** Puzzles classés : un puzzle à ton niveau, puis le suivant. */
export default function PuzzlesPage() {
  const t = useT();
  const { ready } = useMe();
  const [initial, setInitial] = useState<PuzzleAttempt | null>(null);
  const [stats, setStats] = useState<PuzzleStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const p = usePuzzle(initial);

  const loadStats = useCallback(() => api<PuzzleStats>("puzzles/stats").then(setStats).catch(() => undefined), []);
  const next = useCallback(async () => {
    setError(null);
    try {
      setInitial(await api<PuzzleAttempt>("puzzles/next"));
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    if (!ready) return;
    void next();
    void loadStats();
  }, [ready, next, loadStats]);
  // Classement à jour après chaque puzzle terminé.
  useEffect(() => {
    if (p.att && p.att.status !== "playing") void loadStats();
  }, [p.att?.status, p.att, loadStats]);

  const rating = p.att?.ratingChange?.after ?? stats?.rating ?? p.att?.playerRating;
  return (
    <div className="page puzzlePage">
      <div className="puzzleGrid">
        <section className="puzzleBoard">
          <PuzzleBoard p={p} />
        </section>
        <aside className="card">
          <div className="puzzleHead">
            <h1 className="pageTitle">{t.puzzles.title}</h1>
            {rating != null && (
              <div className="puzzleRating">
                <small className="muted">{t.puzzles.rating}</small>
                <b>{rating}</b>
                {stats && <RankChip rank={stats.rank} size={26} />}
              </div>
            )}
          </div>
          {stats && <p className="muted small">{t.puzzles.solved(stats.solved, stats.total)}</p>}
          {error ? (
            <p className="error">{error}</p>
          ) : (
            <PuzzlePanel
              p={p}
              onNext={() => void next()}
              blockOnFail
              onRetry={p.att ? () => void api<PuzzleAttempt>(`puzzles/${p.att!.puzzleId}/retry`, { body: {} }).then(setInitial) : undefined}
            />
          )}
          <p className="muted small">{t.puzzles.intro}</p>
        </aside>
      </div>
    </div>
  );
}
