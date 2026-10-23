"use client";

import { useFullSite } from "@/components/ui/Shell";
import { Flag } from "@/components/ui/Flag";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useGame } from "@/lib/useGame";
import { useAnalysis } from "@/lib/useAnalysis";
import { PIECES } from "@/lib/game";
import { useT } from "@/lib/i18n/client";
import type { Dict } from "@/lib/i18n/dict";
import { playerName, rankLabel } from "@/lib/i18n/helpers";
import { sounds } from "@/lib/sound";
import { updateSettings, useSettings } from "@/lib/settings";
import { NO_ANNOTATIONS, hasAnnotations, toggleAnnotation, type Annotations } from "@/lib/annotations";
import type { LegalMove, MoveClass, MoveRecord, Position, Side } from "@/lib/types";
import { PlayerBar } from "./PlayerBar";
import { MoveList } from "./MoveList";
import { CombatCard } from "./CombatCard";
import { AnalysisPanel, EvalBar } from "./AnalysisPanel";
import { Modal } from "@/components/ui/Modal";
import { LpBar, RankEmblem, rankValue } from "@/components/ui/Rank";
import type { Rank } from "@/lib/types";
import {
  IconCenter,
  IconClose,
  IconPen,
  IconEye,
  IconFirst,
  IconFlag,
  IconFlip,
  IconHandshake,
  IconLast,
  IconLink,
  IconNext,
  IconPrev,
  PieceIcon,
} from "@/components/ui/icons";

import type { CameraView } from "@/components/board3d/Board3D";
import { botSkin, type SkinId } from "@/components/board3d/skins";

const Board3D = dynamic(() => import("@/components/board3d/Board3D"), {
  ssr: false,
  loading: () => <BoardLoading />,
});

const Board2D = dynamic(() => import("@/components/board2d/Board2D"), {
  ssr: false,
  loading: () => <BoardLoading />,
});

function BoardLoading() {
  const t = useT();
  return <div className="board3d loadingBoard">{t.game.loadingBoard}</div>;
}

/** Résultat de rang en fin de partie classée : PL gagnés/perdus, promotion, révélation. */
function RankResult({ before, after, delta }: { before: Rank; after: Rank; delta: number }) {
  const t = useT();
  const afterLabel = rankLabel(after, t);
  const lp = Math.round(delta * 2); // 50 points de classement = 100 PL
  const revealed = !!before.placement && !after.placement;
  const up = rankValue(after) > rankValue(before);
  const down = rankValue(after) < rankValue(before);
  const banner = revealed
    ? t.game.rankRevealed(afterLabel)
    : after.placement
      ? t.common.placement(after.placement.played, after.placement.total)
      : up
        ? t.game.promotion(afterLabel)
        : down
          ? t.game.relegation(afterLabel)
          : null;
  return (
    <div className="rankResult">
      {banner && <div className={`rankBanner ${revealed ? "reveal" : up ? "up" : down ? "down" : ""}`}>{banner}</div>}
      <div className="rankLine">
        {(up || down) && !revealed && (
          <>
            <RankEmblem rank={before} size={46} animated={false} />
            <span className="arrow">→</span>
          </>
        )}
        <span className={up || revealed ? "promoGlow" : ""}>
          <RankEmblem rank={after} size={up || revealed ? 86 : 64} />
        </span>
      </div>
      {!after.placement && (
        <>
          <b>{afterLabel}</b>
          {after.division ? (
            <LpBar from={up || revealed ? 0 : down ? 100 : before.lp} to={after.lp} />
          ) : (
            <span className="small">
              {after.lp} {t.common.lpShort}
            </span>
          )}
        </>
      )}
      {!revealed && !after.placement && (
        <span className={`lpDelta ${lp >= 0 ? "up" : "down"}`}>
          {lp >= 0 ? "+" : ""}
          {lp} {t.common.lpShort}
        </span>
      )}
    </div>
  );
}

// Libellés et infobulles : `t.game.cameraViews[key]`.
const CAMERA_VIEWS: CameraView[] = ["default", "top", "left", "right", "low"];

function reasonText(reason: string, winner: Side | null, t: Dict): string {
  if (reason === "score" && winner === null) return t.game.scoreTie;
  return t.common.reasons[reason] ?? reason;
}

