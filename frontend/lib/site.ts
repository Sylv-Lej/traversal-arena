// Arène seule (défaut) ou site complet (`FULL_SITE=1`) : jouer, puzzles, regarder,
// classement des joueurs, matchs. Côté serveur seulement (variable d'environnement lue à
// chaque requête) : rouvrir le site = changer la variable, sans rebuild.
//
// Fermé quand FULL_SITE n'est pas activé :
// - les PAGES `/play`, `/puzzles/**`, `/watch`, `/leaderboard`, `/match/**` : redirigées vers
//   l'accueil (`middleware.ts`) ;
// - leurs ROUTES D'API, dans le relais (`closedApi`) : le relais est le seul à détenir la
//   clé d'API, donc personne d'autre ne peut les appeler ;
// - leurs onglets, grisés (`Shell`).
// Restent ouverts : l'arène, les règles (et leur bac à sable), les comptes, les profils, les
// rangs, et la relecture des parties existantes (dont celles de l'arène).

export function fullSite(): boolean {
  return process.env.FULL_SITE === "1";
}

// Créer une partie, matchmaking, matchs, puzzles, classement des joueurs, parties en cours.
const CLOSED = /^(games|games\/live|me\/games|leaderboard|lobby(\/seek)?|matches(\/.*)?|puzzles(\/.*)?)$/;
// D'une partie existante, on garde la lecture (et le bilan) ; pas les coups ni les actions.
const GAME_READ = /^games\/[\w-]+(\/(history|stream|analysis|analysis\/stream))?$/;

/** Route d'API (chemin sous /api, sans la requête) fermée hors site complet ? */
export function closedApi(sub: string): boolean {
  if (fullSite()) return false;
  return CLOSED.test(sub) || (sub.startsWith("games/") && !GAME_READ.test(sub));
}
