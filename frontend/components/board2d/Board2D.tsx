"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { Board3DProps } from "@/components/board3d/Board3D";
import type { Kind, LegalMove, Side } from "@/lib/types";
import { LETTERS } from "@/lib/game";
import { ANN_COLORS, annColor, hasAnnotations, type AnnColor } from "@/lib/annotations";
import { useT } from "@/lib/i18n/client";
import { TEAM, heightColor, heightInk } from "./colors";

// Plateau vu de dessus, en SVG : une case = 1 unité. Chaque case prend la teinte de sa
// hauteur (et l'affiche en chiffre) ; un trait d'autant plus épais que la marche est haute
// sépare deux cases de niveaux différents, comme des courbes de niveau. Mêmes props et
// mêmes interactions que Board3D, pour passer de l'un à l'autre sans rien perdre.

const FORCE: Record<Kind, number> = { explorer: 1, vanguard: 2, sentinel: 3 };

type Pt = { x: number; y: number };

function polygon(n: number, r: number): string {
  return Array.from({ length: n }, (_, i) => {
    const a = -Math.PI / 2 + (i / n) * Math.PI * 2;
    return `${(Math.cos(a) * r).toFixed(3)},${(Math.sin(a) * r).toFixed(3)}`;
  }).join(" ");
}

/** Base vue de dessus : autant de coins que de Mouvement (5 / 4 / 3). */
const SHAPES: Record<Kind, string> = {
  explorer: polygon(5, 0.36),
  vanguard: polygon(4, 0.38),
  sentinel: polygon(3, 0.4),
};

/** Points de Force au centre de la pièce. */
const PIPS: Record<number, Pt[]> = {
  1: [{ x: 0, y: 0 }],
  2: [{ x: -0.1, y: 0 }, { x: 0.1, y: 0 }],
  3: [{ x: 0, y: -0.04 }, { x: -0.1, y: 0.12 }, { x: 0.1, y: 0.12 }],
};

/** Flèche pleine de a vers b (centres de cases), pointe comprise. */
function arrowPath(a: Pt, b: Pt, width = 0.2, head = 0.42): string {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  const ux = dx / len;
  const uy = dy / len;
  const nx = -uy;
  const ny = ux;
  const start = { x: a.x + ux * 0.18, y: a.y + uy * 0.18 };
  const tip = { x: b.x - ux * 0.08, y: b.y - uy * 0.08 };
  const neck = { x: tip.x - ux * head, y: tip.y - uy * head };
  const w = width / 2;
  const hw = head * 0.6;
  const p = [
    [start.x + nx * w, start.y + ny * w],
    [neck.x + nx * w, neck.y + ny * w],
    [neck.x + nx * hw, neck.y + ny * hw],
    [tip.x, tip.y],
    [neck.x - nx * hw, neck.y - ny * hw],
    [neck.x - nx * w, neck.y - ny * w],
    [start.x - nx * w, start.y - ny * w],
  ];
  return `M${p.map(([x, y]) => `${x.toFixed(3)},${y.toFixed(3)}`).join("L")}Z`;
}

