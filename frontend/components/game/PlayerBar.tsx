"use client";

import { Flag } from "@/components/ui/Flag";
import { useEffect, useState } from "react";
import { Avatar } from "@/components/ui/Shell";
import { PieceIcon } from "@/components/ui/icons";
import { RankChip, RankEmblem } from "@/components/ui/Rank";
import { BOTS, formatClock } from "@/lib/game";
import { useT } from "@/lib/i18n/client";
import { playerName } from "@/lib/i18n/helpers";
import type { PieceT, PlayerCard, Side } from "@/lib/types";
import { sounds } from "@/lib/sound";
import { useSettings } from "@/lib/settings";

function Clock({ ms, running, receivedAt }: { ms: number; running: boolean; receivedAt: number }) {
  const [now, setNow] = useState(() => performance.now());
  const { sound } = useSettings();
  useEffect(() => {
    if (!running) return;
    let raf = 0;
    let lastSec = -1;
    const tick = () => {
      const t = performance.now();
      setNow(t);
      const left = ms - (t - receivedAt);
      const sec = Math.ceil(left / 1000);
      if (sound && left < 10_000 && left > 0 && sec !== lastSec) {
        lastSec = sec;
        sounds.tick();
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [running, ms, receivedAt, sound]);
  const left = running ? ms - (now - receivedAt) : ms;
  return <div className={`clock ${running ? "running" : ""} ${left < 10_000 ? "low" : ""}`}>{formatClock(left)}</div>;
}

export function PlayerBar({
  side,
  player,
  isYou,
  toMove,
  score,
  capturedByThem,
  clockMs,
  clockRunning,
  receivedAt,
  ratingDelta,
  waiting,
}: {
  side: Side;
  player: PlayerCard | null;
  isYou: boolean;
  toMove: boolean;
  score: number;
  capturedByThem: PieceT[];
  clockMs: number | null;
  clockRunning: boolean;
  receivedAt: number;
  ratingDelta?: number | null;
  waiting?: boolean;
}) {
  const t = useT();
  const name = player ? playerName(player, t) : waiting ? t.game.waitingShort : t.common.sides[side];
  return (
    <div className={`playerBar side${side} ${toMove ? "toMove" : ""}`}>
      <div className="who">
        {player?.isBot ? (
          <RankEmblem
            rank={player.rank ?? BOTS[Number(player.id.replace("bot", "")) - 1]?.rank ?? null}
            size={40}
            animated={false}
          />
        ) : (
          <Avatar name={name} size={36} />
        )}
        <div className="names">
          <div className="nameLine">
            <span className={`teamDot side${side}`} />
            <strong>{name}</strong>
            <Flag code={player?.country} />
            {player?.rank && <RankChip rank={player.rank} size={20} />}
            {player?.rating != null && (
              <span className="rating">
                ({player.rating}
                {player.provisional ? "?" : ""})
              </span>
            )}
            {ratingDelta != null && (
              <span className={`delta ${ratingDelta >= 0 ? "up" : "down"}`}>
                {ratingDelta >= 0 ? "+" : ""}
                {ratingDelta}
              </span>
            )}
            {isYou && <span className="youTag">{t.common.you}</span>}
          </div>
          <div className="material">
            {capturedByThem.map((p) => (
              <PieceIcon key={p.id} kind={p.kind} side={p.owner} size={15} />
            ))}
            {score > 0 && <span className="scorePill">★ {score}</span>}
          </div>
        </div>
      </div>
      {clockMs !== null && <Clock ms={clockMs} running={clockRunning} receivedAt={receivedAt} />}
    </div>
  );
}
