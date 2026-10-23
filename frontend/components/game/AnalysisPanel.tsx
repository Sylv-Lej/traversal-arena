"use client";

import { useEffect, useId, useRef, useState } from "react";
import type { Analysis, AnalysisStatus, AnalyzedMove, Eval, MoveClass, Side } from "@/lib/types";
import { useT } from "@/lib/i18n/client";
import type { Dict } from "@/lib/i18n/dict";

// Libellés traduits : t.analysis.classes[c].
export const CLASS_META: Record<MoveClass, { sym: string }> = {
  best: { sym: "★" },
  excellent: { sym: "!" },
  good: { sym: "✓" },
  inaccuracy: { sym: "?!" },
  mistake: { sym: "?" },
  blunder: { sym: "??" },
  forced: { sym: "□" },
};
const ORDER: MoveClass[] = ["best", "excellent", "good", "inaccuracy", "mistake", "blunder", "forced"];

/** Probabilité de gain de Rouge (0..1) — même échelle que le moteur (app/analysis.py). */
export function redWinProb(e: Eval): number {
  if (e.win) return e.win === 1 ? 1 : 0;
  return 1 / (1 + Math.exp((-e.score * 100) / 300));
}

export function formatEval(e: Eval, t: Dict): string {
  if (e.win) return t.analysis.wins(t.common.sides[e.win === 1 ? 1 : 2]);
  const v = Math.abs(e.score) < 0.05 ? 0 : e.score;
  return `${v > 0 ? "+" : ""}${t.analysis.dec(v)}`;
}

export function ClassBadge({ c }: { c: MoveClass }) {
  const t = useT();
  return (
    <span className={`clsBadge cls-${c}`} title={t.analysis.classes[c]} aria-label={t.analysis.classes[c]}>
      {CLASS_META[c].sym}
    </span>
  );
}

/** Barre verticale d'évaluation, posée le long du plateau (Rouge côté Rouge). */
export function EvalBar({ e, redAtBottom }: { e: Eval; redAtBottom: boolean }) {
  const t = useT();
  const red = redWinProb(e) * 100;
  return (
    <div className={`evalBar ${redAtBottom ? "" : "flip"}`} aria-label={t.analysis.evalLabel(formatEval(e, t))}>
      <div className="evalRed" style={{ height: `${red}%` }} />
      <span className={`evalLabel ${red >= 50 ? "onRed" : "onBlue"}`}>{e.win ? t.analysis.winShort : Math.abs(e.score) >= 10 ? Math.round(Math.abs(e.score)) : t.analysis.dec(Math.abs(e.score))}</span>
    </div>
  );
}

// --- Courbe d'avantage -----------------------------------------------------------------
// Polarité (qui mène ?) : deux pôles aux couleurs des camps, ligne médiane neutre.
const RED = "#e5484d";
const BLUE = "#3e7bfa";
const GRID = "#3a3835";
const SURFACE = "#21201d";

function EvalGraph({
  a,
  current,
  onSelect,
}: {
  a: Analysis;
  current: number;
  onSelect: (ply: number) => void;
}) {
  const t = useT();
  const wrap = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(320);
  const [hover, setHover] = useState<number | null>(null);
  const uid = useId().replace(/:/g, "");
  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([en]) => setW(Math.max(220, en.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const h = 110;
  const pts = [a.initialEval, ...a.moves.map((m) => m.eval)].map(redWinProb);
  const n = pts.length - 1;
  const x = (i: number) => (n === 0 ? w / 2 : (i / n) * w);
  const y = (p: number) => 4 + (1 - p) * (h - 8);
  const mid = y(0.5);
  const line = pts.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p).toFixed(1)}`).join("");
  const area = `${line}L${x(n)},${mid}L${x(0)},${mid}Z`;
  const pick = (cx: number) => {
    const r = wrap.current?.getBoundingClientRect();
    if (!r) return 0;
    return Math.max(0, Math.min(n, Math.round(((cx - r.left) / r.width) * n)));
  };
  const hv = hover;
  const hm: AnalyzedMove | null = hv && hv > 0 ? a.moves[hv - 1] : null;

  return (
    <div className="evalGraph" ref={wrap}>
      <svg
        width={w}
        height={h}
        role="img"
        aria-label={t.analysis.graphLabel}
        onPointerMove={(e) => setHover(pick(e.clientX))}
        onPointerLeave={() => setHover(null)}
        onClick={(e) => onSelect(pick(e.clientX))}
      >
        <defs>
          <clipPath id={`above${uid}`}>
            <rect x={0} y={0} width={w} height={mid} />
          </clipPath>
          <clipPath id={`below${uid}`}>
            <rect x={0} y={mid} width={w} height={h - mid} />
          </clipPath>
        </defs>
        <path d={area} fill={RED} opacity={0.35} clipPath={`url(#above${uid})`} />
        <path d={area} fill={BLUE} opacity={0.35} clipPath={`url(#below${uid})`} />
        <line x1={0} x2={w} y1={mid} y2={mid} stroke={GRID} strokeWidth={1} />
        <path d={line} fill="none" stroke="#d6d3ce" strokeWidth={2} strokeLinejoin="round" />
        {a.moves.map((m, i) =>
          m.class === "mistake" || m.class === "blunder" ? (
            <circle key={m.ply} cx={x(i + 1)} cy={y(pts[i + 1])} r={4.5} className={`dot-${m.class}`} stroke={SURFACE} strokeWidth={2} />
          ) : null,
        )}
        <line x1={x(current)} x2={x(current)} y1={0} y2={h} stroke="#f7ec74" strokeWidth={1.5} />
        {hv !== null && <line x1={x(hv)} x2={x(hv)} y1={0} y2={h} stroke="#9a9894" strokeWidth={1} />}
      </svg>
      {hv !== null && (
        <div className="chartTip" style={{ left: Math.min(Math.max(x(hv), 80), w - 80), top: -6 }}>
          <strong>{formatEval(hv === 0 ? a.initialEval : a.moves[hv - 1].eval, t)}</strong>
          {hm ? (
            <span className="tipLine">
              {Math.ceil(hm.ply / 2)}. {hm.notation} · {t.analysis.classes[hm.class]}
            </span>
          ) : (
            <span className="tipLine muted">{t.analysis.startPosition}</span>
          )}
        </div>
      )}
    </div>
  );
}

