// Textes : page profil d'un joueur et courbe de classement. Le français est la référence ;
// l'anglais a les mêmes clés.

const fr = {
  howRanksWork: "Comment fonctionnent les rangs ?",
  ratingHistory: "Évolution du classement",
  currentRating: "Classement actuel",
  inPlacement: "En placement",
  best: "Meilleur",
  games: "Parties",
  wdl: (w: number, l: number, d: number) => `${w} V · ${l} D · ${d} N`,
  noRatedGames: (cls: string) =>
    `Aucune partie classée en ${cls} pour l’instant. Les parties en ligne avec pendule comptent pour le classement.`,
  onlineGames: "Parties en ligne",
  noOnlineGames: "Aucune partie en ligne pour l’instant.",
  result: { ongoing: "En cours", draw: "Nulle", win: "Victoire", loss: "Défaite" },
  vs: (name: string) => `vs ${name}`,
  noClock: "sans pendule",
  chart: {
    aria: (from: number, to: number, n: number) => `Évolution du classement : de ${from} à ${to} en ${n} parties`,
    result: { win: "Victoire", loss: "Défaite", draw: "Nulle" },
    against: (result: string, opponent: string) => `${result} contre ${opponent}`,
    gameN: (n: number) => `Partie ${n}`,
    start: "Classement de départ",
    ratedGames: "Parties classées →",
    showTable: "Voir le tableau",
    hideTable: "Masquer le tableau",
    date: "Date",
    opponent: "Adversaire",
    resultCol: "Résultat",
    rating: "Classement",
  },
};

const en: typeof fr = {
  howRanksWork: "How do ranks work?",
  ratingHistory: "Rating history",
  currentRating: "Current rating",
  inPlacement: "In placement",
  best: "Best",
  games: "Games",
  wdl: (w: number, l: number, d: number) => `${w} W · ${l} L · ${d} D`,
  noRatedGames: (cls: string) => `No rated ${cls} games yet. Online games with a clock count toward your rating.`,
  onlineGames: "Online games",
  noOnlineGames: "No online games yet.",
  result: { ongoing: "In progress", draw: "Draw", win: "Win", loss: "Loss" },
  vs: (name: string) => `vs ${name}`,
  noClock: "no clock",
  chart: {
    aria: (from: number, to: number, n: number) => `Rating history: from ${from} to ${to} over ${n} game${n === 1 ? "" : "s"}`,
    result: { win: "Win", loss: "Loss", draw: "Draw" },
    against: (result: string, opponent: string) => `${result} vs ${opponent}`,
    gameN: (n: number) => `Game ${n}`,
    start: "Starting rating",
    ratedGames: "Rated games →",
    showTable: "Show table",
    hideTable: "Hide table",
    date: "Date",
    opponent: "Opponent",
    resultCol: "Result",
    rating: "Rating",
  },
};

export default { fr, en };
