"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { BoardPreview } from "@/components/board3d/BoardPreview";
import { botSkin } from "@/components/board3d/skins";
import { MapDraw } from "@/components/ui/MapDraw";
import { RankEmblem } from "@/components/ui/Rank";
import { Modal } from "@/components/ui/Modal";
import { IconBot, IconLink, IconPeople, IconPlay } from "@/components/ui/icons";
import { api } from "@/lib/api";
import { BOTS, GAME_TYPES, TERRAINS, type GameType } from "@/lib/game";
import { useT } from "@/lib/i18n/client";
import { rankLabel } from "@/lib/i18n/helpers";
import { useMe } from "@/lib/me";
import type { GameView, LobbyInfo, MatchView, Side } from "@/lib/types";

type Tab = "online" | "bot" | "local";
type Choice = GameType | "none"; // hors ligne : on peut aussi jouer sans pendule

/** Types de partie : Bullet, Classique, Tactique (+ « sans pendule » hors ligne). */
function TypePicker({
  value,
  onChange,
  offline,
  waiting,
}: {
  value: Choice;
  onChange: (c: Choice) => void;
  offline?: boolean;
  waiting?: Record<string, number>;
}) {
  const t = useT();
  const items: { key: Choice; clock: string }[] = [
    ...GAME_TYPES.map((g) => ({ key: g.type as Choice, clock: g.type === "tactic" ? "Bo2 · 2+0" : g.clock })),
    ...(offline ? [{ key: "none" as Choice, clock: "∞" }] : []),
  ];
  return (
    <div className="typeGrid">
      {items.map(({ key, clock }) => (
        <button key={key} className={`typeBtn ${value === key ? "on" : ""}`} onClick={() => onChange(key)}>
          <strong>{t.common.timeClasses[key === "none" ? "casual" : key]}</strong>
          <span className="typeClock">{clock}</span>
          <small>
            {t.common.typeDesc[key === "none" ? "casual" : key]}
            {waiting?.[key] ? ` · ${t.play.waiting(waiting[key])}` : ""}
          </small>
        </button>
      ))}
    </div>
  );
}

function TerrainPicker({ value, onChange }: { value: string; onChange: (t: string) => void }) {
  const tr = useT();
  return (
    <div className="terrainGrid">
      {Object.entries(TERRAINS).map(([key, t]) => (
        <button key={key} className={`terrainChip ${value === key ? "on" : ""}`} onClick={() => onChange(key)}>
          <span className="swatch" style={{ background: `linear-gradient(135deg, ${t.swatch.join(", ")})` }} />
          <span className="tName">{tr.common.terrains[key]?.name}</span>
          <small>{tr.common.terrains[key]?.desc}</small>
        </button>
      ))}
    </div>
  );
}

function SidePicker({ value, onChange }: { value: Side | null; onChange: (s: Side | null) => void }) {
  const t = useT();
  return (
    <div className="segmented">
      <button className={value === 1 ? "on" : ""} onClick={() => onChange(1)}>
        <span className="teamDot side1" /> {t.common.sides[1]}
      </button>
      <button className={value === null ? "on" : ""} onClick={() => onChange(null)}>
        {t.play.random}
      </button>
      <button className={value === 2 ? "on" : ""} onClick={() => onChange(2)}>
        <span className="teamDot side2" /> {t.common.sides[2]}
      </button>
    </div>
  );
}

/** Choix du terrain, sauf en tactique : les cartes s'y choisissent par bans. */
function TerrainOrMaps({ type, terrain, setTerrain }: { type: Choice; terrain: string; setTerrain: (t: string) => void }) {
  const t = useT();
  if (type === "tactic") return <p className="muted small">{t.play.tacticMaps}</p>;
  return (
    <>
      <h3>{t.play.terrain}</h3>
      <TerrainPicker value={terrain} onChange={setTerrain} />
    </>
  );
}