export default function Board2D({
  heights,
  pieces,
  orientation,
  legalMoves = [],
  lastMove = null,
  animate = true,
  interactive = false,
  autoSelect = null,
  autoPreview = null,
  hint = null,
  annotations,
  onAnnotate,
  onClearAnnotations,
  drawMode = false,
  onMove,
  onPreview,
  className,
}: Board3DProps) {
  const t = useT();
  const svg = useRef<SVGSVGElement>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoverSq, setHoverSq] = useState<number | null>(null);
  const [hoverExit, setHoverExit] = useState(false);
  const [armed, setArmed] = useState<number | "exit" | null>(null);
  const [touchArmed, setTouchArmed] = useState(false);
  const [drag, setDrag] = useState<{ from: number; to: number; color: AnnColor } | null>(null);

  // Repère écran : colonne c (gauche → droite), rangée r (haut → bas). Le camp du joueur
  // est en bas ; le bleu voit le plateau tourné d'un demi-tour.
  const cell = (sq: number) => {
    const x = sq % 10;
    const y = Math.floor(sq / 10);
    return orientation === 1 ? { c: x, r: 9 - y } : { c: 9 - x, r: y };
  };
  const center = (sq: number): Pt => {
    const { c, r } = cell(sq);
    return { x: c + 0.5, y: r + 0.5 };
  };
  /** Sens écran de la sortie d'un camp (-1 = vers le haut). */
  const exitDir = (owner: Side) => ((owner === 1) === (orientation === 1) ? -1 : 1);

  const movesByPiece = useMemo(() => {
    const m = new Map<string, LegalMove[]>();
    for (const mv of legalMoves) {
      if (mv.kind === "pass") continue;
      if (!m.has(mv.pieceId)) m.set(mv.pieceId, []);
      m.get(mv.pieceId)!.push(mv);
    }
    return m;
  }, [legalMoves]);
  const movableIds = useMemo(() => new Set(interactive ? movesByPiece.keys() : []), [movesByPiece, interactive]);

  useEffect(() => {
    const keep = autoSelect && movesByPiece.has(autoSelect) ? autoSelect : null;
    setSelectedId(keep);
    setArmed(keep && autoPreview !== null ? autoPreview : null);
    setTouchArmed(false);
  }, [legalMoves, autoSelect, autoPreview, movesByPiece]);

  const selectedMoves = selectedId ? movesByPiece.get(selectedId) ?? [] : [];
  const bySquare = useMemo(() => new Map(selectedMoves.filter((m) => m.to !== null).map((m) => [m.to as number, m])), [selectedMoves]);
  const exitMove = selectedMoves.find((m) => m.kind === "exit") ?? null;
  const hovered = hoverExit ? exitMove : hoverSq !== null ? bySquare.get(hoverSq) ?? null : null;
  const preview = hovered ?? (armed === "exit" ? exitMove : armed !== null ? bySquare.get(armed) ?? null : null);
  const occupied = useMemo(() => new Map(pieces.map((p) => [p.sq, p])), [pieces]);
  const selectedPiece = pieces.find((p) => p.id === selectedId) ?? null;

  useEffect(() => onPreview?.(preview ?? null), [preview, onPreview]);

  function disarm() {
    setArmed(null);
    setTouchArmed(false);
  }

  function pick(move: LegalMove, key: number | "exit", pointerType: string) {
    if (pointerType === "touch" && armed !== key) {
      setArmed(key);
      setTouchArmed(true);
      return;
    }
    setSelectedId(null);
    disarm();
    onMove?.(move);
  }

  function pickSquare(sq: number | null, pointerType: string) {
    if (!interactive) return;
    const move = sq !== null ? bySquare.get(sq) : undefined;
    if (move) return pick(move, sq!, pointerType);
    const piece = sq !== null ? occupied.get(sq) : undefined;
    if (piece && movableIds.has(piece.id)) {
      setSelectedId(piece.id === selectedId ? null : piece.id);
    } else {
      setSelectedId(null);
    }
    disarm();
  }

  function sqAt(e: React.PointerEvent): number | null {
    const el = svg.current;
    const m = el?.getScreenCTM();
    if (!el || !m) return null;
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(m.inverse());
    const c = Math.floor(p.x);
    const r = Math.floor(p.y);
    if (c < 0 || c > 9 || r < 0 || r > 9) return null;
    const x = orientation === 1 ? c : 9 - c;
    const y = orientation === 1 ? 9 - r : r;
    return y * 10 + x;
  }

  function onDown(e: React.PointerEvent<SVGSVGElement>) {
    const sq = sqAt(e);
    if (onAnnotate && (e.button === 2 || (drawMode && e.button === 0))) {
      e.preventDefault();
      if (sq === null) return;
      e.currentTarget.setPointerCapture(e.pointerId);
      setDrag({ from: sq, to: sq, color: annColor(e) });
      return;
    }
    if (e.button !== 0) return;
    if (hasAnnotations(annotations)) onClearAnnotations?.();
    pickSquare(sq, e.pointerType);
  }

  function onMoveEvt(e: React.PointerEvent<SVGSVGElement>) {
    const sq = sqAt(e);
    if (drag) {
      if (sq !== null && sq !== drag.to) setDrag({ ...drag, to: sq });
      return;
    }
    if (interactive && e.pointerType === "mouse") setHoverSq(sq);
  }

  function onUp() {
    if (!drag) return;
    onAnnotate?.(drag.from, drag.to, drag.color);
    setDrag(null);
  }

  const lastSquares = lastMove && lastMove.kind !== "pass" ? [lastMove.from, lastMove.to].filter((s): s is number => s !== null) : [];

  // Courbes de niveau : un trait sur chaque arête entre deux cases de hauteurs différentes.
  const contours = useMemo(() => {
    const out: { x1: number; y1: number; x2: number; y2: number; d: number }[] = [];
    for (let sq = 0; sq < 100; sq++) {
      const x = sq % 10;
      const y = Math.floor(sq / 10);
      const { c, r } = orientation === 1 ? { c: x, r: 9 - y } : { c: 9 - x, r: y };
      const right = x < 9 ? Math.abs(heights[sq] - heights[sq + 1]) : 0;
      const up = y < 9 ? Math.abs(heights[sq] - heights[sq + 10]) : 0;
      // Côté écran de la case voisine : x+1 est à droite (rouge) ou à gauche (bleu).
      const ex = orientation === 1 ? c + 1 : c;
      const ey = orientation === 1 ? r : r + 1;
      if (right) out.push({ x1: ex, y1: r, x2: ex, y2: r + 1, d: right });
      if (up) out.push({ x1: c, y1: ey, x2: c + 1, y2: ey, d: up });
    }
    return out;
  }, [heights, orientation]);

  const pathPoints = (move: { path: number[]; kind: string }, owner: Side | null) => {
    const pts = move.path.map(center);
    if (move.kind === "exit" && pts.length && owner) {
      const last = pts[pts.length - 1];
      pts.push({ x: last.x, y: last.y + exitDir(owner) * 0.8 });
    }
    return pts.map((p) => `${p.x},${p.y}`).join(" ");
  };

  const exitAt = exitMove && selectedPiece ? (() => {
    const p = center(exitMove.path[exitMove.path.length - 1]);
    return { x: p.x, y: p.y + exitDir(selectedPiece.owner) * 0.78, dir: exitDir(selectedPiece.owner) };
  })() : null;

  return (
    <div className={`${className ?? "board3d"} board2d`} onContextMenu={(e) => e.preventDefault()}>
      {touchArmed && armed !== null && <div className="tapConfirm">{t.board.tapAgain}</div>}
      <svg
        ref={svg}
        viewBox="-0.55 -0.55 11.1 11.1"
        preserveAspectRatio="xMidYMid meet"
        onPointerDown={onDown}
        onPointerMove={onMoveEvt}
        onPointerUp={onUp}
        onPointerCancel={() => setDrag(null)}
        onPointerLeave={() => setHoverSq(null)}
        style={{ cursor: drawMode ? "crosshair" : undefined }}
      >
        {/* Lignes d'arrivée : rouge sort par la rangée 10, bleu par la rangée 1. */}
        {([1, 2] as Side[]).map((s) => (
          <rect key={s} x={0} y={exitDir(s) < 0 ? -0.16 : 10.04} width={10} height={0.12} rx={0.05} fill={TEAM[s].main} />
        ))}

        {heights.map((h, sq) => {
          const { c, r } = cell(sq);
          return (
            <g key={sq}>
              <rect x={c} y={r} width={1} height={1} fill={heightColor(h)} />
              {(c + r) % 2 === 1 && <rect x={c} y={r} width={1} height={1} fill="#000" opacity={0.05} />}
              <text x={c + 0.07} y={r + 0.31} fontSize={0.3} fontWeight={900} fill={heightInk(h)} opacity={0.9} pointerEvents="none">
                {h}
              </text>
            </g>
          );
        })}
        {contours.map((l, i) => (
          <line key={i} x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2} stroke="#14110e" strokeOpacity={0.7} strokeWidth={0.025 + 0.03 * l.d} strokeLinecap="round" />
        ))}

        {/* Coordonnées : lettres en bas, chiffres à gauche. */}
        {Array.from({ length: 10 }, (_, i) => {
          const col = orientation === 1 ? i : 9 - i;
          const row = orientation === 1 ? 9 - i : i;
          return (
            <g key={`l${i}`} fontSize={0.28} fontWeight={700} fill="#8b8782" textAnchor="middle" pointerEvents="none">
              <text x={col + 0.5} y={10.45}>{LETTERS[i]}</text>
              <text x={-0.3} y={row + 0.6}>{i + 1}</text>
            </g>
          );
        })}

        {lastSquares.map((sq) => {
          const { c, r } = cell(sq);
          return <rect key={`last${sq}`} x={c + 0.04} y={r + 0.04} width={0.92} height={0.92} fill="#f7ec74" fillOpacity={0.3} stroke="#f7ec74" strokeWidth={0.07} pointerEvents="none" />;
        })}
        {selectedPiece && (() => {
          const { c, r } = cell(selectedPiece.sq);
          return <rect x={c} y={r} width={1} height={1} fill="#f7ec74" opacity={0.6} pointerEvents="none" />;
        })()}
        {preview && preview.to !== null && preview.kind !== "attack" && (() => {
          const { c, r } = cell(preview.to);
          return <rect x={c} y={r} width={1} height={1} fill={preview.special ? "#b48cff" : "#9be07a"} opacity={0.5} pointerEvents="none" />;
        })()}

        {annotations?.circles.map((a) => {
          const p = center(a.sq);
          return <circle key={`c${a.sq}`} cx={p.x} cy={p.y} r={0.44} fill="none" stroke={ANN_COLORS[a.color]} strokeWidth={0.08} opacity={0.9} pointerEvents="none" />;
        })}

        {pieces.map((p) => {
          const { x, y } = center(p.sq);
          const team = TEAM[p.owner];
          const movable = movableIds.has(p.id);
          return (
            <g
              key={p.id}
              style={{ transform: `translate(${x}px, ${y}px)`, transition: animate ? "transform .25s ease-out" : undefined }}
              pointerEvents="none"
            >
              <ellipse cx={0.03} cy={0.06} rx={0.36} ry={0.34} fill="#000" opacity={0.3} />
              <polygon points={SHAPES[p.kind]} fill={team.main} stroke={movable ? team.glow : team.dark} strokeWidth={movable ? 0.07 : 0.05} strokeLinejoin="round" />
              {PIPS[FORCE[p.kind]].map((d, i) => (
                <circle key={i} cx={d.x} cy={d.y + (p.kind === "sentinel" ? 0.04 : 0)} r={0.055} fill="#fff" />
              ))}
            </g>
          );
        })}

        {selectedMoves.map((m) => {
          if (m.to === null) return null;
          const p = center(m.to);
          if (m.kind === "attack") {
            const ok = m.combat ? m.combat.attack >= m.combat.defense : true;
            return <circle key={`a${m.to}`} cx={p.x} cy={p.y} r={0.45} fill="none" stroke={ok ? "#ff5a4f" : "#9a9a9a"} strokeWidth={preview === m ? 0.1 : 0.07} pointerEvents="none" />;
          }
          return <circle key={`m${m.to}`} cx={p.x} cy={p.y} r={preview === m ? 0.19 : 0.15} fill={m.special ? "#c9a8ff" : "#b6f08f"} stroke="#1d1b18" strokeOpacity={0.5} strokeWidth={0.03} pointerEvents="none" />;
        })}
        {exitAt && exitMove && (
          <g
            style={{ cursor: "pointer" }}
            onPointerDown={(e) => {
              if (e.button !== 0 || drawMode) return;
              e.stopPropagation();
              pick(exitMove, "exit", e.pointerType);
            }}
            onPointerEnter={() => setHoverExit(true)}
            onPointerLeave={() => setHoverExit(false)}
          >
            <circle cx={exitAt.x} cy={exitAt.y} r={0.45} fill="transparent" />
            <polygon
              points={`${exitAt.x - 0.26},${exitAt.y - exitAt.dir * 0.1} ${exitAt.x + 0.26},${exitAt.y - exitAt.dir * 0.1} ${exitAt.x},${exitAt.y + exitAt.dir * 0.22}`}
              fill="#ffe066"
              stroke="#c99a00"
              strokeWidth={0.04}
              opacity={hoverExit || armed === "exit" ? 1 : 0.85}
            />
          </g>
        )}

        {preview && (
          <polyline points={pathPoints(preview, selectedPiece?.owner ?? null)} fill="none" stroke="#fff" strokeWidth={0.07} strokeDasharray="0.18 0.1" strokeLinecap="round" strokeLinejoin="round" opacity={0.9} pointerEvents="none" />
        )}
        {hint && hint.path.length > 0 && (
          <g pointerEvents="none">
            <polyline points={pathPoints(hint, hint.owner)} fill="none" stroke="#f7c631" strokeWidth={0.09} strokeDasharray="0.18 0.1" strokeLinecap="round" strokeLinejoin="round" />
            {hint.kind !== "exit" && (() => {
              const p = center(hint.path[hint.path.length - 1]);
              return <circle cx={p.x} cy={p.y} r={0.36} fill="none" stroke="#f7c631" strokeWidth={0.1} />;
            })()}
          </g>
        )}

        <g pointerEvents="none" opacity={0.82}>
          {annotations?.arrows.map((a) => (
            <path key={`${a.from}-${a.to}`} d={arrowPath(center(a.from), center(a.to))} fill={ANN_COLORS[a.color]} />
          ))}
          {drag && drag.from !== drag.to && <path d={arrowPath(center(drag.from), center(drag.to))} fill={ANN_COLORS[drag.color]} opacity={0.7} />}
        </g>
      </svg>
    </div>
  );
}
