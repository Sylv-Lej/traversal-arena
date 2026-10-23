"use client";

import { Loader } from "@/components/ui/Loader";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Flag } from "@/components/ui/Flag";
import { RankChip } from "@/components/ui/Rank";
import { IconEye } from "@/components/ui/icons";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n/client";
import { playerName } from "@/lib/i18n/helpers";
import { useMe } from "@/lib/me";
import type { LiveGame, PlayerCard } from "@/lib/types";

const REFRESH_MS = 10_000;

function Who({ p, side }: { p: PlayerCard | null; side: 1 | 2 }) {
  const t = useT();
  return (
    <span className="liveWho">
      <span className={`teamDot side${side}`} />
      <strong>{playerName(p, t)}</strong>
      <Flag code={p?.country} />
      {p?.rank && <RankChip rank={p.rank} size={18} />}
      {p?.rating != null && <span className="muted small">{p.rating}</span>}
    </span>
  );
}

/** Parties en ligne en cours, les plus relevées d'abord (rafraîchie toutes les 10 s). */
export default function WatchPage() {
  const t = useT();
  const { ready } = useMe();
  const [games, setGames] = useState<LiveGame[] | null>(null);

  useEffect(() => {
    if (!ready) return;
    let alive = true;
    const load = () =>
      api<LiveGame[]>("games/live")
        .then((g) => alive && setGames(g))
        .catch(() => undefined);
    void load();
    const timer = setInterval(load, REFRESH_MS);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [ready]);

  return (
    <div className="page narrow">
      <h1 className="pageTitle">{t.watch.title}</h1>
      <p className="muted">{t.watch.intro}</p>
      <p className="muted small watchNote">
        <IconEye size={14} /> {t.watch.delayNote}
      </p>
      {games === null ? (
        <Loader />
      ) : games.length === 0 ? (
        <div className="card center stack">
          <p className="muted">{t.watch.empty}</p>
          <Link className="btn primary" href="/play">
            {t.watch.playOne}
          </Link>
        </div>
      ) : (
        <ul className="liveList">
          {games.map((g) => (
            <li key={g.id}>
              <Link href={`/game/${g.id}`} className="liveGame card">
                <span className="livePlayers">
                  <Who p={g.players[0]} side={1} />
                  <Who p={g.players[1]} side={2} />
                </span>
                <span className="liveMeta">
                  <b>{g.timeControl ?? "—"}</b>
                  <small className="muted">
                    {t.common.timeClasses[g.timeClass] ?? g.timeClass} · {g.rated ? t.watch.rated : t.watch.casual}
                  </small>
                  {g.match && (
                    <small className="muted">
                      {g.match.round > 2 ? t.match.decider : t.match.round(g.match.round)} · {g.match.score[0]}–{g.match.score[1]}
                    </small>
                  )}
                  <small className="muted">{t.watch.moves(g.ply)}</small>
                  {g.spectators > 0 && (
                    <small className="muted" title={t.watch.spectators(g.spectators)}>
                      <IconEye size={12} /> {g.spectators}
                    </small>
                  )}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
