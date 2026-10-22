// Textes : page Rangs et classement + puces / cartes de rang (components/ui/Rank.tsx).
// Le français est la référence ; l'anglais a les mêmes clés. Fichier en .tsx : les
// paragraphes gardent leur mise en valeur (<b>).
import type { ReactNode } from "react";

const fr = {
  metaTitle: "Rangs et classement — Traversal",
  title: "Rangs et classement",
  hero: (
    <>
      De la vallée au sommet : chaque partie <b>en ligne</b> compte pour ton rang, dans son type : <b>Bullet</b>,{" "}
      <b>Classique</b> et <b>Tactique</b> (au match) ont chacun leur échelle. Grimpe de l’<b>Ardoise</b> jusqu’à la <b>Légende</b>.
    </>
  ) as ReactNode,
  ascent: {
    title: "L’ascension",
    intro: "Chaque rang est une étape de la montée, de la vallée jusqu’au-dessus des nuages.",
  },
  // Même barème que l'API (backend/app/services/ranks.py).
  ladder: {
    slate: { range: "moins de 1000", blurb: "On lace ses chaussures au fond de la vallée." },
    bronze: { range: "1000 – 1199", blurb: "Le sentier serpente : les pièges du terrain apparaissent." },
    silver: { range: "1200 – 1399", blurb: "Sous les sapins, on apprend à compter ses points de Mouvement." },
    gold: { range: "1400 – 1599", blurb: "Le soleil se lève sur l’alpage. Tout le monde part d’Or II." },
    jade: { range: "1600 – 1799", blurb: "Le lac reflète le sommet : combats préparés, hauteurs maîtrisées." },
    sapphire: { range: "1800 – 1999", blurb: "Piolet en main sur la glace : les charges tombent juste." },
    diamond: { range: "2000 – 2199", blurb: "Le drapeau est planté : l’élite, où chaque coup se paie." },
    master: { range: "2200 et plus", blurb: "L’air se raréfie dans les neiges éternelles. Plus de divisions : seuls les PL départagent." },
    legend: { range: "les 3 meilleurs Maîtres", blurb: "Seuls au-dessus des nuages : trois places par type de partie, à défendre." },
  } as Record<string, { range: string; blurb: string }>,
  how: {
    title: "Comment ça marche",
    items: [
      <>
        <b>Divisions.</b> Chaque palier compte 4 divisions, de <b>IV</b> (l’entrée) à <b>I</b> (le seuil du palier
        suivant). Exemple : Or IV → Or III → Or II → Or I → Jade IV.
      </>,
      <>
        <b>Points de ligue (PL).</b> Tu as de 0 à 100 PL dans ta division. À 100, tu montes ; sous 0, tu descends.
        Une victoire rapporte des PL, une défaite en retire.
      </>,
      <>
        <b>Placement.</b> Tes <b>5 premières parties</b> classées dans un type de partie servent à te situer : ton rang
        est révélé à la fin de la 5ᵉ. Tout le monde démarre à <b>Or II</b>, puis le placement bouge vite.
      </>,
      <>
        <b>Maître et Légende.</b> À partir de Maître, plus de divisions : tes PL grimpent sans plafond. Les{" "}
        <b>3 meilleurs Maîtres</b> de chaque type de partie portent le rang <b>Légende</b> — tant qu’ils tiennent leur
        place.
      </>,
      <>
        <b>Ce qui compte.</b> Les parties en ligne avec pendule, par matchmaking ou par invitation. Pas les parties
        contre un bot, en local, ni sans pendule.
      </>,
    ] as ReactNode[],
  },
  glicko: {
    title: "Sous le capot : Glicko-2",
    intro: (
      <>
        Ton rang est une lecture de ton <b>classement Glicko-2</b> (le système de chess.com et lichess) : chaque
        division couvre 50 points de classement, soit 2 PL par point. Pas de PL « offerts » ni de protection
        artificielle : ton rang suit exactement ton niveau.
      </>
    ) as ReactNode,
    items: [
      <>Battre un adversaire mieux classé rapporte plus ; perdre contre un moins bien classé coûte plus.</>,
      <>
        Le système tient compte de sa <b>certitude</b> sur ton niveau : tant qu’il te connaît mal (début, longue
        absence), ton classement bouge beaucoup ; ensuite il se stabilise.
      </>,
      <>Le matchmaking cherche un adversaire proche de ton classement, et élargit la recherche si l’attente dure.</>,
    ] as ReactNode[],
  },
  cta: {
    play: "Jouer une partie classée",
    leaderboard: "Voir le classement",
  },
  // Puces et cartes de rang (components/ui/Rank.tsx).
  chip: {
    placementTitle: (played: number, total: number) => `En placement (${played}/${total})`,
  },
  lpAria: (lp: number) => `${lp} points de ligue sur 100`,
  card: {
    placementLeft: (n: number) => `Encore ${n} partie${n > 1 ? "s" : ""} de placement`,
    next: "Prochain :",
    playRanked: "Joue une partie classée",
  },
};

