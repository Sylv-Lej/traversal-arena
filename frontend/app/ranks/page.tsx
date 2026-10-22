import Link from "next/link";
import type { Metadata } from "next";
import { RankEmblem } from "@/components/ui/Rank";
import { TIER_ORDER } from "@/lib/ranks";
import { getT } from "@/lib/i18n/server";
import { fullSite } from "@/lib/site";
import type { Rank } from "@/lib/types";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT();
  return { title: t.ranks.metaTitle };
}

// Rang de démonstration (emblèmes) : le libellé affiché vient du dictionnaire (`rankLabel`).
const demo = (tier: string, division: number | null): Rank => ({
  tier,
  name: tier,
  division,
  label: tier,
  lp: 0,
  placement: null,
  next: null,
});

export default async function RanksPage() {
  const t = await getT();
  const r = t.ranks;
  return (
    <div className="page narrow ranksPage">
      <h1 className="pageTitle">{r.title}</h1>

      <section className="card rankHero">
        <div className="heroEmblems">
          <RankEmblem rank={demo("gold", 2)} size={88} />
          <RankEmblem rank={demo("diamond", 1)} size={104} />
          <RankEmblem rank={demo("legend", null)} size={120} />
        </div>
        <p>{r.hero}</p>
      </section>

      <section className="card">
        <h2>{r.ascent.title}</h2>
        <p className="muted">{r.ascent.intro}</p>
        <ul className="ladder">
          {[...TIER_ORDER].reverse().map((tier) => (
            <li key={tier} className={`ladderRow tier-${tier}`}>
              <RankEmblem rank={demo(tier, ["master", "legend"].includes(tier) ? null : 4)} size={58} />
              <div>
                <b>{t.common.tiers[tier]}</b>
                <span className="rankZone">
                  {t.common.zones[tier]}
                </span>
                <span className="muted small">{r.ladder[tier].blurb}</span>
              </div>
              <span className="ladderRange">{r.ladder[tier].range}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="card">
        <h2>{r.how.title}</h2>
        <ul className="ruleList">
          {r.how.items.map((item, i) => <li key={i}>{item}</li>)}
        </ul>
      </section>

      <section className="card">
        <h2>{r.glicko.title}</h2>
        <p>{r.glicko.intro}</p>
        <ul className="ruleList">
          {r.glicko.items.map((item, i) => <li key={i}>{item}</li>)}
        </ul>
      </section>

      <div className="center stack">
        {fullSite() ? (
          <>
            <Link className="btn primary huge" href="/play">
              {r.cta.play}
            </Link>
            <Link className="btn" href="/leaderboard">
              {r.cta.leaderboard}
            </Link>
          </>
        ) : (
          <Link className="btn primary huge" href="/arena">
            {t.arena.title}
          </Link>
        )}
      </div>
    </div>
  );
}
