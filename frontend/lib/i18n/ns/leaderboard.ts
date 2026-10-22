// Textes : classement (tableau des meilleurs joueurs par type de partie). Le français est la
// référence ; l'anglais a les mêmes clés.

const fr = {
  title: "Classement",
  intro: "Grimpe de l’Ardoise à la Légende.",
  howRanksWork: "Comment fonctionnent les rangs ?",
  empty: (cls: string) => `Personne n’est encore classé en ${cls}.`,
  playRated: "Joue une partie classée",
  emptyAfter: " pour inaugurer le tableau !",
  player: "Joueur",
  rank: "Rang",
  rating: "Classement",
  wdl: "V / D / N",
};

const en: typeof fr = {
  title: "Leaderboard",
  intro: "Climb from Slate to Legend.",
  howRanksWork: "How do ranks work?",
  empty: (cls: string) => `Nobody is ranked in ${cls} yet.`,
  playRated: "Play a rated game",
  emptyAfter: " to be the first on the board!",
  player: "Player",
  rank: "Rank",
  rating: "Rating",
  wdl: "W / L / D",
};

export default { fr, en };
