//! Moteur de l'ANALYSE DE PARTIE : il note les coups (backend : `app/analysis.py`, via le
//! module `traversal_rs` ; runner de l'arène : `arena/src/analyse.rs`, où le n°1 de
//! l'arène propose les coups et orque les note).
//!
//! C'est le bot « orque » (93 % contre Mont Blanc), recopié depuis
//! le dépôt du SDK (`bots/custom/orque`, bot personnel, non publié) ; ce crate n'est pas
//! publié non plus. Ajouts : `analyse` (meilleur coup ET score du coup joué, même
//! recherche, budget de nœuds fixe). Le code du bot n'est compilé qu'en WebAssembly.
//! Si orque évolue là-bas, recopier `lib.rs` (sauf `analyse`), `eval.rs` et `gen.rs`.
//!
//! Bot « orque » (le prédateur de la morue) : la recherche de `morue` (idées de
//! Stockfish), en deux fois plus de nœuds par coup, plus les parades.
//!
//! - l'évaluation de Mont Blanc, à l'identique, mais en version rapide (`eval`, reprise de
//!   `rapide`) ;
//! - un générateur de coups plus rapide que celui du moteur, mêmes coups (`gen`) ; la
//!   recherche de calme n'y produit que les sorties et les attaques ;
//! - les coups qui barrent le chemin du coureur adverse passent devant dans l'ordre des
//!   coups, et quelques-uns échappent toujours à l'élagage.
//!
//! La recherche, reprise de `morue` :
//!
//! - **approfondissement itératif** et **fenêtres d'aspiration** autour du score précédent ;
//! - **PVS** (Principal Variation Search) : le premier coup avec la fenêtre complète, les
//!   autres avec une fenêtre nulle, revus seulement s'ils la dépassent ;
//! - **table de transposition** (hachage de Zobrist), gardée d'un coup à l'autre pendant
//!   la partie : meilleur coup, score et bornes de chaque position déjà vue ;
//! - **ordre des coups** : coup de la table, sorties, captures (victime la plus forte
//!   d'abord), coups « killer », puis historique et avance vers la sortie ;
//! - **null move** : si passer son tour suffit déjà à dépasser beta, inutile de chercher ;
//! - **LMR** (réductions des derniers coups), **late move pruning** et **futility** : les
//!   coups calmes mal classés sont explorés moins profond, ou pas du tout, près des feuilles ;
//! - **recherche de calme** : sorties et captures jusqu'à une position stable.
//!
//! La recherche s'arrête quand le fuel descend sous une petite réserve ; le meilleur coup
//! de la dernière itération (ou de l'itération en cours, s'il l'a déjà battu) est joué.
//!
//! ```text
//! cargo build --release --target wasm32-unknown-unknown
//! # -> target/wasm32-unknown-unknown/release/traversal_orque_bot.wasm
//! ```

use std::sync::Mutex;

use traversal_bot::core::bot::WIN;
use traversal_bot::core::config::SQUARES;
use traversal_bot::core::state::NONE;
use traversal_bot::core::{apply_move, legal_moves, Kind, Move, MoveKind, State};
use traversal_bot::fuel_left;
#[cfg(target_arch = "wasm32")]
use traversal_bot::{bot, index_of, log, Turn};

pub mod eval;
pub mod gen;
use eval::Eval;
use gen::Gen;

const INF: i32 = 1_000_000;
/// Au-delà, le score est une victoire ou une défaite forcée.
const DECIDED: i32 = WIN / 2;
const MAX_PLY: usize = 96;
const MAX_DEPTH: i32 = 40;
/// Profondeur de la recherche de calme (sorties et captures).
const QPLIES: u8 = 4;
const TT_SIZE: usize = 1 << 19;
const EVAL_SIZE: usize = 1 << 16;

