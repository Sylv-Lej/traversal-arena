"use client";

import { Loader } from "@/components/ui/Loader";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Flag } from "@/components/ui/Flag";
import { RankChip } from "@/components/ui/Rank";
import { Avatar } from "@/components/ui/Shell";
import { api } from "@/lib/api";
import { arenaName, type ArenaRow, type MyBot } from "@/lib/arena";
import { useT } from "@/lib/i18n/client";
import { useMe } from "@/lib/me";

export default function Arena() {
  const t = useT();
  const { me, ready } = useMe();
  const [rows, setRows] = useState<ArenaRow[] | null>(null);
  const [mine, setMine] = useState<MyBot[]>([]);

  useEffect(() => {
    api<ArenaRow[]>("arena/leaderboard").then(setRows).catch(() => setRows([]));
  }, []);
  useEffect(() => {
    if (ready && me && !me.isGuest) api<MyBot[]>("arena/mine").then(setMine).catch(() => setMine([]));
  }, [ready, me]);

  const community = rows?.filter((r) => !r.house).length ?? 0;

  return (
    <div className="page narrow">
      <div className="arenaHead">
        <h1 className="pageTitle">{t.arena.title}</h1>
        <Link href="/arena/new" className="btn primary">
          {t.arena.create}
        </Link>
      </div>
      <p className="muted">{t.arena.intro}</p>

      {mine.length > 0 && (
        <div className="card">
          <h2 className="cardTitle">{t.arena.mine}</h2>
          <ul className="versionList">
            {mine.map((b) => (
              <li key={b.id}>
                <Link href={`/arena/bot/${b.id}`} className="botCell grow">
                  <span className="botName">{arenaName(b, t)}</span>
                </Link>
                <RankChip rank={b.tier} size={22} />
                <span className={`chip ${b.status}`}>{t.arena.status[b.status]}</span>
                <span className="muted small">{b.rating !== null ? b.rating : t.arena.noGames}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="card">
        <h2 className="cardTitle">{t.arena.leaderboard}</h2>
        {rows === null ? (
          <Loader />
        ) : (
          <>
            {community === 0 && (
              <p className="muted center">
                {t.arena.empty} <Link href="/arena/new">{t.arena.create}</Link>
              </p>
            )}
            <table className="table arenaTable">
              <thead>
                <tr>
                  <th className="colRank">#</th>
                  <th>{t.arena.bot}</th>
                  <th className="colDiv">{t.arena.division}</th>
                  <th className="num colRating">{t.arena.rating}</th>
                  <th className="num colGames hideSm">{t.arena.games}</th>
                  <th className="num colWdl hideSm">{t.arena.wdl}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const name = arenaName(r, t);
                  return (
                    <tr key={r.id}>
                      <td className={`rank r${r.rank ?? 0}`}>{r.rank ?? "–"}</td>
                      <td>
                        <Link href={`/arena/bot/${r.id}`} className="botCell">
                          <Avatar name={r.name} size={26} />
                          <span className="botName">
                            {name}
                            {r.house ? (
                              <span className="botSub" title={t.arena.houseHint}>
                                {t.arena.house}
                              </span>
                            ) : (
                              r.author && (
                                <span className="botSub">
                                  {t.arena.by} <Flag code={r.author.country} /> {r.author.name}
                                </span>
                              )
                            )}
                          </span>
                        </Link>
                      </td>
                      <td className="colDiv">
                        <RankChip rank={r.tier} size={24} />
                      </td>
                      <td className="num">
                        {r.rating === null ? (
                          <span className="muted small">{t.arena.noGames}</span>
                        ) : (
                          <span title={r.provisional ? t.arena.provisional : undefined}>
                            <b>{r.rating}</b>
                            {r.provisional ? "?" : ""}
                            <span className="botSub">{t.arena.margin(r.margin ?? 0)}</span>
                          </span>
                        )}
                      </td>
                      <td className="num hideSm">{r.games}</td>
                      <td className="num hideSm muted">
                        {r.wins} / {r.losses} / {r.draws}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </>
        )}
      </div>

      <div className="card">
        <h2 className="cardTitle">{t.arena.how.title}</h2>
        <ol className="steps">
          {t.arena.how.steps.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ol>
      </div>
    </div>
  );
}
