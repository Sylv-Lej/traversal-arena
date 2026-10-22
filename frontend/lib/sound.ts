"use client";

// Petits sons synthétisés (WebAudio) : aucun fichier audio à charger.

let ctx: AudioContext | null = null;

function audio(): AudioContext | null {
  if (typeof window === "undefined") return null;
  if (!ctx) {
    const AC = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AC) return null;
    ctx = new AC();
  }
  if (ctx.state === "suspended") void ctx.resume();
  return ctx;
}

function tone(freq: number, dur: number, type: OscillatorType, gain: number, delay = 0, slide = 0) {
  const a = audio();
  if (!a) return;
  const t = a.currentTime + delay;
  const osc = a.createOscillator();
  const g = a.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, t);
  if (slide) osc.frequency.exponentialRampToValueAtTime(freq * slide, t + dur);
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(gain, t + 0.01);
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  osc.connect(g).connect(a.destination);
  osc.start(t);
  osc.stop(t + dur + 0.02);
}

export const sounds = {
  move: () => tone(420, 0.09, "triangle", 0.18, 0, 0.7),
  capture: () => {
    tone(160, 0.22, "sawtooth", 0.12, 0, 0.5);
    tone(90, 0.3, "sine", 0.25, 0.02, 0.6);
  },
  exit: () => {
    tone(660, 0.14, "sine", 0.15);
    tone(880, 0.18, "sine", 0.15, 0.1);
    tone(1320, 0.3, "sine", 0.12, 0.2);
  },
  end: () => {
    tone(523, 0.2, "triangle", 0.15);
    tone(659, 0.2, "triangle", 0.15, 0.15);
    tone(784, 0.4, "triangle", 0.15, 0.3);
  },
  tick: () => tone(1200, 0.03, "square", 0.05),
  notify: () => tone(740, 0.12, "sine", 0.12),
};