/// Marges des élagages, en unités d'évaluation (une Sentinelle sortie vaut 300).
const RFP_MARGIN: i32 = 70;
const FUTILITY_MARGIN: i32 = 90;
const ASPIRATION: i32 = 40;
/// Coups calmes qui barrent le coureur adverse : bonus d'ordre, et combien échappent au
/// late move pruning.
const GUARD_BONUS: i32 = 3000;
const GUARDS: usize = 2;

// ---------------------------------------------------------------------------------------
// Hachage de Zobrist

const fn splitmix(x: u64) -> u64 {
    let mut z = x.wrapping_add(0x9E37_79B9_7F4A_7C15);
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^ (z >> 31)
}

/// Une clé par (camp, type, case).
static ZOBRIST: [u64; 6 * SQUARES] = {
    let mut t = [0; 6 * SQUARES];
    let mut i = 0;
    while i < t.len() {
        t[i] = splitmix(0x5EED_0000 + i as u64);
        i += 1;
    }
    t
};

fn kind_index(k: Kind) -> usize {
    match k {
        Kind::Explorer => 0,
        Kind::Vanguard => 1,
        Kind::Sentinel => 2,
    }
}

/// Clé de la position : pièces, trait, scores, sorties, et demi-coups restants quand la
/// limite approche (la partie s'y arrête, la même position n'a plus la même valeur).
fn hash(s: &State) -> u64 {
    let mut h = 0;
    for p in s.pieces() {
        h ^= ZOBRIST[((p.owner as usize - 1) * 3 + kind_index(p.kind)) * SQUARES + p.sq as usize];
    }
    let left = s.move_limit.saturating_sub(s.ply).min(63) as u64;
    let extra = s.to_move as u64 | (s.scores[0] as u64) << 2 | (s.scores[1] as u64) << 8 | (s.finished as u64) << 14 | left << 18;
    h ^ splitmix(extra)
}

// ---------------------------------------------------------------------------------------
// Coups compacts : indépendants de l'ordre des pièces (qui change à chaque capture), donc
// valables d'une position à sa transposée.

type Key = u32;
const NO_KEY: Key = u32::MAX;

fn key_of(s: &State, m: &Move) -> Key {
    let from = if m.piece == NONE { NONE } else { s.piece(m.piece).sq };
    (from as u32) << 16 | (m.kind as u32) << 8 | m.to as u32
}

// ---------------------------------------------------------------------------------------
// Table de transposition

const EXACT: u8 = 0;
const LOWER: u8 = 1;
const UPPER: u8 = 2;

#[derive(Clone, Copy)]
struct Entry {
    key: u64,
    mv: Key,
    score: i32,
    depth: i8,
    bound: u8,
}

const EMPTY: Entry = Entry { key: 0, mv: NO_KEY, score: 0, depth: -1, bound: EXACT };

// ---------------------------------------------------------------------------------------
// Moteur

struct Engine {
    heights: [u8; SQUARES],
    ev: Eval,
    gen: Gen,
    tt: Vec<Entry>,
    evals: Vec<(u64, i32)>,
    killers: [[Key; 2]; MAX_PLY],
    /// Historique des coups calmes qui ont coupé : [camp][type][case d'arrivée].
    history: [[[i32; SQUARES]; 3]; 2],
    lmr: [[u8; 64]; 64],
    nodes: u64,
    max_nodes: u64,
    reserve: u64,
    stopped: bool,
    best_root: Option<Move>,
    last_ply: u16,
}

impl Engine {
    fn new(heights: [u8; SQUARES]) -> Engine {
        let mut lmr = [[0u8; 64]; 64];
        for (d, row) in lmr.iter_mut().enumerate().skip(1) {
            for (n, r) in row.iter_mut().enumerate().skip(1) {
                *r = (0.5 + (d as f64).ln() * (n as f64).ln() / 2.25) as u8;
            }
        }
        Engine {
            heights,
            ev: Eval::new(&heights),
            gen: Gen::new(&heights),
            tt: vec![EMPTY; TT_SIZE],
            evals: vec![(0, 0); EVAL_SIZE],
            killers: [[NO_KEY; 2]; MAX_PLY],
            history: [[[0; SQUARES]; 3]; 2],
            lmr,
            nodes: 0,
            max_nodes: u64::MAX,
            reserve: 0,
            stopped: false,
            best_root: None,
            last_ply: 0,
        }
    }

