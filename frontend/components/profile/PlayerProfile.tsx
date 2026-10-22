"use client";

import { Loader } from "@/components/ui/Loader";
import { CLASSES } from "@/lib/game";
import { Flag } from "@/components/ui/Flag";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Avatar } from "@/components/ui/Shell";
import { RatingChart, type RatingPoint } from "@/components/ui/RatingChart";
import { RankCard } from "@/components/ui/Rank";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n/client";
import { botNameById, playerName, rankLabel } from "@/lib/i18n/helpers";
import type { GameSummary, Me } from "@/lib/types";


function RatingSection({ p }: { p: Me }) {
  const t = useT();
  // Cadence affichée par défaut : celle où le joueur a le plus joué.
  const best = CLASSES.reduce((a, c) => ((p.ratings[c]?.games ?? 0) > (p.ratings[a]?.games ?? 0) ? c : a), "classic");
  const [cls, setCls] = useState(best);
  const [points, setPoints] = useState<RatingPoint[] | null>(null);
  useEffect(() => {
    setPoints(null);
    api<RatingPoint[]>(`players/${p.id}/history?timeClass=${cls}`).then(setPoints).catch(() => setPoints([]));
  }, [p.id, cls]);
  const r = p.ratings[cls];
  const peak = points && points.length ? Math.max(points[0].before, ...points.map((x) => x.rating)) : null;

  return (
    <div className="card">
      <h2 className="cardTitle">{t.profile.ratingHistory}</h2>
      <div className="tabs">
        {CLASSES.map((c) => (
          <button key={c} className={cls === c ? "on" : ""} onClick={() => setCls(c)}>
            {t.common.timeClasses[c]}
          </button>
        ))}
      </div>
      <div className="statTiles">
        <div className="statTile">
          <span className="statLabel">{t.profile.currentRating}</span>
          <span className="statValue">{r ? `${r.rating}${r.provisional ? "?" : ""}` : "—"}</span>
          {r?.rank && <span className="statSub">{r.rank.placement ? t.profile.inPlacement : rankLabel(r.rank, t)}</span>}
        </div>
        <div className="statTile">
          <span className="statLabel">{t.profile.best}</span>
          <span className="statValue">{peak ?? "—"}</span>
        </div>
        <div className="statTile">
          <span className="statLabel">{t.profile.games}</span>
          <span className="statValue">{r?.games ?? 0}</span>
          {r && (
            <span className="statSub">{t.profile.wdl(r.wins, r.losses, r.draws)}</span>
          )}
        </div>
      </div>
      {points === null ? (
        <Loader />
      ) : points.length === 0 ? (
        <p className="muted">{t.profile.noRatedGames(t.common.timeClasses[cls].toLowerCase())}</p>
      ) : (
        <RatingChart points={points} />
      )}
    </div>
  );
}

/** Profil public d'un joueur : rangs, courbe de classement, parties en ligne. */
export function PlayerProfile({ id, children }: { id: string; children?: React.ReactNode }) {
  const t = useT();
  const [p, setP] = useState<(Me & { games: GameSummary[] }) | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    api<Me & { games: GameSummary[] }>(`players/${id}`).then(setP).catch((e) => setErr(e.message));
  }, [id]);

  if (err) return <div className="page narrow"><p className="error">{err}</p></div>;
  if (!p) return <div className="page narrow"><Loader page /></div>;
  const name = botNameById(p.id, t) ?? p.name;

  return (
    <div className="page narrow">
      <div className="card">
        <div className="profileHead">
          <Avatar name={name} size={72} />
          <div>
            <h1>
              <Flag code={p.country} size={22} /> {name}
            </h1>
            <Link className="small" href="/ranks">
              {t.profile.howRanksWork}
            </Link>
          </div>
        </div>
        <div className="rankCards">
          {CLASSES.map((c) => (
            <RankCard key={c} title={t.common.timeClasses[c]} rank={p.ratings[c]?.rank} />
          ))}
        </div>
      </div>
      <RatingSection p={p} />
      <div className="card">
        <h2 className="cardTitle">{t.profile.onlineGames}</h2>
        {p.games.length === 0 ? (
          <p className="muted">{t.profile.noOnlineGames}</p>
        ) : (
          <ul className="gameList">
            {p.games.map((g) => {
              const side = g.you[0];
              const opp = g.players[side === 1 ? 1 : 0];
              const res = !g.result ? "ongoing" : g.result.winner == null ? "draw" : g.result.winner === side ? "win" : "loss";
              return (
                <li key={g.id}>
                  <Link href={`/game/${g.id}`}>
                    <span className={`pill ${res === "win" ? "win" : res === "loss" ? "loss" : ""}`}>{t.profile.result[res]}</span>
                    <span className="grow">
                      <Flag code={opp?.country} /> {t.profile.vs(playerName(opp, t))}{" "}
                      <small className="muted">
                        · {t.common.terrains[g.terrain]?.name} · {g.timeControl ?? t.profile.noClock}
                        {g.result ? ` · ${t.common.reasons[g.result.reason] ?? ""}` : ""}
                      </small>
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      {children}
    </div>
  );
}
