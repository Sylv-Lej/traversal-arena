"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import { useT } from "./i18n/client";
import { useMe } from "./me";
import type { GameView, LegalMove } from "./types";

/**
 * État d'une partie, tenu à jour par le flux SSE du serveur (relayé par /api/...).
 * EventSource se reconnecte tout seul ; à chaque (re)connexion le serveur renvoie la
 * vue complète, donc aucun évènement ne peut être « perdu ».
 */
export function useGame(id: string) {
  const { ready } = useMe();
  // Ref : changer de langue ne doit pas rouvrir le flux de la partie.
  const t = useT();
  const tRef = useRef(t);
  tRef.current = t;
  const [view, setView] = useState<GameView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [receivedAt, setReceivedAt] = useState(0);
  const [spectators, setSpectators] = useState(0);
  const versionRef = useRef(0);

  const accept = useCallback((v: GameView) => {
    // Le même état arrive souvent deux fois (réponse du POST + flux SSE) : on ignore
    // tout ce qui n'est pas strictement plus récent, sinon React re-rend la partie et
    // relance les animations en cours.
    if (v.version <= versionRef.current) return;
    versionRef.current = v.version;
    setSpectators(v.spectators ?? 0);
    setView(v);
    setReceivedAt(performance.now());
  }, []);

  useEffect(() => {
    versionRef.current = 0; // nouvelle partie (ex. revanche) : on repart de zéro
    setView(null);
  }, [id]);

  useEffect(() => {
    if (!ready) return;
    let closed = false;
    api<GameView>(`games/${id}`)
      .then((v) => !closed && accept(v))
      .catch((e: ApiError) => !closed && setError(e.status === 404 ? tRef.current.game.notFound : e.message));
    const es = new EventSource(`/api/games/${id}/stream`);
    es.addEventListener("state", (ev) => {
      try {
        accept(JSON.parse((ev as MessageEvent).data));
        setConnected(true);
      } catch {
        /* évènement illisible : on attend le suivant */
      }
    });
    // Le nombre de spectateurs change sans que la partie change (pas de nouvelle version).
    es.addEventListener("spectators", (ev) => {
      try {
        setSpectators(JSON.parse((ev as MessageEvent).data).count ?? 0);
      } catch {
        /* ignoré */
      }
    });
    es.onerror = () => setConnected(false);
    return () => {
      closed = true;
      es.close();
    };
  }, [id, ready, accept]);

  const call = useCallback(
    async (path: string, body?: unknown) => {
      setError(null);
      try {
        const v = await api<GameView>(`games/${id}/${path}`, { method: "POST", body: body ?? {} });
        if (v.id === id) accept(v);
        return v;
      } catch (e) {
        setError((e as Error).message);
        if ((e as ApiError).status === 409) {
          api<GameView>(`games/${id}`).then(accept).catch(() => undefined);
        }
        return null;
      }
    },
    [id, accept],
  );

  const play = useCallback(
    (m: LegalMove) => call("moves", { pieceId: m.pieceId, kind: m.kind, to: m.to, version: view?.version }),
    [call, view?.version],
  );

  return {
    view,
    error,
    setError,
    connected,
    receivedAt,
    spectators,
    play,
    join: () => call("join"),
    resign: () => call("resign"),
    abort: () => call("abort"),
    draw: (action: "offer" | "accept" | "decline") => call("draw", { action }),
    rematch: () => call("rematch"),
  };
}