const en: typeof fr = {
  metaTitle: "Ranks and rating — Traversal",
  title: "Ranks and rating",
  hero: (
    <>
      From the valley to the summit: every <b>online game</b> counts towards your rank in its game type: <b>Bullet</b>,{" "}
      <b>Classic</b> and <b>Tactic</b> (per match) each have their own ladder. Climb from <b>Slate</b> all the way to <b>Legend</b>.
    </>
  ),
  ascent: {
    title: "The ascent",
    intro: "Each rank is a stage of the climb, from the valley to above the clouds.",
  },
  ladder: {
    slate: { range: "below 1000", blurb: "Lacing up your boots at the bottom of the valley." },
    bronze: { range: "1000 – 1199", blurb: "The trail winds upward: the terrain’s traps start to show." },
    silver: { range: "1200 – 1399", blurb: "Under the pines, you learn to count your Movement points." },
    gold: { range: "1400 – 1599", blurb: "The sun rises over the alpine meadow. Everyone starts at Gold II." },
    jade: { range: "1600 – 1799", blurb: "The lake mirrors the summit: fights prepared, heights mastered." },
    sapphire: { range: "1800 – 1999", blurb: "Ice axe in hand on the glacier: every charge lands." },
    diamond: { range: "2000 – 2199", blurb: "The flag is planted: the elite, where every move counts." },
    master: { range: "2200 and above", blurb: "The air thins in the eternal snows. No more divisions: only LP decide." },
    legend: { range: "the top 3 Masters", blurb: "Alone above the clouds: three spots per game type, to defend." },
  },
  how: {
    title: "How it works",
    items: [
      <>
        <b>Divisions.</b> Each tier has 4 divisions, from <b>IV</b> (the entry) to <b>I</b> (the doorstep of the next
        tier). For example: Gold IV → Gold III → Gold II → Gold I → Jade IV.
      </>,
      <>
        <b>League points (LP).</b> You have 0 to 100 LP in your division. At 100, you get promoted; below 0, you get
        demoted. A win earns LP, a loss costs LP.
      </>,
      <>
        <b>Placement.</b> Your <b>first 5 ranked games</b> in a game type are placement games: your rank is
        revealed at the end of the 5th. Everyone starts at <b>Gold II</b>, then placement moves you quickly.
      </>,
      <>
        <b>Master and Legend.</b> From Master on, there are no divisions: your LP climb with no ceiling. The{" "}
        <b>top 3 Masters</b> of each game type hold the <b>Legend</b> rank — as long as they keep their spot.
      </>,
      <>
        <b>What counts.</b> Online games with a clock, from matchmaking or by invitation. Not games against a bot,
        local games, or games without a clock.
      </>,
    ],
  },
  glicko: {
    title: "Under the hood: Glicko-2",
    intro: (
      <>
        Your rank is a reading of your <b>Glicko-2 rating</b> (the system used by chess.com and lichess): each
        division covers 50 rating points, i.e. 2 LP per point. No “free” LP and no artificial demotion shields: your
        rank follows your level exactly.
      </>
    ),
    items: [
      <>Beating a higher-rated opponent earns more; losing to a lower-rated one costs more.</>,
      <>
        The system tracks how <b>certain</b> it is about your level: while it doesn’t know you well (new player, long
        break), your rating moves a lot; then it settles down.
      </>,
      <>Matchmaking looks for an opponent close to your rating, and widens the search if the wait drags on.</>,
    ],
  },
  cta: {
    play: "Play a ranked game",
    leaderboard: "View the leaderboard",
  },
  chip: {
    placementTitle: (played, total) => `In placement (${played}/${total})`,
  },
  lpAria: (lp) => `${lp} league points out of 100`,
  card: {
    placementLeft: (n) => `${n} placement game${n > 1 ? "s" : ""} left`,
    next: "Next:",
    playRanked: "Play a ranked game",
  },
};

export default { fr, en };
