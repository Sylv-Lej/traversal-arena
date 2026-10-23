"use client";

// Ancienne page d'accueil (jouer en ligne, contre un bot, puzzles…), mise de côté tant
// que le site est centré sur l'arène des bots. Pour la remettre : `app/page.tsx` ->
// `export { ClassicHome as default } from "@/components/home/ClassicHome";`

import { Flag } from "@/components/ui/Flag";
import Link from "next/link";
import { useEffect, useState } from "react";
import { BoardPreview } from "@/components/board3d/BoardPreview";
import { IconBook, IconBot, IconPeople, IconPlay, IconPuzzle } from "@/components/ui/icons";
import { api } from "@/lib/api";
import { useMe } from "@/lib/me";
import { useT } from "@/lib/i18n/client";
import { playerName } from "@/lib/i18n/helpers";
import type { GameSummary, LobbyInfo } from "@/lib/types";

function RecentGames() {
  const { me, ready } = useMe();
  const t = useT();
  const [games, setGames] = useState<GameSummary[] | null>(null);
  useEffect(() => {
    if (!ready || !me) return;
    api<GameSummary[]>("me/games").then(setGames).catch(() => setGames([]));
  }, [ready, me]);
  if (!games || games.length === 0) return null;
  return (
    <section className="card">
      <h2 className="cardTitle">{t.home.myGames}</h2>
      <ul className="gameList">
        {games.slice(0, 8).map((g) => {
          const opp = g.players.find((p, i) => p && !g.you.includes((i + 1) as 1 | 2));
          const mine = g.you.length === 1 ? g.you[0] : null;
          const outcome = !g.result
            ? g.status === "waiting"
              ? "waiting"
              : g.status === "aborted"
                ? "aborted"
                : "ongoing"
            : g.result.winner == null
              ? "draw"
              : mine === null
                ? null
                : g.result.winner === mine
                  ? "win"
                  : "loss";
          const label = outcome ? t.home.outcome[outcome] : t.home.sideWins(t.common.sides[g.result!.winner!]);
          return (
            <li key={g.id}>
              <Link href={`/game/${g.id}`}>
                <span className={`pill ${outcome === "win" ? "win" : outcome === "loss" ? "loss" : ""}`}>{label}</span>
                <span className="grow">
                  {g.mode === "local" ? (
                    t.home.localGame
                  ) : (
                    <>
                      {t.home.vs(playerName(opp, t))} <Flag code={opp?.country} />
                    </>
                  )}
                  <small className="muted">
                    {" "}
                    · {t.common.terrains[g.terrain]?.name ?? g.terrain} · {g.timeControl ?? t.home.noClock}
                    {g.result ? ` · ${t.common.reasons[g.result.reason] ?? ""}` : ""}
                  </small>
                </span>
                <span className="muted">
                  ★ {g.scores[0]}–{g.scores[1]}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function ClassicHome() {
  const [lobby, setLobby] = useState<LobbyInfo | null>(null);
  const { ready } = useMe();
  const t = useT();
  useEffect(() => {
    if (!ready) return;
    api<LobbyInfo>("lobby").then(setLobby).catch(() => undefined);
  }, [ready]);

  return (
    <div className="page home">
      <section className="hero">
        <div className="heroBoard">
          <BoardPreview mode="mountains" seed={4} className="board3d hero3d" />
        </div>
        <div className="heroSide">
          <h1>
            {t.home.heroTitle}
            <br />
            <span className="accent">{t.home.heroAccent}</span>
          </h1>
          <p className="lead">{t.home.heroLead}</p>
          <div className="bigButtons">
            <Link href="/play" className="bigBtn primary">
              <IconPlay size={34} />
              <span>
                <strong>{t.home.playOnline}</strong>
                <small>{t.home.playOnlineSub}</small>
              </span>
            </Link>
            <Link href="/play?tab=bot" className="bigBtn">
              <IconBot size={34} />
              <span>
                <strong>{t.home.playBot}</strong>
                <small>{t.home.playBotSub(t.common.bots[1].name, t.common.bots[5].name)}</small>
              </span>
            </Link>
            <Link href="/play?tab=local" className="bigBtn">
              <IconPeople size={34} />
              <span>
                <strong>{t.home.playLocal}</strong>
                <small>{t.home.playLocalSub}</small>
              </span>
            </Link>
            <Link href="/puzzles" className="bigBtn">
              <IconPuzzle size={34} />
              <span>
                <strong>{t.home.puzzles}</strong>
                <small>{t.home.puzzlesSub}</small>
              </span>
            </Link>
            <Link href="/rules" className="bigBtn">
              <IconBook size={34} />
              <span>
                <strong>{t.home.learnRules}</strong>
                <small>{t.home.learnRulesSub}</small>
              </span>
            </Link>
          </div>
          {lobby && (
            <p className="muted stats">
              <b>{lobby.online}</b> {t.home.playersOnline(lobby.online)} ·{" "}
              <Link href="/watch">
                <b>{lobby.playing}</b> {t.home.gamesPlaying(lobby.playing)}
              </Link>
            </p>
          )}
        </div>
      </section>
      <RecentGames />
    </div>
  );
}
