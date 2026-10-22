"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { LOCALES } from "@/lib/i18n/core";
import { useLang, useT } from "@/lib/i18n/client";

export interface RatingPoint {
  gameId: string;
  t: number;
  before: number;
  rating: number;
  result: "win" | "loss" | "draw";
  opponent: string;
}

// Une seule série : pas de légende, le titre de la carte dit ce qui est tracé.
const LINE = "#81b64c"; // accent du site (contraste ≥ 3:1 sur la surface sombre)
const SURFACE = "#262522";
const GRID = "#3a3835";
const INK = "#e8e6e3";
const MUTED = "#9a9894";

function niceStep(range: number, target = 4): number {
  const raw = range / target;
  const steps = [5, 10, 20, 25, 50, 100, 200, 250, 500];
  return steps.find((s) => s >= raw) ?? 1000;
}

/**
 * Évolution du classement, partie après partie (axe X = parties classées, pas le temps :
 * dix parties jouées le même soir restent lisibles). Le point 0 est le classement de départ.
 */
export function RatingChart({ points }: { points: RatingPoint[] }) {
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const t = useT();
  const { lang } = useLang();
  const tc = t.profile.chart;
  const fmtDate = (ts: number) =>
    new Date(ts * 1000).toLocaleDateString(LOCALES[lang], { day: "numeric", month: "short", year: "numeric" });

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(260, e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Série : départ (avant la 1re partie) puis le classement après chaque partie.
  const series = useMemo(() => (points.length ? [points[0].before, ...points.map((p) => p.rating)] : []), [points]);

  const height = width < 480 ? 190 : 230;
  const m = { top: 14, right: 52, bottom: 26, left: 44 };
  const iw = width - m.left - m.right;
  const ih = height - m.top - m.bottom;

  const lo = Math.min(...series);
  const hi = Math.max(...series);
  const step = niceStep(Math.max(hi - lo, 20));
  const y0 = Math.floor((lo - step * 0.3) / step) * step;
  const y1 = Math.ceil((hi + step * 0.3) / step) * step;
  const yTicks: number[] = [];
  for (let v = y0; v <= y1 + 1e-6; v += step) yTicks.push(v);

  const n = series.length - 1;
  const x = (i: number) => m.left + (n === 0 ? iw / 2 : (i / n) * iw);
  const y = (v: number) => m.top + ih - ((v - y0) / (y1 - y0)) * ih;
  // Graduations X : un pas « rond » (1, 2, 5, 10…) pour ~3 à 6 repères.
  const every = [1, 2, 5, 10, 20, 25, 50, 100, 200].find((s) => n / s <= (width < 480 ? 3 : 6)) ?? 500;
  const xTicks: number[] = [];
  for (let i = 0; i <= n; i += every) xTicks.push(i);

  const line = series.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const area = `${line}L${x(n).toFixed(1)},${m.top + ih}L${x(0).toFixed(1)},${m.top + ih}Z`;

  function pick(clientX: number) {
    const r = wrap.current?.querySelector("svg")?.getBoundingClientRect();
    if (!r || n < 0) return;
    const i = Math.round(((clientX - r.left - m.left) / Math.max(iw, 1)) * n);
    setHover(Math.max(0, Math.min(n, i)));
  }

  const h = hover;
  const game = h !== null && h > 0 ? points[h - 1] : null;
  const last = series[n];
  const tipLeft = h !== null ? Math.min(Math.max(x(h), 90), width - 90) : 0;

  return (
    <div className="ratingChart" ref={wrap}>
      <svg
        width={width}
        height={height}
        role="img"
        aria-label={tc.aria(series[0], last, n)}
        tabIndex={0}
        onPointerMove={(e) => pick(e.clientX)}
        onPointerDown={(e) => pick(e.clientX)}
        onPointerLeave={() => setHover(null)}
        onBlur={() => setHover(null)}
        onKeyDown={(e) => {
          if (e.key === "ArrowLeft") setHover((v) => Math.max(0, (v ?? n) - 1));
          if (e.key === "ArrowRight") setHover((v) => Math.min(n, (v ?? -1) + 1));
        }}
      >
        {yTicks.map((v) => (
          <g key={v}>
            <line x1={m.left} x2={m.left + iw} y1={y(v)} y2={y(v)} stroke={GRID} strokeWidth={1} />
            <text x={m.left - 8} y={y(v)} fill={MUTED} fontSize={11} textAnchor="end" dominantBaseline="middle">
              {v}
            </text>
          </g>
        ))}
        {xTicks.map((i) => (
          <text key={i} x={x(i)} y={height - 8} fill={MUTED} fontSize={11} textAnchor="middle">
            {i}
          </text>
        ))}

        <path d={area} fill={LINE} opacity={0.1} />
        <path d={line} fill="none" stroke={LINE} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />

        {/* Fin de courbe : point cerclé de la couleur de fond + valeur actuelle. */}
        <circle cx={x(n)} cy={y(last)} r={5} fill={LINE} stroke={SURFACE} strokeWidth={2} />
        <text x={x(n) + 10} y={y(last)} fill={INK} fontSize={13} fontWeight={700} dominantBaseline="middle">
          {last}
        </text>

        {h !== null && (
          <g pointerEvents="none">
            <line x1={x(h)} x2={x(h)} y1={m.top} y2={m.top + ih} stroke={MUTED} strokeWidth={1} />
            <circle cx={x(h)} cy={y(series[h])} r={5} fill={LINE} stroke={SURFACE} strokeWidth={2} />
          </g>
        )}
      </svg>

      {h !== null && (
        <div className="chartTip" style={{ left: tipLeft }}>
          <strong>{series[h]}</strong>
          {game ? (
            <>
              <span className={game.rating >= game.before ? "up" : "down"}>
                {game.rating >= game.before ? "+" : ""}
                {game.rating - game.before}
              </span>
              <span className="tipLine">{tc.against(tc.result[game.result], game.opponent)}</span>
              <span className="tipLine muted">
                {tc.gameN(h)} · {fmtDate(game.t)}
              </span>
            </>
          ) : (
            <span className="tipLine muted">{tc.start}</span>
          )}
        </div>
      )}

      <div className="chartFoot">
        <span className="muted small">{tc.ratedGames}</span>
        <button className="linkBtn small" onClick={() => setTable((v) => !v)}>
          {table ? tc.hideTable : tc.showTable}
        </button>
      </div>
      {table && (
        <div className="chartTable">
          <table className="table">
            <thead>
              <tr>
                <th>#</th>
                <th>{tc.date}</th>
                <th>{tc.opponent}</th>
                <th>{tc.resultCol}</th>
                <th className="num">{tc.rating}</th>
              </tr>
            </thead>
            <tbody>
              {[...points].reverse().map((p, k) => (
                <tr key={p.gameId}>
                  <td className="muted">{points.length - k}</td>
                  <td className="muted">{fmtDate(p.t)}</td>
                  <td>
                    <Link href={`/game/${p.gameId}`}>{p.opponent}</Link>
                  </td>
                  <td>{tc.result[p.result]}</td>
                  <td className="num">
                    <b>{p.rating}</b>{" "}
                    <small className={p.rating >= p.before ? "deltaUp" : "deltaDown"}>
                      ({p.rating >= p.before ? "+" : ""}
                      {p.rating - p.before})
                    </small>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
