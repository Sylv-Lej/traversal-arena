"use client";

import { useEffect, useRef, useState } from "react";
import { MAP_TYPES, TERRAINS } from "@/lib/game";
import { useT } from "@/lib/i18n/client";

const LAPS = 3; // tours complets avant de ralentir sur la carte tirée
const HOLD_MS = 1100; // temps laissé pour lire le résultat

/** Tirage au sort de la carte, façon roulette : la sélection défile parmi les cartes en
 * ralentissant et s'arrête sur `target` (déjà tirée par le serveur), puis `onDone`. */
export function MapDraw({ target, onDone }: { target: string; onDone: () => void }) {
  const t = useT();
  const end = Math.max(0, MAP_TYPES.indexOf(target));
  const [step, setStep] = useState(0);
  const total = LAPS * MAP_TYPES.length + end;
  const done = step >= total;
  const finish = useRef(onDone); // le parent peut se re-rendre sans relancer le tirage
  finish.current = onDone;

  useEffect(() => {
    if (done) {
      const timer = setTimeout(() => finish.current(), HOLD_MS);
      return () => clearTimeout(timer);
    }
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const p = step / total;
    const timer = setTimeout(() => setStep(reduced ? total : step + 1), 55 + 330 * p * p * p);
    return () => clearTimeout(timer);
  }, [step, total, done]);

  const key = MAP_TYPES[step % MAP_TYPES.length];
  return (
    <div className={`mapDraw ${done ? "done" : ""}`}>
      <div className="mapDrawRow" aria-hidden>
        {MAP_TYPES.map((m) => (
          <span
            key={m}
            className={`swatch ${m === key ? "on" : ""}`}
            style={{ background: `linear-gradient(135deg, ${TERRAINS[m].swatch.join(", ")})` }}
          />
        ))}
      </div>
      <strong key={step} className="mapDrawName" aria-live="polite">
        {t.common.terrains[key]?.name}
      </strong>
      <small className="muted">{done ? t.common.terrains[key]?.desc : t.play.drawing}</small>
    </div>
  );
}