    /// Compte un nœud ; vrai s'il faut tout arrêter (fuel presque épuisé).
    fn tick(&mut self) -> bool {
        self.nodes += 1;
        if !self.stopped && (self.nodes >= self.max_nodes || fuel_left() < self.reserve) {
            self.stopped = true;
        }
        self.stopped
    }

    /// Évaluation (du point de vue du camp au trait), mise en cache.
    fn eval(&mut self, s: &State, key: u64) -> i32 {
        if s.over {
            return self.ev.evaluate(s, s.to_move);
        }
        let slot = &mut self.evals[key as usize % EVAL_SIZE];
        if slot.0 == key {
            return slot.1;
        }
        let v = self.ev.evaluate(s, s.to_move);
        self.evals[key as usize % EVAL_SIZE] = (key, v);
        v
    }

    fn probe(&self, key: u64) -> Option<Entry> {
        let e = self.tt[key as usize % TT_SIZE];
        (e.key == key).then_some(e)
    }

    fn store(&mut self, key: u64, depth: i32, score: i32, bound: u8, mv: Key) {
        let slot = &mut self.tt[key as usize % TT_SIZE];
        // Remplacement : toujours, sauf une entrée plus profonde de la même position.
        if slot.key != key || depth >= slot.depth as i32 || bound == EXACT {
            let mv = if mv == NO_KEY && slot.key == key { slot.mv } else { mv };
            *slot = Entry { key, mv, score, depth: depth as i8, bound };
        }
    }

    /// Cases sur un plus court chemin (relief seul) du coureur adverse le plus rapide :
    /// s'y placer le ralentit. Ces parades ne sont jamais élaguées d'emblée.
    fn guard_squares(&self, s: &State) -> [bool; SQUARES] {
        let mut out = [false; SQUARES];
        let them = if s.to_move == 1 { 2 } else { 1 };
        let Some(runner) = s.pieces().iter().filter(|p| p.owner == them).min_by_key(|p| {
            let m = p.kind.movement() as i32;
            (self.ev.cost(them, p.sq) + m - 1) / m
        }) else {
            return out;
        };
        let total = self.ev.cost(them, runner.sq);
        let from = &self.ev.between[runner.sq as usize];
        for (sq, g) in out.iter_mut().enumerate() {
            *g = sq != runner.sq as usize && from[sq] as i32 + self.ev.cost(them, sq as u8) == total;
        }
        out
    }

    /// Coups triés, les plus prometteurs d'abord : (coup, clé, tactique, parade).
    /// `tactical` : sorties et attaques seulement (recherche de calme).
    fn ordered(&self, s: &State, tt_move: Key, ply: usize, tactical_only: bool) -> Vec<(Move, Key, bool, bool)> {
        let killers = if ply < MAX_PLY { self.killers[ply] } else { [NO_KEY; 2] };
        let side = s.to_move as usize - 1;
        let guard = if tactical_only { [false; SQUARES] } else { self.guard_squares(s) };
        let mut scored: Vec<(i32, Move, Key, bool, bool)> = self
            .gen
            .moves(s, tactical_only)
            .into_iter()
            .map(|m| {
                let k = key_of(s, &m);
                let g = m.kind == MoveKind::Move && guard[m.to as usize];
                let (score, tactical) = if k == tt_move {
                    (10_000_000, m.kind != MoveKind::Move)
                } else {
                    match m.kind {
                        MoveKind::Exit => (9_000_000 + s.piece(m.piece).kind.strength() as i32, true),
                        MoveKind::Attack => {
                            let victim = s.piece(s.at(m.to).expect("cible")).kind.strength() as i32;
                            let attacker = s.piece(m.piece).kind.strength() as i32;
                            (8_000_000 + 10 * victim - attacker, true)
                        }
                        MoveKind::Pass => (0, false),
                        MoveKind::Move if k == killers[0] => (7_000_000, false),
                        MoveKind::Move if k == killers[1] => (6_900_000, false),
                        MoveKind::Move => {
                            let p = s.piece(m.piece);
                            let c = &self.ev.costs[side];
                            let progress = c[p.sq as usize] as i32 - c[m.to as usize] as i32;
                            let parry = if g { GUARD_BONUS } else { 0 };
                            (progress * 400 * p.kind.strength() as i32 + parry + self.history[side][kind_index(p.kind)][m.to as usize], false)
                        }
                    }
                };
                (score, m, k, tactical, g)
            })
            .collect();
        scored.sort_by_key(|e| std::cmp::Reverse(e.0));
        scored.into_iter().map(|(_, m, k, t, g)| (m, k, t, g)).collect()
    }

