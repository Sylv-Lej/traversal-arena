"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { PuzzleBoard, usePuzzle } from "@/components/puzzles/PuzzlePlayer";
import { Flag } from "@/components/ui/Flag";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n/client";
import { useMe } from "@/lib/me";
import type { PuzzleRush, PuzzleStats } from "@/lib/types";

const MODES = ["3min", "5min", "survival"] as const;
type Mode = (typeof MODES)[number];
type Row = { rank: number; id: string; name: string; country: string | null; score: number };

function clock(ms: number): string {
  const s = Math.ceil(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** Puzzle Rush : un max de puzzles, de plus en plus durs, 3 erreurs et c'est fini. */
export default function RushPage() {
  const t = useT();
  const { ready } = useMe();
  const [mode, setMode] = useState<Mode>("5min");
  const [rush, setRush] = useState<PuzzleRush | null>(null);
  const [stats, setStats] = useState<PuzzleStats | null>(null);
  const [board, setBoard] = useState<Row[]>([]);
  const [left, setLeft] = useState<number | null>(null);
  const [prevBest, setPrevBest] = useState(0);
  const received = useRef(0);
  const p = usePuzzle(rush?.attempt ?? null);

  useEffect(() => {
    if (!ready) return;
    api<PuzzleStats>("puzzles/stats").then(setStats).catch(() => undefined);
  }, [ready, rush?.status]);
  useEffect(() => {
    api<Row[]>(`puzzles/rush/leaderboard?mode=${mode}`).then(setBoard).catch(() => undefined);
  }, [mode, rush?.status]);

  const refresh = useCallback(async (id: string) => {
    const r = await api<PuzzleRush>(`puzzles/rush/${id}`);
    received.current = performance.now();
    setRush(r);
  }, []);

  // Puzzle terminé : on laisse voir le résultat un instant, puis le suivant.
  const status = p.att?.status;
  useEffect(() => {
    if (!rush || rush.status !== "running" || !status || status === "playing") return;
    const timer = setTimeout(() => void refresh(rush.id), 700);
    return () => clearTimeout(timer);
  }, [status, rush, refresh]);

  // Chrono local ; à zéro, le serveur arrête le Rush.
  useEffect(() => {
    if (!rush || rush.status !== "running" || rush.remainingMs == null) {
      setLeft(null);
      return;
    }
    const tick = () => {
      const ms = rush.remainingMs! - (performance.now() - received.current);
      setLeft(Math.max(0, ms));
      if (ms <= 0) void refresh(rush.id);
    };
    tick();
    const timer = setInterval(tick, 250);
    return () => clearInterval(timer);
  }, [rush, refresh]);

  async function start() {
    setPrevBest(stats?.rushBest[mode] ?? 0);
    const r = await api<PuzzleRush>("puzzles/rush", { body: { mode } });
    received.current = performance.now();
    setRush(r);
  }

  const running = rush?.status === "running";
  const over = rush?.status === "over";
  const strikes = rush ? Array.from({ length: rush.maxStrikes }, (_, i) => i < rush.strikes) : [];

  return (
    <div className="page puzzlePage">
      <div className="puzzleGrid">
        <section className="puzzleBoard">
          {running ? <PuzzleBoard p={p} /> : <div className="board3d loadingBoard rushIdle" />}
        </section>
        <aside className="card stack">
          <h1 className="pageTitle">{t.puzzles.rush}</h1>
          {!running && !over && (
            <>
              <p className="muted">{t.puzzles.rushIntro}</p>
              <div className="typeGrid">
                {MODES.map((m) => (
                  <button key={m} className={`typeBtn ${mode === m ? "on" : ""}`} onClick={() => setMode(m)}>
                    <strong>{t.puzzles.rushModes[m]}</strong>
                    <small>{t.puzzles.rushModeDesc[m]}</small>
                    <span className="typeClock">{t.puzzles.best(stats?.rushBest[m] ?? 0)}</span>
                  </button>
                ))}
              </div>
              <button className="btn primary huge" onClick={() => void start()} disabled={!ready}>
                {t.puzzles.start}
              </button>
            </>
          )}
          {rush && (running || over) && (
            <div className="rushHud">
              <div className={left != null && left < 15_000 ? "low" : ""}>
                <small className="muted">{t.puzzles.timeLeft}</small>
                <b>{left != null ? clock(left) : "∞"}</b>
              </div>
              <div>
                <small className="muted">{t.puzzles.score}</small>
                <b>
                  {rush.score}
                  <small className="muted"> / {rush.maxPuzzles}</small>
                </b>
              </div>
              <div>
                <small className="muted">{t.puzzles.strikes}</small>
                <b className="strikes">
                  {strikes.map((on, i) => (
                    <span key={i} className={on ? "on" : "off"}>
                      ✗
                    </span>
                  ))}
                </b>
              </div>
            </div>
          )}
          {running && p.att && (
            <p className="muted small">
              {p.att.status === "playing" ? t.puzzles.yourTurn(t.common.sides[p.att.side]) : p.att.status === "solved" ? `✓ ${t.puzzles.correct}` : `✗ ${t.puzzles.wrongMove}`}
            </p>
          )}
          {over && rush && (
            <div className="stack center">
              <div className="endTitle">{t.puzzles.rushOver}</div>
              {rush.score > prevBest && rush.score > 0 && <p className="delta up">{t.puzzles.newRecord}</p>}
              <p className="muted">{t.puzzles.best(rush.best)}</p>
              <button className="btn primary big" onClick={() => setRush(null)}>
                {t.puzzles.playAgain}
              </button>
            </div>
          )}
          {rush && rush.history.length > 0 && (
            <div className="rushTrail">
              {rush.history.map((h, i) => (
                <span key={i} className={h.solved ? "ok" : "ko"} title={String(h.rating)}>
                  {h.solved ? "✓" : "✗"}
                </span>
              ))}
            </div>
          )}
          {!running && (
            <>
              <h3>
                {t.puzzles.rushBoard} · {t.puzzles.rushModes[mode]}
              </h3>
              {board.length === 0 ? (
                <p className="muted small">{t.puzzles.noScores}</p>
              ) : (
                <ol className="miniBoard">
                  {board.map((r) => (
                    <li key={r.id}>
                      <span>
                        {r.rank}. <Flag code={r.country} /> {r.name}
                      </span>
                      <b>{r.score}</b>
                    </li>
                  ))}
                </ol>
              )}
              <Link className="small" href="/puzzles">
                {t.puzzles.backToPuzzles}
              </Link>
            </>
          )}
        </aside>
      </div>
    </div>
  );
}