function useConfirm(timeout = 3000) {
  const [armed, setArmed] = useState<string | null>(null);
  useEffect(() => {
    if (!armed) return;
    const timer = setTimeout(() => setArmed(null), timeout);
    return () => clearTimeout(timer);
  }, [armed, timeout]);
  return {
    armed,
    ask: (key: string, run: () => void) => {
      if (armed === key) {
        setArmed(null);
        run();
      } else setArmed(key);
    },
  };
}

export function GameClient({ id }: { id: string }) {
  const t = useT();
  // Hors site complet (FULL_SITE), « nouvelle partie » ramène à l'arène.
  const fullSite = useFullSite();
  const newGame = fullSite ? { href: "/play", label: t.game.newGame } : { href: "/arena", label: t.arena.title };
  const router = useRouter();
  const g = useGame(id);
  const { view } = g;
  const settings = useSettings();
  const [flip, setFlip] = useState(false);
  const [camView, setCamView] = useState<CameraView>("default");
  const [recenter, setRecenter] = useState(0);
  const [viewPly, setViewPly] = useState<number | null>(null);
  const [positions, setPositions] = useState<Position[] | null>(null);
  const [preview, setPreview] = useState<LegalMove | null>(null);
  const [tab, setTab] = useState<"moves" | "info" | "review">("moves");
  const [showHint, setShowHint] = useState(true);
  // Flèches et cercles (analyse, spectateur) : effacés à chaque changement de position.
  const [ann, setAnn] = useState<Annotations>(NO_ANNOTATIONS);
  const [drawMode, setDrawMode] = useState(false);
  const finished = view?.status === "finished" && (view?.moves.length ?? 0) > 0;
  const review = useAnalysis(id, finished);
  const marks = useMemo(() => {
    const out: Record<number, MoveClass> = {};
    review.analysis?.moves.forEach((m) => (out[m.ply] = m.class));
    return out;
  }, [review.analysis]);
  // Partie importée : on vient pour son bilan.
  const imported = view?.mode === "import";
  useEffect(() => {
    if (imported) setTab("review");
  }, [imported]);
  const startReview = useCallback(() => {
    setTab("review");
    void review.start();
  }, [review]);
  const [showEnd, setShowEnd] = useState(false);
  const [nextIn, setNextIn] = useState<number | null>(null);
  const [copied, setCopied] = useState(false);
  const confirm = useConfirm();
  const seenMoves = useRef<number | null>(null);
  const seenStatus = useRef<string | null>(null);

  // --- Sons + modale de fin, sur les changements réels de la partie ------------------
  useEffect(() => {
    if (!view) return;
    const n = view.moves.length;
    if (seenMoves.current !== null && n > seenMoves.current && settings.sound) {
      const last = view.moves[n - 1];
      if (last.kind === "exit") sounds.exit();
      else if (last.kind === "attack") sounds.capture();
      else sounds.move();
    }
    seenMoves.current = n;
    if (seenStatus.current === "active" && view.status === "finished") {
      setShowEnd(true);
      if (settings.sound) setTimeout(sounds.end, 600);
    }
    if (seenStatus.current === "waiting" && view.status === "active" && settings.sound) sounds.notify();
    seenStatus.current = view.status;
  }, [view, settings.sound]);

  // Revanche acceptée (par nous ou l'adversaire) : on file vers la nouvelle partie.
  useEffect(() => {
    if (view?.rematchId) router.push(`/game/${view.rematchId}`);
  }, [view?.rematchId, router]);

  // Match tactique : manche terminée, match pas fini -> on enchaîne (bans de la suivante).
  const matchId = view?.match?.id;
  const roundOver = !!view?.match && (view.status === "finished" || view.status === "aborted");
  const matchGoesOn = roundOver && (view!.match!.status === "veto" || view!.match!.status === "playing");
  useEffect(() => {
    if (!matchGoesOn || !matchId) return;
    setNextIn(6);
    const timer = setInterval(() => setNextIn((n) => (n == null ? n : n - 1)), 1000);
    return () => clearInterval(timer);
  }, [matchGoesOn, matchId]);
  useEffect(() => {
    if (nextIn !== null && nextIn <= 0 && matchId && fullSite) router.push(`/match/${matchId}`);
  }, [nextIn, matchId, router, fullSite]);

  // Historique (pour la revue des coups), chargé à la demande.
  const moveCount = view?.moves.length ?? 0;
  useEffect(() => {
    if (viewPly === null) return;
    if (positions && positions.length === moveCount + 1) return;
    api<{ positions: Position[] }>(`games/${id}/history`).then((h) => setPositions(h.positions)).catch(() => undefined);
  }, [viewPly, moveCount, id, positions]);

  const goto = useCallback(
    (ply: number | null) => {
      if (ply === null || ply >= moveCount) setViewPly(null);
      else setViewPly(Math.max(0, ply));
    },
    [moveCount],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === "INPUT") return;
      if (e.key === "ArrowLeft") goto((viewPly ?? moveCount) - 1);
      if (e.key === "ArrowRight") goto((viewPly ?? moveCount) + 1);
      if (e.key === "f") setFlip((f) => !f);
      if (e.key === "d") updateSettings({ board2d: !settings.board2d });
      const n = Number(e.key);
      if (n >= 1 && n <= CAMERA_VIEWS.length) {
        setCamView(CAMERA_VIEWS[n - 1]);
        setRecenter((r) => r + 1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [goto, viewPly, moveCount, settings.board2d]);

  const reviewing = viewPly !== null && positions !== null && positions[viewPly] !== undefined;
  const shownPos = viewPly ?? moveCount;
  useEffect(() => setAnn(NO_ANNOTATIONS), [shownPos]);
  const position = reviewing ? positions![viewPly!] : view?.position;
  const lastMove = view ? (reviewing ? (viewPly! > 0 ? view.moves[viewPly! - 1] : null) : view.moves[view.moves.length - 1] ?? null) : null;

  // Capture par la charge de l'Avant-garde (+1, R7.5) : peu intuitive (une Force 2 qui
  // prend une Force 3), on l'annonce quelques secondes sur le plateau. Pas au chargement.
  const [chargeFlash, setChargeFlash] = useState<MoveRecord | null>(null);
  const seenPly = useRef<number | null>(null);
  const shownPly = lastMove?.ply ?? 0;
  const loaded = !!view;
  useEffect(() => {
    if (!loaded) return;
    if (seenPly.current === null || seenPly.current === shownPly) {
      seenPly.current = shownPly;
      return;
    }
    seenPly.current = shownPly;
    const charged = lastMove?.kind === "attack" && lastMove.combat?.attackTerms.some((x) => x.label === "charge");
    setChargeFlash(charged ? lastMove : null);
  }, [loaded, shownPly, lastMove]);
  useEffect(() => {
    if (!chargeFlash) return;
    const timer = setTimeout(() => setChargeFlash(null), 3500);
    return () => clearTimeout(timer);
  }, [chargeFlash]);

  const mySides = view?.you ?? [];
  // Spectateur d'une partie en ligne : le joueur le mieux classé en bas, comme à la télé.
  const bestSide: Side = (view?.players[1]?.rating ?? 0) > (view?.players[0]?.rating ?? 0) ? 2 : 1;
  const baseSide: Side = mySides.length === 1 ? mySides[0] : mySides.length === 0 && view?.mode === "online" ? bestSide : 1;
  const orientation: Side = flip ? (baseSide === 1 ? 2 : 1) : baseSide;
  const bottom = orientation;
  const top: Side = orientation === 1 ? 2 : 1;

  const legal = useMemo(() => (reviewing ? [] : view?.legalMoves ?? []), [reviewing, view?.legalMoves]);
  // Le relief ne change jamais pendant une partie : on garde la même référence pour que
  // la scène 3D ne recalcule ni terrain ni positions à chaque mise à jour.
  const terrainKey = view ? `${view.id}:${view.terrain.seed}` : "";
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const heights = useMemo(() => view?.terrain.heights ?? [], [terrainKey]);
  const onlyPass = legal.length === 1 && legal[0].kind === "pass";
  const myTurn = !!view && view.status === "active" && mySides.includes(view.position.toMove);

  if (g.error && !view) {
    return (
      <div className="page narrow">
        <div className="card center">
          <h1>{t.game.oops}</h1>
          <p>{g.error}</p>
          <Link className="btn primary" href={newGame.href}>
            {newGame.label}
          </Link>
        </div>
      </div>
    );
  }
  if (!view || !position) {
    return (
      <div className="gamePage">
        <section className="boardCol">
          <div className="board3d loadingBoard">{t.game.loadingGame}</div>
        </section>
      </div>
    );
  }

  const isPlayer = mySides.length > 0;
  // Annotations comme sur chess.com, hors partie en cours : analyse, revue des coups, spectateur.
  const annotate = !isPlayer || reviewing || view.status === "finished" || view.status === "aborted";
  const Board = settings.board2d ? Board2D : Board3D;
  // Contre un bot, ses pièces portent l'habillage de son niveau.
  const botSkins: Partial<Record<Side, SkinId>> | undefined =
    view.mode === "bot" ? { [view.players[0]?.isBot ? 1 : 2]: botSkin(view.botLevel) } : undefined;
  const curPly = viewPly ?? moveCount;
  const analysis = review.analysis;
  const curAnalyzed = analysis && curPly > 0 ? analysis.moves[curPly - 1] : null;
  const hint =
    analysis && showHint && curAnalyzed?.best
      ? { path: curAnalyzed.best.path, kind: curAnalyzed.best.kind, owner: curAnalyzed.side }
      : null;
  const curEval = analysis ? (curAnalyzed ? curAnalyzed.eval : analysis.initialEval) : null;
  // En local, les deux camps sont le même compte : on les nomme par leur couleur.
  const playerOf = (s: Side) => (view.mode === "local" ? null : view.players[s - 1]);
  const nameOf = (s: Side) => (playerOf(s) ? playerName(playerOf(s), t) : t.common.sides[s]);
  const toMove = position.toMove;
  const clock = view.clock;
  const botSide = view.mode === "bot" ? (view.players[0]?.isBot ? 1 : 2) : null;
  const botThinking = view.status === "active" && botSide === view.position.toMove;
  const capturedBy = (s: Side) => position.captured.filter((p) => p.owner !== s);
  const result = view.result;
  const winnerName = result?.winner ? nameOf(result.winner) : null;
  const youWon = result?.winner != null && mySides.length === 1 && mySides[0] === result.winner;
  const youLost = result?.winner != null && mySides.length === 1 && mySides[0] !== result.winner;
  const inviteUrl = typeof window !== "undefined" ? `${window.location.origin}/game/${view.id}` : "";
  const canAbort = isPlayer && ((view.status === "active" && view.position.ply < 2 && view.mode !== "local") || view.status === "waiting");

  const bar = (s: Side) => (
    <PlayerBar
      side={s}
      player={playerOf(s)}
      isYou={mySides.length === 1 && mySides[0] === s}
      toMove={view.status === "active" && toMove === s && !reviewing}
      score={position.scores[s - 1]}
      capturedByThem={capturedBy(s)}
      clockMs={clock ? clock.remaining[s - 1] : null}
      clockRunning={!!clock && clock.running === s}
      receivedAt={g.receivedAt}
      ratingDelta={view.ratingChange ? view.ratingChange[s - 1] : null}
      waiting={view.status === "waiting"}
    />
  );

  // Manche d'un match tactique : score du match et suite.
  const mb = view.match;
  const matchName = (pid: string | null) => {
    const p = view.players.find((x) => x && x.id === pid);
    return p ? playerName(p, t) : "";
  };
  const matchInfo = mb ? (
    <div className="matchBar">
      <span>
        <b>{t.match.matchBar(mb.round > 2 ? t.match.decider : t.match.round(mb.round))}</b>
        {view.mode !== "local" && (
          <>
            {" "}
            · {matchName(mb.players[0])} {mb.score[0]} – {mb.score[1]} {matchName(mb.players[1])}
          </>
        )}
        {view.mode === "local" && <> · {mb.score[0]} – {mb.score[1]}</>}
      </span>
      {matchGoesOn ? (
        <Link className="btn small primary" href={`/match/${mb.id}`}>
          {nextIn != null && nextIn > 0 ? t.match.nextRoundIn(nextIn) : t.match.nextRound}
        </Link>
      ) : (
        <Link className="small" href={`/match/${mb.id}`}>
          {t.match.seeMatch}
        </Link>
      )}
    </div>
  ) : null;

  // Spectateur : bandeau (avec le différé anti-triche) ; nombre de spectateurs pour tous.
  const watcher = !isPlayer && view.status !== "waiting";
  const watchInfo =
    watcher || g.spectators > 0 ? (
      <div className={`watchInfo ${watcher ? "watcher" : ""}`}>
        <IconEye size={16} />
        <span>
          {watcher ? t.game.watching : t.game.spectators(g.spectators)}
          {watcher && view.delay > 0 && <small> · {t.game.delayed(view.delay)}</small>}
        </span>
        {watcher && g.spectators > 0 && <span className="watchCount">{t.game.spectators(g.spectators)}</span>}
      </div>
    ) : null;

  const status = (() => {
    if (view.status === "waiting") return isPlayer ? t.game.waitingOpponent : t.game.gameAwaits;
    if (view.status === "aborted") return t.game.aborted;
    if (result) {
      const why = reasonText(result.reason, result.winner, t);
      return result.winner ? t.game.winsBecause(winnerName ?? "", why) : t.game.drawBecause(why);
    }
    if (botThinking) return t.game.thinking(playerName(view.players[botSide! - 1], t));
    if (myTurn) return mySides.length === 2 ? t.game.sideToMove(t.common.sides[toMove]) : t.game.yourMove;
    return t.game.sideToMove(nameOf(toMove));
  })();

  const actions = (
    <div className="actions">
      {onlyPass && myTurn && (
        <button className="btn primary" onClick={() => g.play(legal[0])}>
          {t.game.pass}
        </button>
      )}
      {view.status === "active" && isPlayer && (
        <>
          {canAbort ? (
            <button className="btn ghost" onClick={() => confirm.ask("abort", g.abort)}>
              {confirm.armed === "abort" ? t.game.confirmAbort : t.game.abort}
            </button>
          ) : (
            <button className={`btn ghost ${confirm.armed === "resign" ? "danger" : ""}`} onClick={() => confirm.ask("resign", g.resign)}>
              <IconFlag size={18} /> {confirm.armed === "resign" ? t.game.confirm : t.game.resign}
            </button>
          )}
          {view.mode !== "bot" && (
            <button className="btn ghost" onClick={() => (view.mode === "local" ? confirm.ask("draw", () => g.draw("offer")) : g.draw("offer"))} disabled={view.drawOffer === mySides[0]}>
              <IconHandshake size={18} /> {view.drawOffer === mySides[0] ? t.game.drawOffered : confirm.armed === "draw" ? t.game.confirm : t.game.offerDraw}
            </button>
          )}
        </>
      )}
      {view.status === "waiting" && isPlayer && (
        <button className="btn ghost" onClick={g.abort}>
          {t.game.cancelGame}
        </button>
      )}
      {(view.status === "finished" || view.status === "aborted") && (
        <>
          {isPlayer && !mb && (
            <button className="btn primary" onClick={g.rematch} disabled={view.rematchOffer === mySides[0]}>
              {view.rematchOffer && view.rematchOffer !== mySides[0] ? t.game.acceptRematch : view.rematchOffer === mySides[0] ? t.game.rematchOffered : t.game.rematch}
            </button>
          )}
          {!matchGoesOn && (
            <Link className="btn" href={newGame.href}>
              {newGame.label}
            </Link>
          )}
        </>
      )}
    </div>
  );

  return (
    <div className={`gamePage ${finished ? "done" : ""}`}>
      <section className="boardCol">
        {bar(top)}
        <div className="boardFrame">
          <Board
            heights={heights}
            terrainMode={view.terrain.mode}
            pieces={position.pieces}
            orientation={orientation}
            legalMoves={legal}
            lastMove={lastMove}
            animate={!reviewing}
            interactive={myTurn && !reviewing}
            view={camView}
            intro
            recenterKey={recenter}
            onMove={(m) => void g.play(m)}
            onPreview={setPreview}
            hint={hint}
            skins={botSkins}
            annotations={annotate ? ann : undefined}
            onAnnotate={annotate ? (from, to, color) => setAnn((a) => toggleAnnotation(a, from, to, color)) : undefined}
            onClearAnnotations={() => setAnn(NO_ANNOTATIONS)}
            drawMode={annotate && drawMode}
          />
          {curEval && <EvalBar e={curEval} redAtBottom={orientation === 1} />}
          <div className="viewBar" role="group" aria-label={t.game.cameraAria}>
            <button
              className={`dimToggle ${settings.board2d ? "on" : ""}`}
              title={settings.board2d ? t.game.board3dTitle : t.game.board2dTitle}
              aria-pressed={settings.board2d}
              onClick={() => updateSettings({ board2d: !settings.board2d })}
            >
              2D
            </button>
            {!settings.board2d && CAMERA_VIEWS.map((v, i) => (
              <button
                key={v}
                className={camView === v ? "on" : ""}
                title={`${t.game.cameraViews[v].title} (${i + 1})`}
                onClick={() => {
                  setCamView(v);
                  setRecenter((r) => r + 1);
                }}
              >
                {t.game.cameraViews[v].label}
              </button>
            ))}
          </div>
          <div className="boardTools">
            <button className="iconBtn" title={t.game.flipBoard} onClick={() => setFlip((f) => !f)}>
              <IconFlip size={18} />
            </button>

            {!settings.board2d && (
              <button className="iconBtn" title={t.game.recenter} onClick={() => setRecenter((r) => r + 1)}>
                <IconCenter size={18} />
              </button>
            )}
            {annotate && (
              <button className={`iconBtn ${drawMode ? "on" : ""}`} title={t.game.drawArrows} aria-pressed={drawMode} onClick={() => setDrawMode((d) => !d)}>
                <IconPen size={18} />
              </button>
            )}
            {annotate && hasAnnotations(ann) && (
              <button className="iconBtn" title={t.game.clearArrows} onClick={() => setAnn(NO_ANNOTATIONS)}>
                <IconClose size={18} />
              </button>
            )}
          </div>
          {chargeFlash?.combat && (
            <div className="chargeFlash" key={chargeFlash.ply} role="status">
              <strong>⚡ {t.game.chargeTitle}</strong>
              <span>{t.game.chargeText(chargeFlash.combat.attack, chargeFlash.combat.defense)}</span>
            </div>
          )}
          {preview?.combat && (
            // Mobile : détail du combat par-dessus le plateau (ne le redimensionne pas).
            <div className="combatFloat">
              <CombatCard combat={preview.combat} />
            </div>
          )}
          {reviewing && (
            <button className="reviewBanner" onClick={() => goto(null)}>
              {t.game.reviewBanner(viewPly!, moveCount)}
            </button>
          )}
          {view.drawOffer && mySides.length === 1 && view.drawOffer !== mySides[0] && view.status === "active" && (
            <div className="offerBanner">
              <span>{t.game.opponentOffersDraw}</span>
              <button className="btn small primary" onClick={() => g.draw("accept")}>
                {t.game.accept}
              </button>
              <button className="btn small" onClick={() => g.draw("decline")}>
                {t.game.decline}
              </button>
            </div>
          )}
          {view.status === "waiting" && (
            <div className="boardOverlay">
              {isPlayer ? (
                <div className="overlayCard">
                  <h3>{t.game.inviteTitle}</h3>
                  <p>{t.game.inviteText}</p>
                  <div className="copyRow">
                    <input readOnly value={inviteUrl} onFocus={(e) => e.currentTarget.select()} />
                    <button
                      className="btn primary"
                      onClick={() => {
                        void navigator.clipboard?.writeText(inviteUrl);
                        setCopied(true);
                        setTimeout(() => setCopied(false), 1500);
                      }}
                    >
                      <IconLink size={18} /> {copied ? t.game.copied : t.game.copy}
                    </button>
                  </div>
                  <div className="spinnerRow">
                    <span className="spinner" /> {t.game.waitingOpponent}
                  </div>
                </div>
              ) : (
                <div className="overlayCard">
                  <h3>{t.game.challengesYou(playerName(view.players.find(Boolean), t))}</h3>
                  <p>
                    {view.timeControl ? t.game.timeControlValue(view.timeControl) : t.common.timeClasses.casual} ·{" "}
                    {t.common.terrains[view.terrain.mode]?.name ?? view.terrain.mode}
                    {view.rated ? t.game.ratedSuffix : ""}
                  </p>
                  <button className="btn primary big" onClick={g.join}>
                    {t.game.join}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
        {bar(bottom)}

        {/* Mobile : panneau compact, le plateau prend tout le reste de l'écran. */}
        <div className="mobilePanel">
          {matchInfo}
          {watchInfo}
          <div className="statusLine">
            {botThinking && <span className="spinner" />}
            {status}
          </div>
          <div className="mobileMoves">
            <button className="iconBtn" onClick={() => goto((viewPly ?? moveCount) - 1)} aria-label={t.game.nav.prev}>
              <IconPrev size={18} />
            </button>
            <MoveList moves={view.moves} viewPly={viewPly ?? moveCount} onSelect={goto} compact marks={marks} />
            <button className="iconBtn" onClick={() => goto((viewPly ?? moveCount) + 1)} aria-label={t.game.nav.next}>
              <IconNext size={18} />
            </button>
          </div>
          {actions}
          {g.error && <p className="error">{g.error}</p>}
        </div>
      </section>

      {finished && (
        <div className="card mobileReview">
          <h3>{t.game.gameReview}</h3>
          <AnalysisPanel
            status={review.status}
            analysis={analysis}
            start={startReview}
            error={review.error}
            names={[nameOf(1), nameOf(2)]}
            current={curPly}
            onSelect={goto}
            showHint={showHint}
            setShowHint={setShowHint}
          />
        </div>
      )}

      <aside className="sidePanel">
        <div className="tabs">
          <button className={tab === "moves" ? "on" : ""} onClick={() => setTab("moves")}>
            {t.game.tabs.moves}
          </button>
          <button className={tab === "info" ? "on" : ""} onClick={() => setTab("info")}>
            {t.game.tabs.info}
          </button>
          {finished && (
            <button className={tab === "review" ? "on" : ""} onClick={() => setTab("review")}>
              {t.game.tabs.review}
            </button>
          )}
        </div>
        {matchInfo}
        {watchInfo}
        <div className="statusLine">
          {botThinking && <span className="spinner" />}
          {status}
        </div>
        {tab === "review" && finished ? (
          <>
            <AnalysisPanel
              status={review.status}
              analysis={analysis}
              start={startReview}
              error={review.error}
              names={[nameOf(1), nameOf(2)]}
              current={curPly}
              onSelect={goto}
              showHint={showHint}
              setShowHint={setShowHint}
            />
            {analysis && <MoveList moves={view.moves} viewPly={curPly} onSelect={goto} marks={marks} />}
          </>
        ) : tab === "moves" ? (
          <>
            <MoveList moves={view.moves} viewPly={viewPly ?? moveCount} onSelect={goto} marks={marks} />
            <div className="navRow">
              <button className="iconBtn" onClick={() => goto(0)} title={t.game.nav.first}>
                <IconFirst size={18} />
              </button>
              <button className="iconBtn" onClick={() => goto((viewPly ?? moveCount) - 1)} title={t.game.nav.prev}>
                <IconPrev size={18} />
              </button>
              <button className="iconBtn" onClick={() => goto((viewPly ?? moveCount) + 1)} title={t.game.nav.next}>
                <IconNext size={18} />
              </button>
              <button className="iconBtn" onClick={() => goto(null)} title={t.game.nav.live}>
                <IconLast size={18} />
              </button>
            </div>
          </>
        ) : (
          <div className="infoTab">
            <dl>
              <dt>{t.game.info.mode}</dt>
              <dd>
                {view.mode === "bot"
                  ? t.game.info.vsBot(t.common.bots[view.botLevel ?? 1]?.name, view.botLevel)
                  : view.mode === "arena"
                    ? t.arena.title
                  : view.source
                    ? t.game.info.imported(view.source.site)
                  : view.mode === "local"
                    ? t.game.info.local
                    : view.rated
                      ? t.game.info.onlineRated
                      : t.game.info.onlineCasual}
              </dd>
              {view.source && (
                <>
                  <dt />
                  <dd>
                    <a href={view.source.url} target="_blank" rel="noopener noreferrer">
                      {t.game.info.original}
                    </a>
                  </dd>
                </>
              )}
              <dt>{t.game.info.timeControl}</dt>
              <dd>{view.timeControl ?? t.common.timeClasses.casual}</dd>
              <dt>{t.game.info.terrain}</dt>
              <dd>{t.common.terrains[view.terrain.mode]?.name ?? view.terrain.mode}</dd>
              <dt>{t.game.info.moves}</dt>
              <dd>
                {view.position.ply} / {view.moveLimit}
              </dd>
            </dl>
            <h4>{t.game.info.pieces}</h4>
            <ul className="pieceTable">
              {(Object.keys(PIECES) as (keyof typeof PIECES)[]).map((k) => (
                <li key={k}>
                  <PieceIcon kind={k} side={baseSide} />
                  <span>{t.common.pieces[k].name}</span>
                  <small>
                    {t.game.info.pieceStats(PIECES[k].movement, PIECES[k].strength)}
                  </small>
                </li>
              ))}
            </ul>
            <p className="muted small">
              {t.game.info.rulesSummary} <Link href="/rules">{t.game.info.allRules}</Link>
            </p>
          </div>
        )}
        {preview?.combat && <CombatCard combat={preview.combat} />}
        {g.error && <p className="error">{g.error}</p>}
        {actions}
        {!g.connected && view.status === "active" && <p className="muted small">{t.game.reconnecting}</p>}
      </aside>

      <Modal open={showEnd} onClose={() => setShowEnd(false)}>
        <div className="endModal">
          <div className={`endTitle ${youWon ? "won" : youLost ? "lost" : ""}`}>
            {mb && (youWon || youLost || result?.winner == null)
              ? result?.winner == null
                ? t.match.roundDrawn
                : youWon
                  ? t.match.roundWon
                  : t.match.roundLost
              : result?.winner == null
                ? t.game.draw
                : youWon
                  ? t.game.victory
                  : youLost
                    ? t.game.defeat
                    : t.game.winsTitle(winnerName ?? "")}
          </div>
          <p className="muted">{result ? reasonText(result.reason, result.winner, t) : ""}</p>
          <div className="endScores">
            {[1, 2].map((s) => (
              <div key={s} className={`endPlayer side${s}`}>
                <strong>
                  {nameOf(s as Side)} <Flag code={playerOf(s as Side)?.country} />
                </strong>
                <span className="big">★ {view.position.scores[s - 1]}</span>
                {view.ratingChange && (
                  <span className={`delta ${view.ratingChange[s - 1] >= 0 ? "up" : "down"}`}>
                    {view.players[s - 1]?.rating} ({view.ratingChange[s - 1] >= 0 ? "+" : ""}
                    {view.ratingChange[s - 1]})
                  </span>
                )}
              </div>
            ))}
          </div>
          {view.rankChange && mySides.length === 1 && view.ratingChange && (
            <RankResult
              before={view.rankChange[mySides[0] - 1].before}
              after={view.rankChange[mySides[0] - 1].after}
              delta={view.ratingChange[mySides[0] - 1]}
            />
          )}
          <div className="endActions">
            {mb && fullSite && (
              <Link className="btn primary big" href={`/match/${mb.id}`}>
                {matchGoesOn ? t.match.nextRound : t.match.seeMatch}
              </Link>
            )}
            {isPlayer && !mb && (
              <button className="btn primary big" onClick={g.rematch}>
                {view.rematchOffer && view.rematchOffer !== mySides[0] ? t.game.acceptRematch : t.game.rematch}
              </button>
            )}
            {view.moves.length > 0 && (
              <button
                className="btn big"
                onClick={() => {
                  setShowEnd(false);
                  startReview();
                }}
              >
                {t.game.gameReview}
              </button>
            )}
            {!matchGoesOn && (
              <Link className="btn big" href={newGame.href}>
                {newGame.label}
              </Link>
            )}
            <button className="btn ghost" onClick={() => setShowEnd(false)}>
              {t.game.viewBoard}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
