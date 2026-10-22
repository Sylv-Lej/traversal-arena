import Link from "next/link";
import type { Metadata } from "next";
import { PieceShowcase, Situations } from "@/components/rules/Scenarios";
import { PIECES } from "@/lib/game";
import { getT } from "@/lib/i18n/server";
import { fullSite } from "@/lib/site";
import type { Kind } from "@/lib/types";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT();
  return { title: t.rules.metaTitle };
}

export default async function Rules() {
  const t = await getT();
  const r = t.rules;
  return (
    <div className="page narrow rules">
      <h1 className="pageTitle">{r.title}</h1>

      <section className="card">
        <h2>{r.glance.title}</h2>
        <div className="glance">
          <div><b>2</b><small>{r.glance.players}</small></div>
          <div><b>6</b><small>{r.glance.piecesEach}</small></div>
          <div><b>10×10</b><small>{r.glance.board}</small></div>
          <div><b>2</b><small>{r.glance.exits}</small></div>
        </div>
        <p>{r.glance.intro}</p>
        <p className="muted">{r.glance.sides}</p>
      </section>

      <section className="card">
        <h2>{r.pieces.title}</h2>
        <p>{r.pieces.intro}</p>
        <div className="pieceCards">
          {(Object.keys(PIECES) as Kind[]).map((k) => (
            <div key={k} className="pieceCard">
              <PieceShowcase kind={k} />
              <h3>{t.common.pieces[k].name}</h3>
              <small className="muted">{t.common.pieces[k].shape}</small>
              <div className="stats">
                <span>{t.common.stats.movement} <b>{PIECES[k].movement}</b></span>
                <span>{t.common.stats.strength} <b>{PIECES[k].strength}</b></span>
              </div>
              <p>{t.common.pieces[k].special}</p>
            </div>
          ))}
        </div>
        <p className="muted">{r.pieces.setup}</p>
      </section>

      <section className="card">
        <h2>{r.move.title}</h2>
        <ul className="ruleList">
          {r.move.items.map((item, i) => <li key={i}>{item}</li>)}
        </ul>
      </section>

      <section className="card">
        <h2>{r.combat.title}</h2>
        <ul className="ruleList">
          {r.combat.items.map((item, i) => <li key={i}>{item}</li>)}
        </ul>
      </section>

      <section className="card">
        <h2>{r.end.title}</h2>
        <ul className="ruleList">
          {r.end.items.map((item, i) => <li key={i}>{item}</li>)}
        </ul>
      </section>

      <section className="card">
        <h2>{r.situations.title}</h2>
        <p className="muted">{r.situations.intro}</p>
        <Situations />
      </section>

      <div className="center">
        {fullSite() ? (
          <Link className="btn primary huge" href="/play?tab=bot">
            {r.cta.train}
          </Link>
        ) : (
          <Link className="btn primary huge" href="/arena/new">
            {t.arena.create}
          </Link>
        )}
        <p>
          <Link href="/ranks">{r.cta.ranks}</Link>
        </p>
      </div>
    </div>
  );
}
