"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useState } from "react";
import { BoardPreview } from "@/components/board3d/BoardPreview";
import { botSkin, type SkinId } from "@/components/board3d/skins";
import { api } from "@/lib/api";
import { arenaName, type ArenaInfo } from "@/lib/arena";
import { useT } from "@/lib/i18n/client";
import type { GameView, Position } from "@/lib/types";

const Board3D = dynamic(() => import("@/components/board3d/Board3D"), {
  ssr: false,
  loading: () => <div className="board3d hero3d loadingBoard" />,
});

const STEP_MS = 1300; // un demi-coup
const PAUSE_MS = 4000; // fin de partie affichée avant de recommencer

interface Replay {
  view: GameView;
  positions: Position[];
  /** Relecture des parties ouverte (ARENA_REPLAYS) : lien « Revoir » vers la partie. */
  replays: boolean;
}

/** La partie choisie par le serveur pour l'accueil (`arena/showcase`) : seule partie de
 * l'arène visible quand la relecture est fermée. */
async function pickGame(): Promise<Replay | null> {
  const [{ game }, info] = await Promise.all([
    api<{ game: (GameView & { positions: Position[] }) | null }>("arena/showcase"),
    api<ArenaInfo>("arena/info"),
  ]);
  return game ? { view: game, positions: game.positions, replays: info.replays } : null;
}

/** Plateau de l'accueil : rejoue en boucle une vraie partie de l'arène, coup par coup. */
export function ArenaReplay() {
  const t = useT();
  const [replay, setReplay] = useState<Replay | null | undefined>(undefined);
  const [ply, setPly] = useState(0);

  useEffect(() => {
    pickGame()
      .then(setReplay)
      .catch(() => setReplay(null));
  }, []);

  useEffect(() => {
    if (!replay) return;
    const last = replay.positions.length - 1;
    const timer = setTimeout(() => setPly((p) => (p >= last ? 0 : p + 1)), ply >= last ? PAUSE_MS : STEP_MS);
    return () => clearTimeout(timer);
  }, [replay, ply]);

  if (replay === undefined) return <div className="board3d hero3d loadingBoard" />;
  // Pas encore de partie à montrer : plateau décoratif.
  if (replay === null) return <BoardPreview mode="mountains" seed={4} className="board3d hero3d" />;

  const { view, positions, replays } = replay;
  const [red, blue] = view.players;
  const skins: Partial<Record<1 | 2, SkinId>> = {};
  view.players.forEach((p, i) => {
    const level = p?.id.match(/^bot(\d)$/)?.[1];
    if (level) skins[(i + 1) as 1 | 2] = botSkin(Number(level));
  });
  const name = (p: (typeof view.players)[number]) => {
    const level = p?.id.match(/^bot(\d)$/)?.[1];
    return arenaName({ name: p?.name, house: level ? Number(level) : null }, t);
  };

  return (
    <div className="arenaReplay">
      <Board3D
        className="board3d hero3d"
        heights={view.terrain.heights}
        terrainMode={view.terrain.mode}
        pieces={positions[ply].pieces}
        lastMove={ply > 0 ? view.moves[ply - 1] : null}
        animate
        orientation={1}
        skins={skins}
        intro
      />
      <div className="replayCaption">
        <span className="liveDot" aria-hidden="true" />
        <span className="grow">
          <b className="sideRed">{name(red)}</b> {t.arena.vs} <b className="sideBlue">{name(blue)}</b>
          <span className="muted"> · {t.arena.homeReplay.ply(ply, positions.length - 1)}</span>
        </span>
        {replays && <Link href={`/game/${view.id}`}>{t.arena.homeReplay.open}</Link>}
      </div>
    </div>
  );
}