    fn reward(&mut self, s: &State, m: &Move, k: Key, depth: i32, ply: usize, tried: &[(Kind, u8)]) {
        if ply < MAX_PLY && self.killers[ply][0] != k {
            self.killers[ply] = [k, self.killers[ply][0]];
        }
        let side = s.to_move as usize - 1;
        let bonus = (depth * depth * 16).min(4000);
        let p = s.piece(m.piece);
        let h = &mut self.history[side][kind_index(p.kind)][m.to as usize];
        *h += bonus - *h * bonus / 16_000;
        // Les coups calmes essayés avant, qui n'ont pas coupé, reculent.
        for &(kind, to) in tried {
            let h = &mut self.history[side][kind_index(kind)][to as usize];
            *h -= bonus + *h * bonus / 16_000;
        }
    }

    fn search(&mut self, s: &State, mut depth: i32, mut alpha: i32, beta: i32, ply: usize, null_ok: bool) -> i32 {
        if s.over {
            return self.ev.evaluate(s, s.to_move);
        }
        if depth <= 0 || ply >= MAX_PLY - QPLIES as usize - 1 {
            return self.quiesce(s, alpha, beta, QPLIES);
        }
        if self.tick() {
            return 0;
        }
        let pv = beta - alpha > 1;
        let key = hash(s);
        let entry = self.probe(key);
        let tt_move = entry.map_or(NO_KEY, |e| e.mv);
        if let Some(e) = entry {
            if !pv && ply > 0 && e.depth as i32 >= depth {
                let fits = match e.bound {
                    EXACT => true,
                    LOWER => e.score >= beta,
                    _ => e.score <= alpha,
                };
                if fits {
                    return e.score;
                }
            }
        }
        // Pas de coup de la table pour guider : une recherche réduite en trouve un (IIR).
        if tt_move == NO_KEY && depth >= 4 {
            depth -= 1;
        }

        let eval = self.eval(s, key);
        if !pv && ply > 0 && eval.abs() < DECIDED {
            // Reverse futility : même avec une marge, la position dépasse déjà beta.
            if depth <= 3 && eval - RFP_MARGIN * depth >= beta {
                return eval;
            }
            // Null move : on laisse le trait à l'adversaire ; s'il ne fait toujours pas
            // descendre sous beta, la position est assez bonne pour couper.
            if null_ok && depth >= 3 && eval >= beta && s.ply + 2 < s.move_limit {
                let mut null = s.clone();
                null.to_move = if s.to_move == 1 { 2 } else { 1 };
                null.ply += 1;
                let r = 2 + depth / 4;
                let v = -self.search(&null, depth - 1 - r, -beta, -beta + 1, ply + 1, false);
                if self.stopped {
                    return 0;
                }
                if v >= beta {
                    return if v >= DECIDED { beta } else { v };
                }
            }
        }

        let moves = self.ordered(s, tt_move, ply, false);
        let lmp = (3 + depth * depth) as usize;
        let (mut best, mut best_key, mut best_move) = (-INF, NO_KEY, None);
        let mut searched = 0usize;
        let mut quiets: Vec<(Kind, u8)> = Vec::new();
        let mut parries = 0;
        let alpha0 = alpha;
        for (m, k, tactical, guard) in moves {
            let quiet = !tactical && m.kind == MoveKind::Move;
            if !pv && searched > 0 && quiet && best > -DECIDED {
                // Late move pruning : au-delà de quelques coups calmes, on ne regarde plus
                // (sauf quelques parades).
                if quiets.len() >= lmp && !(guard && parries < GUARDS) {
                    continue;
                }
                if guard {
                    parries += 1;
                }
                // Futility : près des feuilles, un coup calme ne rattrapera pas ce retard.
                if depth <= 2 && eval + FUTILITY_MARGIN * depth <= alpha {
                    continue;
                }
            }
            let child = apply_move(s, &m);
            let mut v;
            if searched == 0 {
                v = -self.search(&child, depth - 1, -beta, -alpha, ply + 1, true);
            } else {
                let r = if depth >= 3 && quiet && searched >= 2 {
                    let mut r = self.lmr[depth.min(63) as usize][searched.min(63)] as i32;
                    if pv {
                        r -= 1;
                    }
                    if k == self.killers.get(ply).map_or(NO_KEY, |k| k[0]) {
                        r -= 1;
                    }
                    r.clamp(0, depth - 2)
                } else {
                    0
                };
                v = -self.search(&child, depth - 1 - r, -alpha - 1, -alpha, ply + 1, true);
                if v > alpha && r > 0 {
                    v = -self.search(&child, depth - 1, -alpha - 1, -alpha, ply + 1, true);
                }
                if v > alpha && v < beta {
                    v = -self.search(&child, depth - 1, -beta, -alpha, ply + 1, true);
                }
            }
            if self.stopped {
                return 0;
            }
            searched += 1;
            if v > best {
                best = v;
                best_key = k;
                best_move = Some(m);
                if v > alpha {
                    alpha = v;
                    if ply == 0 {
                        self.best_root = Some(m);
                    }
                    if alpha >= beta {
                        if quiet {
                            self.reward(s, &m, k, depth, ply, &quiets);
                        }
                        break;
                    }
                }
            }
            if quiet {
                quiets.push((s.piece(m.piece).kind, m.to));
            }
        }
        if best_move.is_none() {
            // Tout a été élagué (cas limite) : la note statique fait foi.
            return eval;
        }
        let bound = if best >= beta {
            LOWER
        } else if best > alpha0 {
            EXACT
        } else {
            UPPER
        };
        self.store(key, depth, best, bound, best_key);
        best
    }

