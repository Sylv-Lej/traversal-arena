"use client";

import { Loader } from "@/components/ui/Loader";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Flag } from "@/components/ui/Flag";
import { RankChip } from "@/components/ui/Rank";
import { api, type ApiError } from "@/lib/api";
import { TERRAINS } from "@/lib/game";
import { useT } from "@/lib/i18n/client";
import { playerName } from "@/lib/i18n/helpers";
import { useMe } from "@/lib/me";
import type { MatchView, PlayerCard } from "@/lib/types";

/** Match en direct : chargement, puis flux SSE ; on n'accepte que les versions plus récentes. */
function useMatch(id: string) {
  const { ready } = useMe();
  const t = useT();
  const tRef = useRef(t);
  tRef.current = t;
  const [m, setM] = useState<MatchView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [receivedAt, setReceivedAt] = useState(0);
  const version = useRef(0);

  const accept = useCallback((v: MatchView) => {
    if (v.version <= version.current) return;
    version.current = v.version;
    setM(v);
    setReceivedAt(performance.now());
  }, []);

  useEffect(() => {
    if (!ready) return;
    let closed = false;
    api<MatchView>(`matches/${id}`)
      .then((v) => !closed && accept(v))
      .catch((e: ApiError) => !closed && setError(e.status === 404 ? tRef.current.match.notFound : e.message));
    const es = new EventSource(`/api/matches/${id}/stream`);
    es.addEventListener("match", (ev) => {
      try {
        accept(JSON.parse((ev as MessageEvent).data));
      } catch {
        /* évènement illisible : on attend le suivant */
      }
    });
    return () => {
      closed = true;
      es.close();
    };
  }, [id, ready, accept]);

  const act = useCallback(
    async (verb: string, body?: unknown) => {
      setError(null);
      try {
        accept(await api<MatchView>(`matches/${id}/${verb}`, { method: "POST", body: body ?? {} }));
      } catch (e) {
        setError((e as Error).message);
      }
    },
    [id, accept],
  );

  return { m, error, receivedAt, act };
}

/** Secondes restantes du ban / choix en cours (décompte local entre deux évènements). */
function useCountdown(ms: number | null, receivedAt: number): number | null {
  const [now, setNow] = useState(() => performance.now());
  useEffect(() => {
    if (ms == null) return;
    const timer = setInterval(() => setNow(performance.now()), 250);
    return () => clearInterval(timer);
  }, [ms, receivedAt]);
  if (ms == null) return null;
  return Math.max(0, Math.ceil((ms - (now - receivedAt)) / 1000));
}

function Who({ p, side, score }: { p: PlayerCard | null; side: 1 | 2; score: number }) {
  const t = useT();
  return (
    <div className={`matchWho p${side}`}>
      <span className="matchName">
        <Flag code={p?.country} /> <strong>{p ? playerName(p, t) : "…"}</strong>
      </span>
      <span className="matchMeta">
        {p?.rank && <RankChip rank={p.rank} size={18} />}
        {p?.rating != null && !p.isBot && <span className="muted small">{p.rating}</span>}
      </span>
      <span className="matchScore">{score}</span>
    </div>
  );
}

