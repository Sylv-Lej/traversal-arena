"use client";

import { useSyncExternalStore } from "react";

export type Quality = "auto" | "high" | "medium" | "low";

export interface Settings {
  quality: Quality;
  showHeights: boolean;
  sound: boolean;
  confirmAttacks: boolean;
  /** Plateau vu de dessus en 2D (hauteurs en couleur) au lieu de la scène 3D. */
  board2d: boolean;
}

const KEY = "traversal.settings";
const DEFAULTS: Settings = { quality: "auto", showHeights: false, sound: true, confirmAttacks: false, board2d: false };

let current: Settings = DEFAULTS;
let loaded = false;
const listeners = new Set<() => void>();

function load(): Settings {
  if (!loaded && typeof window !== "undefined") {
    loaded = true;
    try {
      current = { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) ?? "{}") };
    } catch {
      current = DEFAULTS;
    }
  }
  return current;
}

export function updateSettings(patch: Partial<Settings>) {
  current = { ...load(), ...patch };
  try {
    localStorage.setItem(KEY, JSON.stringify(current));
  } catch {
    /* navigation privée : réglages non persistés */
  }
  listeners.forEach((l) => l());
}

export function useSettings(): Settings {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    load,
    () => DEFAULTS,
  );
}

/** Qualité effective : « auto » = haute sur ordinateur, moyenne sur mobile. */
export function resolveQuality(q: Quality): Exclude<Quality, "auto"> {
  if (q !== "auto") return q;
  if (typeof window === "undefined") return "medium";
  const coarse = window.matchMedia?.("(pointer: coarse)").matches;
  return coarse || window.innerWidth < 900 ? "medium" : "high";
}