    /// Recherche de calme : sorties et captures seulement ; le camp au trait peut aussi
    /// s'arrêter là (sa note statique sert de plancher).
    fn quiesce(&mut self, s: &State, mut alpha: i32, beta: i32, plies: u8) -> i32 {
        if s.over {
            return self.ev.evaluate(s, s.to_move);
        }
        let key = hash(s);
        let stand = self.eval(s, key);
        if plies == 0 || stand >= beta {
            return stand;
        }
        if self.tick() {
            return 0;
        }
        alpha = alpha.max(stand);
        let mut best = stand;
        for (m, ..) in self.ordered(s, NO_KEY, MAX_PLY, true) {
            let v = -self.quiesce(&apply_move(s, &m), -beta, -alpha, plies - 1);
            if self.stopped {
                return 0;
            }
            if v > best {
                best = v;
                if v > alpha {
                    alpha = v;
                    if alpha >= beta {
                        break;
                    }
                }
            }
        }
        best
    }

    /// Approfondissement itératif avec fenêtres d'aspiration ; renvoie (coup, profondeur, score).
    fn think(&mut self, s: &State) -> (Option<Move>, i32, i32) {
        self.nodes = 0;
        self.stopped = false;
        self.best_root = None;
        self.killers = [[NO_KEY; 2]; MAX_PLY];
        for h in self.history.iter_mut().flatten().flatten() {
            *h /= 2;
        }
        let (mut best, mut done, mut score) = (None, 0, 0);
        for depth in 1..=MAX_DEPTH {
            let mut delta = ASPIRATION;
            let (mut alpha, mut beta) = if depth >= 3 { (score - delta, score + delta) } else { (-INF, INF) };
            let v = loop {
                let v = self.search(s, depth, alpha, beta, 0, false);
                if self.stopped {
                    break v;
                }
                if v <= alpha {
                    alpha = (alpha - delta).max(-INF);
                } else if v >= beta {
                    beta = (beta + delta).min(INF);
                } else {
                    break v;
                }
                delta *= 3;
            };
            // Itération interrompue : son meilleur coup ne compte que s'il a battu l'ancien.
            if self.best_root.is_some() {
                best = self.best_root;
            }
            if self.stopped {
                break;
            }
            (done, score) = (depth, v);
            if v.abs() >= DECIDED {
                break; // issue forcée trouvée : inutile d'aller plus loin
            }
        }
        (best, done, score)
    }
}

