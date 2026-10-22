"use client";

import { useEffect, useState } from "react";
import { PuzzlePanel } from "@/components/puzzles/PuzzlePanel";
import { PuzzleBoard, usePuzzle } from "@/components/puzzles/PuzzlePlayer";
import { api } from "@/lib/api";
import { LOCALES } from "@/lib/i18n/core";
import { useLang, useT } from "@/lib/i18n/client";
import { useMe } from "@/lib/me";
import type { PuzzleAttempt } from "@/lib/types";

/** Puzzle du jour : le même pour tout le monde, non classé. */
export default function DailyPuzzlePage() {
  const t = useT();
  const { lang } = useLang();
  const { ready } = useMe();
  const [initial, setInitial] = useState<PuzzleAttempt | null>(null);
  const [error, setError] = useState<string | null>(null);
  const p = usePuzzle(initial);

  useEffect(() => {
    if (!ready) return;
    api<PuzzleAttempt>("puzzles/daily").then(setInitial).catch((e) => setError((e as Error).message));
  }, [ready]);

  const day = new Date().toLocaleDateString(LOCALES[lang], { weekday: "long", day: "numeric", month: "long" });
  return (
    <div className="page puzzlePage">
      <div className="puzzleGrid">
        <section className="puzzleBoard">
          <PuzzleBoard p={p} />
        </section>
        <aside className="card">
          <h1 className="pageTitle">{t.puzzles.daily}</h1>
          <p className="muted small">
            {day} · {t.puzzles.dailyIntro}
          </p>
          {error ? (
            <p className="error">{error}</p>
          ) : (
            <PuzzlePanel p={p} footer={p.att && p.att.status !== "playing" ? <p className="muted">{t.puzzles.dailyDone}</p> : null} />
          )}
        </aside>
      </div>
    </div>
  );
}
