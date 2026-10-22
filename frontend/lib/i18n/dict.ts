// Tous les textes du site, par langue. Chaque espace de noms (`ns/*.ts`) définit `fr`
// (référence) et `en` (mêmes clés, vérifié par TypeScript).
import type { Lang } from "./core";
import common from "./ns/common";
import shell from "./ns/shell";
import home from "./ns/home";
import auth from "./ns/auth";
import profile from "./ns/profile";
import leaderboard from "./ns/leaderboard";
import play from "./ns/play";
import game from "./ns/game";
import analysis from "./ns/analysis";
import board from "./ns/board";
import rules from "./ns/rules";
import ranks from "./ns/ranks";
import watch from "./ns/watch";
import match from "./ns/match";
import puzzles from "./ns/puzzles";
import arena from "./ns/arena";

const fr = {
    common: common.fr,
    shell: shell.fr,
    home: home.fr,
    auth: auth.fr,
    profile: profile.fr,
    leaderboard: leaderboard.fr,
    play: play.fr,
    game: game.fr,
    analysis: analysis.fr,
    board: board.fr,
    rules: rules.fr,
    ranks: ranks.fr,
    watch: watch.fr,
    match: match.fr,
    puzzles: puzzles.fr,
    arena: arena.fr,
};

export type Dict = typeof fr;

export const DICTS: Record<Lang, Dict> = {
  fr,
  en: {
    common: common.en,
    shell: shell.en,
    home: home.en,
    auth: auth.en,
    profile: profile.en,
    leaderboard: leaderboard.en,
    play: play.en,
    game: game.en,
    analysis: analysis.en,
    board: board.en,
    rules: rules.en,
    ranks: ranks.en,
    watch: watch.en,
    match: match.en,
    puzzles: puzzles.en,
    arena: arena.en,
  },
};
