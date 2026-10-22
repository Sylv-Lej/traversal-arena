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
  footer: (depth: number) => `Moteur Traversal, profondeur ${depth}. Clique la courbe ou un coup pour le revoir.`,
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
  footer: (depth: number) => `Traversal engine, depth ${depth}. Click the graph or a move to review it.`,
};

export default { fr, en };
