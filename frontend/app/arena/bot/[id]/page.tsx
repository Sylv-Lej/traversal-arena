"use client";

import { Loader } from "@/components/ui/Loader";
import Link from "next/link";
import { use, useEffect, useState } from "react";
import { Flag } from "@/components/ui/Flag";
import { RankChip } from "@/components/ui/Rank";
import { Avatar } from "@/components/ui/Shell";
import { api, ApiError } from "@/lib/api";
import { arenaName, type ArenaBot, type ArenaInfo } from "@/lib/arena";
import { useT } from "@/lib/i18n/client";
import { useMe } from "@/lib/me";

export default function ArenaBotPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const t = useT();
  const { me } = useMe();
  const [bot, setBot] = useState<ArenaBot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Parties consultables ? Sinon la liste ne montre que les résultats, sans lien.
  const [replays, setReplays] = useState(false);
  useEffect(() => {
    api<ArenaInfo>("arena/info").then((i) => setReplays(i.replays)).catch(() => setReplays(false));
  }, []);

  useEffect(() => {
    setBot(null);
    setError(null);
    api<ArenaBot>(`arena/bots/${id}`)
      .then(setBot)
      .catch((e) => setError(e instanceof ApiError ? e.message : t.arena.notFound));
  }, [id, t]);

  if (error) return <div className="page narrow"><p className="error">{error}</p></div>;
  if (!bot) return <div className="page narrow"><Loader page /></div>;

  const mine = !!me && bot.author?.id === me.id;
  /** Une ligne de « Dernières parties » (un lien vers la partie si elle est consultable). */
  const row = (g: ArenaBot["recent"][number]) => (
    <>
      <span className={`pill ${g.result}`}>{t.arena.result[g.result]}</span>
      <span className="grow">
        {t.arena.vs} <b>{arenaName(g.opponent, t)}</b>
        <span className="botSub">
          {t.common.terrains[g.terrain]?.name ?? g.terrain} · {t.arena.plies(g.ply)}
          {g.reason ? ` · ${t.common.reasons[g.reason] ?? g.reason}` : ""}
        </span>
      </span>
    </>
  );
  const retire = async () => {
    if (!window.confirm(t.arena.retireConfirm)) return;
    setBusy(true);
    try {
      setBot(await api<ArenaBot>(`arena/bots/${bot.id}/retire`, { body: {} }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t.common.errors.generic);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page narrow">
      <p className="small">
        <Link href="/arena">← {t.arena.title}</Link>
      </p>
      <div className="card">
        <div className="arenaHead">
          <div className="botCell">
            <Avatar name={bot.name} size={40} />
            <div className="botName">
              <h1 className="cardTitle" style={{ margin: 0 }}>
                {arenaName(bot, t)}
              </h1>
              {bot.house ? (
                <span className="botSub">{t.arena.houseHint}</span>
              ) : (
                bot.author && (
                  <span className="botSub">
                    {t.arena.by} <Link href={`/player/${bot.author.id}`}>{bot.author.name}</Link>{" "}
                    <Flag code={bot.author.country} />
                  </span>
                )
              )}
            </div>
          </div>
          <span className={`chip ${bot.house ? "house" : bot.status}`}>
            {bot.house ? t.arena.house : t.arena.status[bot.status]}
          </span>
        </div>
      </div>

      {bot.status === "pending" && <p className="muted">{t.arena.pendingNote}</p>}
      {bot.status === "rejected" && (
        <p className="error">
          {t.arena.rejectedNote} {bot.error}
        </p>
      )}

      <div className="card">
        <div className="statTiles">
          <div className="statTile">
            <span className="statLabel">{t.arena.rating}</span>
            <span className="statValue">{bot.rating === null ? "—" : `${bot.rating}${bot.provisional ? "?" : ""}`}</span>
            {bot.margin !== null && <span className="statSub">{t.arena.margin(bot.margin)}</span>}
            {bot.tier && (
              <span className="statSub">
                <RankChip rank={bot.tier} size={22} />
              </span>
            )}
          </div>
          <div className="statTile">
            <span className="statLabel">{t.arena.games}</span>
            <span className="statValue">{bot.games}</span>
            {!!bot.queued && <span className="statSub">{t.arena.queued(bot.queued)}</span>}
          </div>
          <div className="statTile">
            <span className="statLabel">{t.arena.wdl}</span>
            <span className="statValue" style={{ fontSize: "clamp(16px, 4vw, 20px)" }}>
              {bot.wins} / {bot.losses} / {bot.draws}
            </span>
          </div>
        </div>
        {bot.sha256 && (
          <p className="muted small">
            {t.arena.sha} <span className="mono">{bot.sha256.slice(0, 16)}…</span>
            {bot.size ? ` · ${t.arena.size(Math.ceil(bot.size / 1024))}` : ""}
          </p>
        )}
        {mine && (
          <div className="actions">
            <Link href={`/arena/new?update=${bot.versions[0]?.id ?? bot.id}`} className="btn small">
              {t.arena.update}
            </Link>
            {(bot.status === "active" || bot.status === "pending") && (
              <button className="btn danger small" onClick={retire} disabled={busy}>
                {t.arena.retire}
              </button>
            )}
          </div>
        )}
      </div>

      <div className="card">
        <h2 className="cardTitle">{t.arena.recent}</h2>
        {bot.recent.length === 0 ? (
          <p className="muted">{t.arena.noRecent}</p>
        ) : (
          <ul className="gameList">
            {bot.recent.map((g) => (
              <li key={g.id}>
                {replays ? (
                  <Link href={`/game/${g.id}`}>{row(g)}</Link>
                ) : (
                  <div className="gameRow">{row(g)}</div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {bot.versions.length > 1 && (
        <div className="card">
          <h2 className="cardTitle">{t.arena.versions}</h2>
          <ul className="versionList">
            {bot.versions.map((v) => (
              <li key={v.id}>
                <Link href={`/arena/bot/${v.id}`} className="grow">
                  {t.arena.version(v.version)}
                </Link>
                <span className={`chip ${v.status}`}>{t.arena.status[v.status]}</span>
                <span className="muted small">
                  {v.rating ?? "—"} · {v.games} {t.arena.games.toLowerCase()}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
