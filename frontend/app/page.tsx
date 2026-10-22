"use client";

// Accueil centré sur l'arène des bots : une vraie partie de l'arène rejouée sur le plateau.
// L'ancien accueil (jouer en ligne, puzzles…) est gardé dans `components/home/ClassicHome`.

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArenaReplay } from "@/components/home/ArenaReplay";
import { RankChip } from "@/components/ui/Rank";
import { Avatar } from "@/components/ui/Shell";
import { IconArena, IconBook, IconLink, IconTrophy } from "@/components/ui/icons";
import { api } from "@/lib/api";
import { arenaName, type ArenaRow } from "@/lib/arena";
import { useT } from "@/lib/i18n/client";

const SDK_REPO = "https://github.com/Sylv-Lej/traversal-rust-sdk";
const TOP = 5;

export default function Home() {
  const t = useT();
  const h = t.arena.home;
  const [rows, setRows] = useState<ArenaRow[] | null>(null);
  useEffect(() => {
    api<ArenaRow[]>("arena/leaderboard").then(setRows).catch(() => setRows([]));
  }, []);
  const ranked = rows?.filter((r) => r.rank !== null).slice(0, TOP) ?? [];
  const community = rows?.filter((r) => !r.house).length ?? 0;

  return (
    <div className="page home">
      <section className="hero">
        <div className="heroBoard">
          <ArenaReplay />
        </div>
        <div className="heroSide">
          <h1>
            {h.title}
            <br />
            <span className="accent">{h.accent}</span>
          </h1>
          <p className="lead">{h.lead}</p>
          <div className="bigButtons">
            <Link href="/arena/new" className="bigBtn primary">
              <IconArena size={34} />
              <span>
                <strong>{t.arena.create}</strong>
                <small>{h.createSub}</small>
              </span>
            </Link>
            <Link href="/arena" className="bigBtn">
              <IconTrophy size={34} />
              <span>
                <strong>{h.board}</strong>
                <small>{h.boardSub(community)}</small>
              </span>
            </Link>
            <Link href="/rules" className="bigBtn">
              <IconBook size={34} />
              <span>
                <strong>{h.rules}</strong>
                <small>{h.rulesSub}</small>
              </span>
            </Link>
            <a href={SDK_REPO} target="_blank" rel="noreferrer" className="bigBtn">
              <IconLink size={34} />
              <span>
                <strong>{h.sdk}</strong>
                <small>{h.sdkSub}</small>
              </span>
            </a>
          </div>
        </div>
      </section>

      {ranked.length > 0 && (
        <section className="card">
          <h2 className="cardTitle">{h.top}</h2>
          <ul className="gameList">
            {ranked.map((r) => (
              <li key={r.id}>
                <Link href={`/arena/bot/${r.id}`}>
                  <span className={`rank r${r.rank}`}>{r.rank}</span>
                  <Avatar name={r.name} size={26} />
                  <span className="grow botName">
                    {arenaName(r, t)}
                    <span className="botSub">{r.house ? t.arena.house : r.author ? `${t.arena.by} ${r.author.name}` : ""}</span>
                  </span>
                  <RankChip rank={r.tier} size={24} />
                  <b>{r.rating}</b>
                </Link>
              </li>
            ))}
          </ul>
          <p className="small">
            <Link href="/arena">{h.fullBoard} →</Link>
          </p>
        </section>
      )}
    </div>
  );
}
