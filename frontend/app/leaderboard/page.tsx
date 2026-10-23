"use client";

import { Loader } from "@/components/ui/Loader";
import { CLASSES } from "@/lib/game";
import { Flag } from "@/components/ui/Flag";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Avatar } from "@/components/ui/Shell";
import { RankChip } from "@/components/ui/Rank";
import type { Rank } from "@/lib/types";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n/client";
import { botNameById } from "@/lib/i18n/helpers";

interface Row {
  rank: number;
  id: string;
  name: string;
  country: string | null;
  rating: number;
  games: number;
  wins: number;
  losses: number;
  draws: number;
  provisional: boolean;
  tier: Rank | null;
}


type PuzzleRow = { rank: number; id: string; name: string; country: string | null; rating: number; games: number; tier: Rank };

export default function Leaderboard() {
  const t = useT();
  const [cls, setCls] = useState<string>("classic");
  const [rows, setRows] = useState<Row[] | null>(null);
  const [puzzleRows, setPuzzleRows] = useState<PuzzleRow[] | null>(null);
  useEffect(() => {
    setRows(null);
    setPuzzleRows(null);
    if (cls === "puzzle") api<PuzzleRow[]>("puzzles/leaderboard").then(setPuzzleRows).catch(() => setPuzzleRows([]));
    else api<Row[]>(`leaderboard?timeClass=${cls}`).then(setRows).catch(() => setRows([]));
  }, [cls]);

  return (
    <div className="page narrow">
      <h1 className="pageTitle">{t.leaderboard.title}</h1>
      <p className="muted">
        {t.leaderboard.intro} <Link href="/ranks">{t.leaderboard.howRanksWork}</Link>
        {" · "}
        <Link href="/arena">{t.arena.title} →</Link>
      </p>
      <div className="card">
        <div className="tabs">
          {CLASSES.map((c) => (
            <button key={c} className={cls === c ? "on" : ""} onClick={() => setCls(c)}>
              {t.common.timeClasses[c]}
            </button>
          ))}
          <button className={cls === "puzzle" ? "on" : ""} onClick={() => setCls("puzzle")}>
            {t.common.nav.puzzles}
          </button>
        </div>
        {cls === "puzzle" ? (
          puzzleRows === null ? (
            <Loader />
          ) : puzzleRows.length === 0 ? (
            <p className="muted center">
              {t.puzzles.noScores} <Link href="/puzzles">{t.puzzles.title}</Link>
            </p>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>{t.leaderboard.player}</th>
                  <th>{t.leaderboard.rank}</th>
                  <th className="num">{t.puzzles.rating}</th>
                </tr>
              </thead>
              <tbody>
                {puzzleRows.map((r) => (
                  <tr key={r.id}>
                    <td className={`rank r${r.rank}`}>{r.rank}</td>
                    <td>
                      <Link href={`/player/${r.id}`} className="playerCell">
                        <Avatar name={r.name} size={26} />
                        {r.name}
                        <Flag code={r.country} />
                      </Link>
                    </td>
                    <td>
                      <RankChip rank={r.tier} size={26} />
                    </td>
                    <td className="num">
                      <b>{r.rating}</b>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        ) : rows === null ? (
          <Loader />
        ) : rows.length === 0 ? (
          <p className="muted center">
            {t.leaderboard.empty(t.common.timeClasses[cls].toLowerCase())}{" "}
            <Link href="/play">{t.leaderboard.playRated}</Link>
            {t.leaderboard.emptyAfter}
          </p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>#</th>
                <th>{t.leaderboard.player}</th>
                <th>{t.leaderboard.rank}</th>
                <th className="num">{t.leaderboard.rating}</th>
                <th className="num hideSm">{t.leaderboard.wdl}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const name = botNameById(r.id, t) ?? r.name;
                return (
                  <tr key={r.id}>
                    <td className={`rank r${r.rank}`}>{r.rank}</td>
                    <td>
                      <Link href={`/player/${r.id}`} className="playerCell">
                        <Avatar name={name} size={26} />
                        {name}
                        <Flag code={r.country} />
                      </Link>
                    </td>
                    <td>
                      <RankChip rank={r.tier} size={26} />
                    </td>
                    <td className="num">
                      <b>{r.rating}</b>
                      {r.provisional ? "?" : ""}
                    </td>
                    <td className="num hideSm muted">
                      {r.wins} / {r.losses} / {r.draws}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
