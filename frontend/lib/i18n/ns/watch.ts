// Textes : page « Regarder » (parties en ligne en cours).

const fr = {
  title: "Parties en cours",
  intro: "Les meilleures parties en ligne du moment, les plus relevées d’abord.",
  delayNote: "Anti-triche : les spectateurs voient chaque partie avec un tour de retard (2 coups). Tout est dévoilé à la fin.",
  empty: "Aucune partie en ligne en cours pour l’instant.",
  playOne: "Lancer une partie",
  moves: (n: number) => `${n} coup${n > 1 ? "s" : ""}`,
  rated: "Classée",
  casual: "Amicale",
  watch: "Regarder",
  spectators: (n: number) => `${n} spectateur${n > 1 ? "s" : ""}`,
};

const en: typeof fr = {
  title: "Live games",
  intro: "The best online games right now, strongest first.",
  delayNote: "Anti-cheat: spectators see every game one full turn late (2 moves). Everything is revealed at the end.",
  empty: "No online games in progress right now.",
  playOne: "Start a game",
  moves: (n: number) => `${n} move${n === 1 ? "" : "s"}`,
  rated: "Rated",
  casual: "Casual",
  watch: "Watch",
  spectators: (n: number) => `${n} spectator${n === 1 ? "" : "s"}`,
};

export default { fr, en };
