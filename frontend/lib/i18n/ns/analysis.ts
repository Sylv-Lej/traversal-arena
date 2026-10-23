// Textes : analysis (bilan de partie : précision, classement des coups, courbe d'avantage).
// Le français est la référence ; l'anglais a les mêmes clés.

const fr = {
  classes: {
    best: "Meilleur",
    excellent: "Excellent",
    good: "Bon",
    inaccuracy: "Imprécision",
    mistake: "Erreur",
    blunder: "Gaffe",
    forced: "Forcé",
  },
  /** Nombre à une décimale (virgule en français). */
  dec: (v: number) => v.toFixed(1).replace(".", ","),
  wins: (side: string) => `${side} gagne`,
  winShort: "V", // victoire forcée, dans la barre d'évaluation
  evalLabel: (v: string) => `Évaluation ${v}`,
  graphLabel: "Courbe d'avantage au fil de la partie",
  startPosition: "Position de départ",
  intro:
    "Le moteur rejoue la partie coup par coup : précision de chaque joueur, meilleurs coups manqués, erreurs et gaffes.",
  queued: "En file d’attente…",
  progress: (done: number, total: number) => `Analyse… ${done} / ${total} coups`,
  start: "Lancer le bilan de la partie",
  failed: "L’analyse a échoué. Réessaie.",
  accuracy: "précision",
  bestMove: "Meilleur coup :",
  showOnBoard: "Montrer sur le plateau",
  wasBest: "C’était le meilleur coup.",
  footer: (depth: number) => `Évaluation par orque, profondeur ${depth}. Clique la courbe ou un coup pour le revoir.`,
  analysedWith: (bot: string, rating: number | null) =>
    `Analysé avec : ${bot}${rating != null ? ` (${rating})` : ""}, n°1 de l’arène.`,
  analysedWithOrque: "Analysé avec : orque.",
  analysing: "Analyse de la partie en cours…",
  byArena: "Le n°1 de l’arène analyse la partie… (une à deux minutes)",
  // Import d'une partie de traversalgame.com (page /analyse)
  importTitle: "Analyser une partie",
  importIntro:
    "Colle le lien d’une partie terminée sur traversalgame.com : elle est rejouée avec nos règles, puis analysée coup par coup par le n°1 du classement de l’arène.",
  importLink: "Lien de la partie",
  importPlaceholder: "https://www.traversalgame.com/game/…",
  importSubmit: "Analyser",
  importing: "Import de la partie…",
  importClosed: "L’import de parties n’est pas disponible pour le moment.",
};

const en: typeof fr = {
  classes: {
    best: "Best",
    excellent: "Excellent",
    good: "Good",
    inaccuracy: "Inaccuracy",
    mistake: "Mistake",
    blunder: "Blunder",
    forced: "Forced",
  },
  dec: (v: number) => v.toFixed(1),
  wins: (side: string) => `${side} wins`,
  winShort: "W",
  evalLabel: (v: string) => `Evaluation ${v}`,
  graphLabel: "Advantage graph over the game",
  startPosition: "Starting position",
  intro: "The engine replays the game move by move: each player’s accuracy, missed best moves, mistakes and blunders.",
  queued: "Queued…",
  progress: (done: number, total: number) => `Analyzing… ${done} / ${total} moves`,
  start: "Start game review",
  failed: "Analysis failed. Try again.",
  accuracy: "accuracy",
  bestMove: "Best move:",
  showOnBoard: "Show on board",
  wasBest: "That was the best move.",
  footer: (depth: number) => `Evaluation by orque, depth ${depth}. Click the graph or a move to review it.`,
  analysedWith: (bot: string, rating: number | null) =>
    `Analyzed with: ${bot}${rating != null ? ` (${rating})` : ""}, the arena’s #1.`,
  analysedWithOrque: "Analyzed with: orque.",
  analysing: "Game analysis in progress…",
  byArena: "The arena’s #1 is analyzing the game… (one to two minutes)",
  importTitle: "Analyze a game",
  importIntro:
    "Paste the link of a finished game on traversalgame.com: it is replayed with our rules, then analyzed move by move by the top bot of the arena leaderboard.",
  importLink: "Game link",
  importPlaceholder: "https://www.traversalgame.com/game/…",
  importSubmit: "Analyze",
  importing: "Importing the game…",
  importClosed: "Game import isn’t available right now.",
};

export default { fr, en };
