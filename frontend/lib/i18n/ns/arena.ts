// Textes : arène des bots (classement des bots WebAssembly envoyés par les joueurs, guide,
// envoi). Le français est la référence ; l'anglais a les mêmes clés.

const fr = {
  title: "Arène des bots",
  // Accueil
  home: {
    title: "Écris un bot.",
    accent: "Il joue pour toi.",
    lead: "Traversal est un jeu de stratégie en relief. Code ton bot, envoie-le dans l’arène : il affronte les autres bots jour et nuit et grimpe au classement.",
    createSub: "SDK Rust, ou n’importe quel langage qui compile en WebAssembly",
    board: "Classement des bots",
    boardSub: (n: number) => (n === 0 ? "Sois le premier bot de la communauté" : `${n} bot${n > 1 ? "s" : ""} de la communauté en lice`),
    rules: "Règles du jeu",
    rulesSub: "10 × 10 en relief, trois pièces, une course",
    sdk: "Le SDK sur GitHub",
    sdkSub: "Exemples, bot de départ, outil de test en local",
    top: "En tête de l’arène",
    fullBoard: "Tout le classement",
  },
  homeReplay: {
    ply: (i: number, n: number) => `demi-coup ${i}/${n}`,
    open: "Revoir",
  },
  intro:
    "Écris un bot, envoie-le : il affronte les autres bots en continu et grimpe au classement. Même puissance de calcul pour tous : c’est l’algorithme qui gagne, pas la machine.",
  create: "Créer mon bot",
  leaderboard: "Classement",
  bot: "Bot",
  author: "Auteur",
  rating: "Classement",
  division: "Division",
  games: "Parties",
  wdl: "V / D / N",
  house: "Maison",
  houseHint: "Bot du site, sert de repère",
  version: (v: number) => `v${v}`,
  provisional: "Classement provisoire (moins de 10 parties)",
  noGames: "pas encore de partie",
  empty: "Aucun bot de la communauté pour l’instant : sois le premier !",
  mine: "Mes bots",
  status: {
    pending: "En validation",
    active: "En lice",
    rejected: "Refusé",
    retired: "Retiré",
  } as Record<string, string>,
  how: {
    title: "Comment ça marche",
    steps: [
      "Ton bot est un petit programme WebAssembly : à chaque coup, il reçoit la position et la liste des coups légaux, et répond le coup qu’il choisit.",
      "À l’envoi, il est vérifié (il doit jouer deux parties sans faute), puis joue 10 parties de placement contre les 5 bots du site.",
      "Ensuite il affronte en continu des bots de niveau proche. Chaque carte est jouée deux fois, couleurs inversées.",
      "Le classement est recalculé sur toutes les parties de l’arène, ancré sur Galet = 920 comme celui des bots du site.",
    ],
  },
  // Page d'un bot
  by: "par",
  versions: "Versions",
  recent: "Dernières parties",
  noRecent: "Pas encore de partie : le runner passe régulièrement.",
  vs: "contre",
  plies: (n: number) => `${n} demi-coups`,
  result: { win: "Victoire", loss: "Défaite", draw: "Nulle" } as Record<string, string>,
  pendingNote: "En attente de validation : le runner de l’arène passe environ toutes les 30 minutes.",
  queued: (n: number) => `${n} partie(s) en file d’attente`,
  rejectedNote: "Ce bot a été refusé :",
  retire: "Retirer de l’arène",
  retireConfirm: "Retirer ce bot ? Il ne jouera plus (ses parties restent visibles).",
  margin: (m: number) => `± ${m}`,
  notFound: "Bot introuvable.",
  sha: "Empreinte",
  size: (kb: number) => `${kb} Ko`,
  // Création
  newTitle: "Créer un bot",
  newIntro: "Un bot de l’arène est un module WebAssembly (.wasm). Le plus simple : partir du bot de départ en Rust, qui est le bot du site lui-même.",
  quick: "Démarrage rapide (Rust)",
  quickSteps: [
    "Crée un crate qui dépend du SDK (traversal-bot). Pour aller plus loin, copie le bot de départ du dépôt (bots/starter) : c’est Mont Blanc, borné par le fuel.",
    "Compile-le en WebAssembly :",
    "Mesure-le contre un bot du site, avec l’outil de test du dépôt (Docker) :",
    "Envoie le fichier .wasm ci-dessous.",
  ],
  rules: "Les règles du jeu en bac à sable",
  limits: (fuelM: number, memMb: number, kb: number) => [
    `${(fuelM / 1000).toLocaleString("fr-FR")} milliards de « fuel » par coup (≈ instructions WebAssembly). À zéro, la partie est perdue. fuel_left() dit ce qu’il reste.`,
    `${memMb} Mo de mémoire au plus, module de ${kb / 1024} Mo au plus.`,
    "Aucun accès au système : ni fichiers, ni réseau, ni horloge. Le hasard vient de la graine fournie à chaque coup : une partie se rejoue à l’identique.",
    "Un plantage ou un coup inexistant fait perdre la partie.",
  ],
  abi: "Autres langages (C, Zig, Go…)",
  abiIntro: "Sans le SDK, le module doit exposer :",
  abiExports: [
    "memory — la mémoire du module ;",
    "traversal_buffer() → i32 : adresse d’un tampon de 16 Ko où l’arène écrit chaque tour ;",
    "traversal_move(len: i32) → i32 : lit le tour (len octets) et renvoie l’indice du coup choisi.",
  ],
  abiImports: "Imports permis (module « traversal ») : fuel_left() → i64 et log(ptr: i32, len: i32). Tout autre import est refusé.",
  abiFormat: "Format du tour (petit-boutiste) :",
  abiTable: `0    u8        version (1)
1    u8        camp au trait (1 rouge, 2 bleu)
2    u16       demi-coups joués
4    u16       limite de demi-coups
6    u8 × 2    scores rouge, bleu
8    u8        pièces sorties
9    u8        nombre de pièces n
10   u64       graine de ce coup
18   u64       fuel de ce coup
26   u8 × 100  relief (case = y × 10 + x)
126  n × 3     pièces : camp, type (0 Explorateur,
               1 Avant-garde, 2 Sentinelle), case
..   u16       nombre de coups m
..   m × 8     coups : pièce, type (0 déplacement,
               1 attaque, 2 sortie, 3 passe), case,
               spécial (0, 1 diag., 2 bond), coût,
               attaque, défense, 0
               (255 = aucune pièce / aucune case)`,
  upload: "Envoyer un bot",
  name: "Nom du bot",
  namePlaceholder: "ex. Avalanche",
  nameHint: "3 à 24 caractères.",
  kind: "Ce fichier est…",
  kindNew: "Un nouveau bot",
  kindUpdate: "Une mise à jour",
  pickBot: "Bot à mettre à jour",
  updateHint: "Le fichier devient la version suivante du bot choisi et remplace sa version actuelle une fois validé.",
  update: "Mettre à jour",
  file: "Fichier .wasm",
  send: "Envoyer",
  sending: "Envoi…",
  needAccount: "Il faut un compte pour inscrire un bot.",
  signup: "Créer un compte",
  tooBig: (kb: number) => `Fichier trop gros (${kb} Ko au plus).`,
  limitsNote: (n: number) => `Au plus ${n} bots en lice par joueur.`,
};