// --- Panneau ---------------------------------------------------------------------------

export function AnalysisPanel({
  status,
  analysis,
  start,
  error,
  names,
  current,
  onSelect,
  showHint,
  setShowHint,
}: {
  status: AnalysisStatus | null;
  analysis: Analysis | null;
  start: () => void;
  error: string | null;
  names: [string, string];
  current: number;
  onSelect: (ply: number) => void;
  showHint: boolean;
  setShowHint: (v: boolean) => void;
}) {
  const t = useT();
  if (!analysis) {
    const running = status?.status === "queued" || status?.status === "running";
    return (
      <div className="analysisPanel">
        <p className="muted small">{t.analysis.intro}</p>
        {running ? (
          <div className="progress" aria-live="polite">
            <div className="progressBar" style={{ width: `${status!.total ? (100 * status!.done) / status!.total : 5}%` }} />
            <span>
              {status!.byArena
                ? t.analysis.byArena
                : status!.status === "queued"
                  ? t.analysis.queued
                  : t.analysis.progress(status!.done, status!.total)}
            </span>
          </div>
        ) : (
          <button className="btn primary" onClick={start}>
            {t.analysis.start}
          </button>
        )}
        {status?.status === "error" && <p className="error">{t.analysis.failed}</p>}
        {error && <p className="error">{error}</p>}
      </div>
    );
  }

  const m = current > 0 ? analysis.moves[current - 1] : null;
  return (
    <div className="analysisPanel">
      <div className="accRow">
        {([1, 2] as Side[]).map((s) => (
          <div key={s} className={`accTile side${s}`}>
            <span className="accName">
              <span className={`teamDot side${s}`} /> {names[s - 1]}
            </span>
            <span className="accValue">{analysis.accuracy[s - 1] != null ? t.analysis.dec(analysis.accuracy[s - 1]!) : "—"}</span>
            <span className="accLabel">{t.analysis.accuracy}</span>
          </div>
        ))}
      </div>

      <EvalGraph a={analysis} current={current} onSelect={onSelect} />

      {m && (
        <div className={`moveVerdict cls-${m.class}`}>
          <div className="verdictHead">
            <ClassBadge c={m.class} />
            <b>
              {Math.ceil(m.ply / 2)}. {m.notation}
            </b>
            <span>{t.analysis.classes[m.class]}</span>
            <span className="verdictEval">{formatEval(m.eval, t)}</span>
          </div>
          {m.best ? (
            <div className="verdictBest">
              <span>
                {t.analysis.bestMove} <b>{m.best.notation}</b> ({formatEval(m.best.eval, t)})
              </span>
              <label className="check small">
                <input type="checkbox" checked={showHint} onChange={(e) => setShowHint(e.target.checked)} />
                {t.analysis.showOnBoard}
              </label>
            </div>
          ) : (
            m.class !== "forced" && <div className="verdictBest muted">{t.analysis.wasBest}</div>
          )}
        </div>
      )}

      <table className="table countTable">
        <thead>
          <tr>
            <th />
            <th className="num">
              <span className="teamDot side1" />
            </th>
            <th className="num">
              <span className="teamDot side2" />
            </th>
          </tr>
        </thead>
        <tbody>
          {ORDER.filter((c) => (analysis.counts[0][c] ?? 0) + (analysis.counts[1][c] ?? 0) > 0).map((c) => (
            <tr key={c}>
              <td>
                <ClassBadge c={c} /> {t.analysis.classes[c]}
              </td>
              <td className="num">{analysis.counts[0][c] ?? 0}</td>
              <td className="num">{analysis.counts[1][c] ?? 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">
        {analysis.engine
          ? t.analysis.analysedWith(analysis.engine.bot.name, analysis.engine.bot.rating)
          : t.analysis.analysedWithOrque}{" "}
        {t.analysis.footer(analysis.depth)}
      </p>
    </div>
  );
}
