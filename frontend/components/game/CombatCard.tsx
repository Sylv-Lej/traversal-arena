"use client";

import { useT } from "@/lib/i18n/client";
import type { CombatT } from "@/lib/types";

export function CombatCard({ combat, title }: { combat: CombatT; title?: string }) {
  const tr = useT();
  const win = combat.attack >= combat.defense;
  const term = (t: { label: string; value: number }, i: number) => (
    <li key={i}>
      <span>{tr.common.terms[t.label] ?? t.label}</span>
      <b className={t.value < 0 ? "neg" : ""}>
        {t.value > 0 && i > 0 ? "+" : ""}
        {t.value}
      </b>
    </li>
  );
  return (
    <div className={`combatCard ${win ? "win" : "lose"}`}>
      <div className="combatHead">
        <span>{title ?? tr.game.combatPreview}</span>
        <strong>
          {combat.attack} <small>vs</small> {combat.defense}
        </strong>
      </div>
      <div className="combatCols">
        <ul>
          <li className="colTitle">⚔ {tr.game.attack}</li>
          {combat.attackTerms.map(term)}
        </ul>
        <ul>
          <li className="colTitle">🛡 {tr.game.defense}</li>
          {combat.defenseTerms.map(term)}
        </ul>
      </div>
      <p className="combatVerdict">{win ? tr.game.combatWin : tr.game.combatLose}</p>
    </div>
  );
}