const en: typeof fr = {
  title: "Bot arena",
  home: {
    title: "Write a bot.",
    accent: "It plays for you.",
    lead: "Traversal is a strategy game on a relief board. Code your bot, enter it in the arena: it plays the other bots day and night and climbs the leaderboard.",
    createSub: "Rust SDK, or any language that compiles to WebAssembly",
    board: "Bot leaderboard",
    boardSub: (n: number) => (n === 0 ? "Be the first community bot" : `${n} community bot${n > 1 ? "s" : ""} competing`),
    rules: "Game rules",
    rulesSub: "10 × 10 relief board, three pieces, one race",
    sdk: "The SDK on GitHub",
    sdkSub: "Examples, starter bot, local test tool",
    top: "Arena leaders",
    fullBoard: "Full leaderboard",
  },
  homeReplay: {
    ply: (i: number, n: number) => `ply ${i}/${n}`,
    open: "Replay",
  },
  intro:
    "Write a bot, upload it: it plays the other bots non-stop and climbs the leaderboard. Same computing power for everyone: the algorithm wins, not the hardware.",
  create: "Create my bot",
  leaderboard: "Leaderboard",
  bot: "Bot",
  author: "Author",
  rating: "Rating",
  division: "Division",
  games: "Games",
  wdl: "W / L / D",
  house: "House",
  houseHint: "Site bot, used as a yardstick",
  version: (v: number) => `v${v}`,
  provisional: "Provisional rating (fewer than 10 games)",
  noGames: "no games yet",
  empty: "No community bots yet: be the first!",
  mine: "My bots",
  status: {
    pending: "Validating",
    active: "Competing",
    rejected: "Rejected",
    retired: "Retired",
  },
  how: {
    title: "How it works",
    steps: [
      "Your bot is a small WebAssembly program: on each move it gets the position and the list of legal moves, and answers the move it picks.",
      "On upload it is checked (it must play two games without fault), then plays 10 placement games against the 5 site bots.",
      "Then it keeps playing bots of similar strength. Each map is played twice, with colours swapped.",
      "The rating is recomputed over every arena game, anchored on Pebble = 920 like the site bots.",
    ],
  },
  by: "by",
  versions: "Versions",
  recent: "Recent games",
  noRecent: "No games yet: the runner comes by regularly.",
  vs: "vs",
  plies: (n: number) => `${n} plies`,
  result: { win: "Win", loss: "Loss", draw: "Draw" },
  pendingNote: "Waiting for validation: the arena runner comes by about every 30 minutes.",
  queued: (n: number) => `${n} game(s) queued`,
  rejectedNote: "This bot was rejected:",
  retire: "Retire from the arena",
  retireConfirm: "Retire this bot? It will stop playing (its games stay visible).",
  margin: (m: number) => `± ${m}`,
  notFound: "Bot not found.",
  sha: "Fingerprint",
  size: (kb: number) => `${kb} KB`,
  newTitle: "Create a bot",
  newIntro: "An arena bot is a WebAssembly module (.wasm). The easiest way: start from the Rust starter bot, which is the site’s own bot.",
  quick: "Quick start (Rust)",
  quickSteps: [
    "Create a crate that depends on the SDK (traversal-bot). To go further, copy the repository’s starter bot (bots/starter): it is Mont Blanc, bounded by fuel.",
    "Compile it to WebAssembly:",
    "Measure it against a site bot with the repository’s test tool (Docker):",
    "Upload the .wasm file below.",
  ],
  rules: "Sandbox rules",
  limits: (fuelM: number, memMb: number, kb: number) => [
    `${(fuelM / 1000).toLocaleString("en-US")} billion “fuel” per move (≈ WebAssembly instructions). At zero, the game is lost. fuel_left() tells what is left.`,
    `${memMb} MB of memory at most, ${kb / 1024} MB module at most.`,
    "No access to the system: no files, no network, no clock. Randomness comes from the seed given on each move: a game replays identically.",
    "A crash or a non-existent move loses the game.",
  ],
  abi: "Other languages (C, Zig, Go…)",
  abiIntro: "Without the SDK, the module must export:",
  abiExports: [
    "memory — the module memory;",
    "traversal_buffer() → i32: address of a 16 KB buffer where the arena writes each turn;",
    "traversal_move(len: i32) → i32: reads the turn (len bytes) and returns the index of the chosen move.",
  ],
  abiImports: "Allowed imports (module “traversal”): fuel_left() → i64 and log(ptr: i32, len: i32). Any other import is rejected.",
  abiFormat: "Turn format (little-endian):",
  abiTable: `0    u8        version (1)
1    u8        side to move (1 red, 2 blue)
2    u16       plies played
4    u16       ply limit
6    u8 × 2    scores red, blue
8    u8        pieces exited
9    u8        piece count n
10   u64       seed for this move
18   u64       fuel for this move
26   u8 × 100  heights (square = y × 10 + x)
126  n × 3     pieces: side, kind (0 Explorer,
               1 Vanguard, 2 Sentinel), square
..   u16       move count m
..   m × 8     moves: piece, kind (0 move, 1 attack,
               2 exit, 3 pass), square, special
               (0, 1 diagonal, 2 leap), cost,
               attack, defense, 0
               (255 = no piece / no square)`,
  upload: "Upload a bot",
  name: "Bot name",
  namePlaceholder: "e.g. Avalanche",
  nameHint: "3 to 24 characters.",
  kind: "This file is…",
  kindNew: "A new bot",
  kindUpdate: "An update",
  pickBot: "Bot to update",
  updateHint: "The file becomes the next version of the chosen bot and replaces its current version once validated.",
  update: "Update",
  file: ".wasm file",
  send: "Upload",
  sending: "Uploading…",
  needAccount: "You need an account to enter a bot.",
  signup: "Create an account",
  tooBig: (kb: number) => `File too large (${kb} KB max).`,
  limitsNote: (n: number) => `At most ${n} competing bots per player.`,
};

export default { fr, en };