export function MatchClient({ id }: { id: string }) {
  const t = useT();
  const router = useRouter();
  const { m, error, receivedAt, act } = useMatch(id);
  const left = useCountdown(m?.deadlineMs ?? null, receivedAt);
  const [copied, setCopied] = useState(false);

  // Une manche commence : tout le monde (joueurs et spectateurs) va sur la partie.
  const gameId = m?.status === "playing" ? m.currentGameId : null;
  useEffect(() => {
    if (gameId) router.replace(`/game/${gameId}`);
  }, [gameId, router]);

  if (!m) return <div className="page narrow">{error ? <p className="error">{error}</p> : <Loader page />}</div>;

  const nameOf = (idx: 1 | 2) => playerName(m.players[idx - 1], t) || "…";
  const mine = (idx: 1 | 2) => m.you.includes(idx);
  const cur = m.rounds[m.rounds.length - 1];
  const roundTitle = m.round > 2 ? t.match.decider : t.match.round(m.round);
  const myTurn = !!m.step && mine(m.step.by);
  const solo = m.you.length === 1;
  const won = solo && m.winner === m.you[0];
  const lost = solo && m.winner != null && m.winner !== m.you[0];
  const inviteUrl = typeof window !== "undefined" ? window.location.href : "";

  const mapState = (key: string) => {
    const ban = cur?.bans.find((b) => b.map === key);
    if (ban && m.status === "veto") return { kind: "banned", text: t.match.bannedBy(nameOf(ban.by)) };
    const playedIn = m.rounds.find((r) => r.pick === key && r.gameId);
    if (playedIn) return { kind: "played", text: t.match.playedRound(playedIn.round) };
    return { kind: m.available.includes(key) ? "open" : "off", text: "" };
  };

  return (
    <div className="page narrow matchPage">
      <h1 className="pageTitle">
        {t.match.title}
        {(m.status === "veto" || m.status === "playing") && <small className="muted"> · {roundTitle}</small>}
      </h1>

      <section className="card matchHead">
        <Who p={m.players[0]} side={1} score={m.score[0]} />
        <span className="matchVs">–</span>
        <Who p={m.players[1]} side={2} score={m.score[1]} />
      </section>

      {m.status === "waiting" && (
        <section className="card stack">
          <p>
            <span className="spinner" /> {t.match.waitingOpponent}
          </p>
          {m.you.length > 0 ? (
            <>
              <p className="muted small">{t.match.invite}</p>
              <div className="copyRow">
                <input readOnly value={inviteUrl} onFocus={(e) => e.currentTarget.select()} />
                <button
                  className="btn"
                  onClick={() => {
                    void navigator.clipboard?.writeText(inviteUrl);
                    setCopied(true);
                  }}
                >
                  {copied ? t.match.copied : t.match.copyLink}
                </button>
              </div>
              <button className="btn ghost" onClick={() => act("abort")}>
                {t.match.abort}
              </button>
            </>
          ) : (
            <button className="btn primary big" onClick={() => act("join")}>
              {t.match.join}
            </button>
          )}
        </section>
      )}

      {m.status === "veto" && m.step && (
        <section className="card stack">
          <div className={`vetoTurn ${myTurn ? "mine" : ""}`}>
            <strong>
              {myTurn
                ? m.step.action === "ban"
                  ? t.match.yourBan
                  : t.match.yourPick
                : m.step.action === "ban"
                  ? t.match.theyBan(nameOf(m.step.by))
                  : t.match.theyPick(nameOf(m.step.by))}
            </strong>
            {left != null && <span className={`vetoClock ${left <= 5 ? "low" : ""}`}>{t.match.timeLeft(left)}</span>}
          </div>
          <div className="mapGrid">
            {m.maps.map((key) => {
              const st = mapState(key);
              const clickable = myTurn && st.kind === "open";
              return (
                <button
                  key={key}
                  className={`mapCard ${st.kind} ${clickable ? "clickable" : ""} ${m.step?.action === "pick" ? "picking" : ""}`}
                  disabled={!clickable}
                  onClick={() => act("veto", { map: key })}
                >
                  <span className="swatch" style={{ background: `linear-gradient(135deg, ${TERRAINS[key].swatch.join(", ")})` }} />
                  <span className="mapText">
                    <strong>{t.common.terrains[key]?.name}</strong>
                    <small>{st.text || t.common.terrains[key]?.desc}</small>
                  </span>
                  {clickable && <span className="mapAction">{m.step?.action === "ban" ? t.match.ban : t.match.pick}</span>}
                </button>
              );
            })}
          </div>
          <p className="muted small">{t.match.timeoutHint}</p>
        </section>
      )}

      {m.status === "playing" && (
        <section className="card center">
          <p>{t.match.starting}</p>
          {m.currentGameId && (
            <Link className="btn primary" href={`/game/${m.currentGameId}`}>
              {m.you.length ? t.match.goToRound : t.match.watchRound}
            </Link>
          )}
        </section>
      )}

      {m.status === "finished" && (
        <section className="card center stack">
          <div className={`endTitle ${won ? "won" : lost ? "lost" : ""}`}>
            {m.winner == null ? t.match.draw : won ? t.match.victory : lost ? t.match.defeat : t.match.wins(nameOf(m.winner))}
          </div>
          <p className="matchFinal">
            {m.score[0]} – {m.score[1]}
          </p>
          {m.ratingChange && solo && (
            <p className={`delta ${m.ratingChange[m.you[0] - 1] >= 0 ? "up" : "down"}`}>
              {m.players[m.you[0] - 1]?.rating} ({m.ratingChange[m.you[0] - 1] >= 0 ? "+" : ""}
              {m.ratingChange[m.you[0] - 1]})
            </p>
          )}
          <Link className="btn primary big" href={m.mode === "bot" ? "/play?tab=bot" : m.mode === "local" ? "/play?tab=local" : "/play"}>
            {t.match.newMatch}
          </Link>
        </section>
      )}

      {m.status === "aborted" && (
        <section className="card center stack">
          <p>{t.match.aborted}</p>
          <Link className="btn" href="/play">
            {t.match.backToPlay}
          </Link>
        </section>
      )}

      {m.rounds.some((r) => r.gameId) && (
        <section className="card">
          <h3>{t.match.rounds}</h3>
          <ul className="roundList">
            {m.rounds
              .filter((r) => r.gameId)
              .map((r) => (
                <li key={r.round}>
                  <Link href={`/game/${r.gameId}`}>
                    <b>{r.round > 2 ? t.match.decider : t.match.roundLine(r.round)}</b> · {t.common.terrains[r.pick ?? ""]?.name} ·{" "}
                    <span className="muted">
                      {!r.done ? t.match.inProgress : r.winner ? t.match.wonBy(nameOf(r.winner as 1 | 2)) : t.match.roundDraw}
                    </span>
                  </Link>
                </li>
              ))}
          </ul>
        </section>
      )}

      <p className="muted small">{t.match.rules}</p>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