function PlayInner() {
  const t = useT();
  const router = useRouter();
  const params = useSearchParams();
  const { ready } = useMe();
  const [tab, setTab] = useState<Tab>((params.get("tab") as Tab) || "online");
  const [tc, setTc] = useState<GameType>("classic");
  const [rated, setRated] = useState(true); // en ligne : classée (carte au sort) ou non (au choix)
  const [terrain, setTerrain] = useState("random");
  const [bot, setBot] = useState(2);
  const [side, setSide] = useState<Side | null>(1);
  const [offType, setOffType] = useState<Choice>("none"); // bots et local
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [seeking, setSeeking] = useState<number | null>(null);
  const [draw, setDraw] = useState<{ gameId: string; map: string } | null>(null);
  const [lobby, setLobby] = useState<LobbyInfo | null>(null);
  const [tick, setTick] = useState(0);
  const poll = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const p = params.get("tab") as Tab | null;
    if (p) setTab(p);
  }, [params]);

  useEffect(() => {
    if (!ready) return;
    const load = () => api<LobbyInfo>("lobby").then(setLobby).catch(() => undefined);
    void load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [ready]);

  useEffect(() => () => {
    if (poll.current) clearInterval(poll.current);
  }, []);

  /** Partie simple, ou match si le type est Tactique. */
  async function create(kind: Choice, body: Record<string, unknown>) {
    setBusy(true);
    setError(null);
    try {
      if (kind === "tactic") {
        const m = await api<MatchView>("matches", {
          body: { mode: body.mode, botLevel: body.botLevel, side: body.side, rated: body.rated ?? true },
        });
        router.push(`/match/${m.id}`);
        return;
      }
      const g = await api<GameView>("games", { body: { ...body, type: kind === "none" ? undefined : kind } });
      router.push(`/game/${g.id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  async function seek() {
    setError(null);
    try {
      type Seek = { status: string; gameId?: string; matchId?: string };
      // Match tactique : les cartes s'y choisissent par bans. Partie simple : la carte a
      // été tirée au sort par le serveur, on anime ce tirage avant d'y aller.
      const go = async (r: Seek) => {
        if (r.matchId) return router.push(`/match/${r.matchId}`);
        if (!rated && terrain !== "random") return router.push(`/game/${r.gameId}`); // carte choisie : pas de tirage
        try {
          const g = await api<GameView>(`games/${r.gameId}`);
          setDraw({ gameId: r.gameId!, map: g.terrain.mode });
        } catch {
          router.push(`/game/${r.gameId}`);
        }
      };
      const body = { type: tc, rated, terrain: rated ? "random" : terrain };
      const r = await api<Seek>("lobby/seek", { body });
      if (r.status === "matched") return go(r);
      setSeeking(Date.now());
      poll.current = setInterval(async () => {
        setTick((n) => n + 1);
        try {
          const p = await api<Seek>("lobby/seek");
          if (p.status === "matched") {
            if (poll.current) clearInterval(poll.current);
            go(p);
          } else if (p.status === "idle") {
            // Recherche expirée côté serveur (onglet en veille…) : on la relance.
            await api("lobby/seek", { body });
          }
        } catch {
          /* on retente au prochain tour */
        }
      }, 1500);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function cancelSeek() {
    if (poll.current) clearInterval(poll.current);
    setSeeking(null);
    await api("lobby/seek", { method: "DELETE" }).catch(() => undefined);
  }

  const elapsed = seeking ? Math.floor((Date.now() - seeking) / 1000) : 0;

  return (
    <div className="page play">
      <div className="playGrid">
        <section className="playPreview">
          <BoardPreview
            key={tab === "online" && rated ? "online" : terrain}
            mode={(tab === "online" && rated) || terrain === "random" ? "highlands" : terrain}
            seed={11}
            className="board3d preview3d"
            // Onglet Bots : les pièces adverses portent l'habillage du bot choisi.
            skins={tab === "bot" ? { [side === 2 ? 1 : 2]: botSkin(bot) } : undefined}
          />
          <p className="muted center small">
            {tab === "bot"
              ? t.play.previewBot(t.common.bots[bot]?.name, t.common.sidesLower[side === 2 ? 1 : 2])
              : tab === "online" && rated
                ? t.play.randomMap
                : t.play.previewTerrain(t.common.terrains[terrain]?.name)}
          </p>
        </section>

        <section className="card playPanel">
          <div className="tabs big">
            <button className={tab === "online" ? "on" : ""} onClick={() => setTab("online")}>
              <IconPlay size={18} /> {t.play.tabs.online}
            </button>
            <button className={tab === "bot" ? "on" : ""} onClick={() => setTab("bot")}>
              <IconBot size={18} /> {t.play.tabs.bots}
            </button>
            <button className={tab === "local" ? "on" : ""} onClick={() => setTab("local")}>
              <IconPeople size={18} /> {t.play.tabs.local}
            </button>
          </div>

          {tab === "online" && (
            <div className="stack">
              <div className="segmented">
                <button className={rated ? "on" : ""} onClick={() => setRated(true)}>
                  {t.play.rated}
                </button>
                <button className={!rated ? "on" : ""} onClick={() => setRated(false)}>
                  {t.play.unrated}
                </button>
              </div>
              <p className="muted small">{rated ? t.play.ratedDesc : t.play.unratedDesc}</p>
              <h3>{t.play.timeControl}</h3>
              <TypePicker value={tc} onChange={(c) => setTc(c as GameType)} waiting={lobby?.seeking} />
              {tc === "tactic" ? (
                <p className="muted small">{t.play.tacticMaps}</p>
              ) : (
                !rated && <TerrainOrMaps type={tc} terrain={terrain} setTerrain={setTerrain} />
              )}
              <button className="btn primary huge" onClick={seek} disabled={!ready}>
                {t.play.play}
              </button>
              <button
                className="btn"
                disabled={busy || !ready}
                onClick={() =>
                  create(tc, { mode: "online", side: side ?? undefined, rated, terrain: rated ? "random" : terrain })
                }
              >
                <IconLink size={18} /> {t.play.challengeFriend}
              </button>
              {lobby && (
                <p className="muted small center">
                  {t.play.lobbyStats(lobby.online, lobby.playing)}
                </p>
              )}
            </div>
          )}

          {tab === "bot" && (
            <div className="stack">
              <h3>{t.play.opponent}</h3>
              <div className="botGrid">
                {BOTS.map((fallback) => {
                  // Classement en direct (/lobby) ; à défaut, la valeur mesurée au départ.
                  const live = lobby?.bots.find((x) => x.level === fallback.level);
                  const b = { ...fallback, rating: live?.rating ?? fallback.rating, rank: live?.rank ?? fallback.rank };
                  return (
                    <button key={b.level} className={`botCard ${bot === b.level ? "on" : ""}`} onClick={() => setBot(b.level)}>
                      <RankEmblem rank={b.rank} size={50} animated={false} />
                      <span className="botText">
                        <strong>
                          {t.common.bots[b.level]?.name} <small>{rankLabel(b.rank, t)} · ≈{b.rating}</small>
                        </strong>
                        <small>{t.common.bots[b.level]?.desc}</small>
                      </span>
                    </button>
                  );
                })}
              </div>
              <h3>{t.play.iPlay}</h3>
              <SidePicker value={side} onChange={setSide} />
              <h3>{t.play.timeControl}</h3>
              <TypePicker value={offType} onChange={setOffType} offline />
              <TerrainOrMaps type={offType} terrain={terrain} setTerrain={setTerrain} />
              <button
                className="btn primary huge"
                disabled={busy || !ready}
                onClick={() => create(offType, { mode: "bot", botLevel: bot, terrain, side: side ?? undefined })}
              >
                {t.play.playVs(t.common.bots[bot]?.name)}
              </button>
            </div>
          )}

          {tab === "local" && (
            <div className="stack">
              <p className="muted">{t.play.localIntro}</p>
              <h3>{t.play.timeControl}</h3>
              <TypePicker value={offType} onChange={setOffType} offline />
              <TerrainOrMaps type={offType} terrain={terrain} setTerrain={setTerrain} />
              <button
                className="btn primary huge"
                disabled={busy || !ready}
                onClick={() => create(offType, { mode: "local", terrain })}
              >
                {t.play.start}
              </button>
            </div>
          )}
          {error && <p className="error">{error}</p>}
        </section>
      </div>

      <Modal
        open={seeking !== null || draw !== null}
        onClose={draw ? undefined : cancelSeek}
        title={draw ? t.play.foundTitle : t.play.seekingTitle}
      >
        {draw ? (
          <div className="seekBox">
            <MapDraw target={draw.map} onDone={() => router.push(`/game/${draw.gameId}`)} />
          </div>
        ) : (
        <div className="seekBox" data-tick={tick}>
          <span className="spinner big" />
          <p>
            <b>{t.common.timeClasses[tc]}</b> · {rated ? t.play.rated : t.play.unrated}
            {!rated && tc !== "tactic" && terrain !== "random" ? ` · ${t.common.terrains[terrain]?.name}` : ""}
          </p>
          <p className="muted">
            {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")} — {t.play.seekTip}
          </p>
          <button className="btn" onClick={cancelSeek}>
            {t.common.actions.cancel}
          </button>
        </div>
        )}
      </Modal>
    </div>
  );
}

export default function PlayPage() {
  return (
    <Suspense>
      <PlayInner />
    </Suspense>
  );
}