static ENGINE: Mutex<Option<Engine>> = Mutex::new(None);

/// Le moteur de la partie en cours (nouveau à chaque partie : autre relief, ou retour au
/// début).
fn engine_for<'a>(slot: &'a mut Option<Engine>, s: &State) -> &'a mut Engine {
    let fresh = slot.as_ref().map_or(true, |e| e.heights != s.heights || s.ply < e.last_ply);
    if fresh {
        *slot = Some(Engine::new(s.heights));
    }
    let e = slot.as_mut().expect("moteur");
    e.last_ply = s.ply;
    e
}

/// Meilleur coup pour `s`, en `max_nodes` nœuds au plus (outils et tests natifs : hors
/// WebAssembly, le fuel est illimité).
pub fn best_move(s: &State, max_nodes: u64) -> Move {
    let mut slot = ENGINE.lock().unwrap_or_else(|e| e.into_inner());
    let e = engine_for(&mut slot, s);
    e.max_nodes = max_nodes;
    e.reserve = 0;
    e.think(s).0.unwrap_or_else(|| legal_moves(s)[0])
}

/// Bilan d'un coup joué : le meilleur coup et le score du coup joué, par la même recherche.
#[derive(Clone, Copy, Debug)]
pub struct Analysis {
    pub best: Move,
    /// Scores du point de vue du camp au trait.
    pub best_score: i32,
    pub played_score: i32,
    /// Profondeur nominale complètement explorée (0 : un seul coup possible).
    pub depth: i32,
}

/// Analyse de `played` dans `s`, en `max_nodes` nœuds au plus par recherche. Sans fuel ni
/// horloge : le résultat ne dépend que de la partie (la table de transposition est gardée
/// d'une position à la suivante, analysées dans l'ordre).
pub fn analyse(s: &State, played: &Move, max_nodes: u64) -> Analysis {
    let moves = legal_moves(s);
    if moves.len() <= 1 {
        return Analysis { best: moves.first().copied().unwrap_or(*played), best_score: 0, played_score: 0, depth: 0 };
    }
    let mut slot = ENGINE.lock().unwrap_or_else(|e| e.into_inner());
    let e = engine_for(&mut slot, s);
    e.max_nodes = max_nodes;
    e.reserve = 0;
    let (best, depth, score) = e.think(s);
    let best = best.unwrap_or(moves[0]);
    let same = best.piece == played.piece && best.kind == played.kind && best.to == played.to;
    if same || depth == 0 {
        return Analysis { best, best_score: score, played_score: score, depth };
    }
    // Le coup joué, à la profondeur atteinte et en fenêtre complète (un score exact) ; si le
    // budget n'y suffit pas, un cran moins profond.
    let child = apply_move(s, played);
    let mut played_score = -e.ev.evaluate(&child, child.to_move);
    for d in (1..=depth).rev() {
        e.nodes = 0;
        e.stopped = false;
        let v = -e.search(&child, d - 1, -INF, INF, 1, true);
        if !e.stopped {
            played_score = v;
            break;
        }
    }
    // Le meilleur coup est le meilleur (la recherche du coup joué peut aller plus loin).
    Analysis { best, best_score: score.max(played_score), played_score, depth }
}

