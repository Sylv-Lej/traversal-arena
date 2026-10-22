"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { AnalysisStatus } from "./types";

/** Bilan d'une partie terminée : état, lancement, et suivi de l'avancement (SSE). */
export function useAnalysis(gameId: string, enabled: boolean) {
  const [st, setSt] = useState<AnalysisStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) return;
    api<AnalysisStatus>(`games/${gameId}/analysis`).then(setSt).catch(() => undefined);
  }, [gameId, enabled]);

  const running = st?.status === "queued" || st?.status === "running";
  useEffect(() => {
    if (!running) return;
    const es = new EventSource(`/api/games/${gameId}/analysis/stream`);
    es.addEventListener("analysis", (ev) => {
      try {
        const next = JSON.parse((ev as MessageEvent).data) as AnalysisStatus;
        setSt(next);
        if (next.status === "done" || next.status === "error") es.close();
      } catch {
        /* évènement illisible : on attend le suivant */
      }
    });
    return () => es.close();
  }, [gameId, running]);

  const start = useCallback(async () => {
    setError(null);
    try {
      setSt(await api<AnalysisStatus>(`games/${gameId}/analysis`, { method: "POST", body: {} }));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [gameId]);

  return { status: st, analysis: st?.status === "done" ? st.result ?? null : null, running, start, error };
}
