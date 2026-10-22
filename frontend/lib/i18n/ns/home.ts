// Textes : accueil (héros, gros boutons, mes parties). Le français est la référence ;
// l'anglais a les mêmes clés.

const fr = {
  myGames: "Mes parties",
  outcome: {
    waiting: "En attente",
    aborted: "Annulée",
    ongoing: "En cours",
    draw: "Nulle",
    win: "Victoire",
    loss: "Défaite",
  },
  sideWins: (side: string) => `${side} gagne`,
  localGame: "Partie locale",
  vs: (name: string) => `vs ${name}`,
  noClock: "sans pendule",
  heroTitle: "Fais traverser tes pièces.",
  heroAccent: "Domine les hauteurs.",
  heroLead:
    "Traversal, le jeu de stratégie en 3D : un plateau de montagnes et de vallées, six pièces chacun, et une seule question — qui franchira l’arrivée en premier ?",
  playOnline: "Jouer en ligne",
  playOnlineSub: "Partie classée contre un joueur de ton niveau",
  playBot: "Jouer contre un bot",
  playBotSub: (first: string, last: string) => `5 niveaux, de ${first} à ${last}`,
  playLocal: "Partie locale",
  playLocalSub: "À deux sur le même écran",
  puzzles: "Puzzles",
  puzzlesSub: "Trouve le coup qui gagne · Puzzle Rush",
  learnRules: "Apprendre les règles",
  learnRulesSub: "5 minutes pour tout comprendre",
  playersOnline: (n: number) => `joueur${n > 1 ? "s" : ""} en ligne`,
  gamesPlaying: (n: number) => `partie${n > 1 ? "s" : ""} en cours`,
};

const en: typeof fr = {
  myGames: "My games",
  outcome: {
    waiting: "Waiting",
    aborted: "Aborted",
    ongoing: "In progress",
    draw: "Draw",
    win: "Win",
    loss: "Loss",
  },
  sideWins: (side: string) => `${side} wins`,
  localGame: "Local game",
  vs: (name: string) => `vs ${name}`,
  noClock: "no clock",
  heroTitle: "Get your pieces across.",
  heroAccent: "Rule the heights.",
  heroLead:
    "Traversal, the 3D strategy game: a board of mountains and valleys, six pieces each, and a single question — who will cross the finish line first?",
  playOnline: "Play online",
  playOnlineSub: "Rated game against a player at your level",
  playBot: "Play a bot",
  playBotSub: (first: string, last: string) => `5 levels, from ${first} to ${last}`,
  playLocal: "Local game",
  playLocalSub: "Two players on the same screen",
  puzzles: "Puzzles",
  puzzlesSub: "Find the winning move · Puzzle Rush",
  learnRules: "Learn the rules",
  learnRulesSub: "5 minutes to get it all",
  playersOnline: (n: number) => `player${n === 1 ? "" : "s"} online`,
  gamesPlaying: (n: number) => `game${n === 1 ? "" : "s"} in progress`,
};

export default { fr, en };