#[cfg(target_arch = "wasm32")]
fn choose(turn: &Turn) -> usize {
    if turn.moves.len() <= 1 {
        return 0;
    }
    let mut slot = ENGINE.lock().unwrap_or_else(|e| e.into_inner());
    let e = engine_for(&mut slot, &turn.state);
    // De quoi rendre la main proprement : un nœud coûte au plus quelques millions de fuel.
    e.reserve = turn.fuel / 40;
    e.max_nodes = u64::MAX;
    let (mv, depth, score) = e.think(&turn.state);
    log(&format!(
        "demi-coup {} : profondeur {depth}, score {score}, {} nœuds, fuel restant {} M",
        turn.state.ply,
        e.nodes,
        fuel_left() / 1_000_000
    ));
    mv.map_or(0, |m| index_of(turn, &m))
}

#[cfg(target_arch = "wasm32")]
bot!(choose);

#[cfg(test)]
mod tests {
    use super::*;
    use traversal_bot::core::{new_game, Piece};

    fn flat() -> [u8; SQUARES] {
        [1; SQUARES]
    }

    #[test]
    fn takes_the_winning_exit() {
        let pieces = [Piece { owner: 1, kind: Kind::Sentinel, sq: 94 }, Piece { owner: 2, kind: Kind::Sentinel, sq: 5 }];
        let s = State::new(flat(), &pieces, 1, 10, [0, 0], 0, 200);
        assert_eq!(best_move(&s, 5_000).kind, MoveKind::Exit);
    }

    #[test]
    fn stops_the_enemy_runner() {
        // La Sentinelle bleue sort au prochain coup (rangée 1, sortie en 0) et gagne (R8.2) :
        // seule parade, l'abattre avec la Sentinelle rouge juste derrière (3 contre 3).
        let pieces = [
            Piece { owner: 1, kind: Kind::Sentinel, sq: 24 },
            Piece { owner: 1, kind: Kind::Explorer, sq: 30 },
            Piece { owner: 2, kind: Kind::Sentinel, sq: 14 },
            Piece { owner: 2, kind: Kind::Explorer, sq: 87 },
        ];
        let s = State::new(flat(), &pieces, 1, 10, [0, 0], 0, 200);
        let m = best_move(&s, 20_000);
        assert_eq!((m.kind, m.to), (MoveKind::Attack, 14));
    }

    #[test]
    fn analysis_scores_best_and_played_moves() {
        let pieces = [Piece { owner: 1, kind: Kind::Sentinel, sq: 84 }, Piece { owner: 2, kind: Kind::Explorer, sq: 45 },
                      Piece { owner: 1, kind: Kind::Explorer, sq: 20 }];
        let s = State::new(flat(), &pieces, 1, 10, [0, 0], 0, 200);
        let moves = legal_moves(&s);
        let best = analyse(&s, &moves[0], 20_000).best;
        let a = analyse(&s, &best, 20_000);
        assert_eq!(a.best_score, a.played_score);
        for m in &moves {
            let a = analyse(&s, m, 20_000);
            assert!(a.best_score >= a.played_score, "{m:?} {a:?}");
        }
    }

    #[test]
    fn plays_a_full_game_against_itself() {
        let mut heights = [0u8; SQUARES];
        for (i, h) in heights.iter_mut().enumerate() {
            *h = ((i * 7 + i / 10 * 3) % 4) as u8;
        }
        let mut s = new_game(heights);
        while !s.over {
            let m = best_move(&s, 3_000);
            assert!(legal_moves(&s).contains(&m));
            s = apply_move(&s, &m);
        }
    }
}
