//! L'évaluation de Mont Blanc (`Ctx::evaluate`, compréhension 3, réglages par défaut),
//! à l'identique mais plusieurs fois moins chère : les Dijkstra « avec obstacles » passent
//! d'un tas binaire à une file à seaux (les coûts d'arête sont des petits entiers).

use traversal_bot::core::bot::{exit_costs, WIN};
use traversal_bot::core::config::{Kind, SIZE, SQUARES};
use traversal_bot::core::movegen::{neighbors_of, step_cost};
use traversal_bot::core::state::{State, MAX_PIECES};

// `Tuning::default()` : réglages des bots du site.
const ALLY: u16 = 2;
const SOFT: u16 = 2;
const DETOUR: i32 = 6;
const SRACE: i32 = 150;
const SRACE_HORIZON: i32 = 5;

/// Plus grand coût d'arête : marche (≤ 7) + pièce à écarter ou abattre (2).
const RING: usize = 16;

pub struct Eval {
    pub costs: [[u16; SQUARES]; 2],
    /// Coût minimal entre deux cases (relief seul), pour les parades.
    pub between: Vec<[u16; SQUARES]>,
    step: [[u8; 4]; SQUARES],
}

impl Eval {
    pub fn new(heights: &[u8; SQUARES]) -> Eval {
        let mut step = [[0u8; 4]; SQUARES];
        for sq in 0..SQUARES as u8 {
            for (k, &nb) in neighbors_of(sq).iter().enumerate() {
                step[sq as usize][k] = step_cost(heights, sq, nb);
            }
        }
        let mut e = Eval { costs: [exit_costs(heights, 1), exit_costs(heights, 2)], between: Vec::new(), step };
        e.between = (0..SQUARES as u8).map(|sq| e.dijkstra(&[sq], 0, |_| 0, |_| false)).collect();
        e
    }

    #[inline]
    pub fn cost(&self, owner: u8, sq: u8) -> i32 {
        self.costs[owner as usize - 1][sq as usize] as i32
    }

    /// Dijkstra à seaux depuis `sources` (distance initiale `d0`) : `enter(c)` est le coût
    /// d'entrée sur `c`, `wall(c)` interdit `c`. Arête nb → cur : la marche de nb vers cur
    /// (le relief étant symétrique, c'est celle de cur vers nb).
    fn dijkstra(&self, sources: &[u8], d0: u16, enter: impl Fn(u8) -> u16, wall: impl Fn(u8) -> bool) -> [u16; SQUARES] {
        let mut dist = [u16::MAX; SQUARES];
        let mut ring = [[0u8; SQUARES]; RING];
        let mut len = [0usize; RING];
        let mut pending = 0;
        for &s in sources {
            if !wall(s) {
                dist[s as usize] = d0;
                let b = d0 as usize % RING;
                ring[b][len[b]] = s;
                len[b] += 1;
                pending += 1;
            }
        }
        let mut d = d0 as usize;
        while pending > 0 {
            let b = d % RING;
            let mut k = 0;
            while k < len[b] {
                let cur = ring[b][k];
                k += 1;
                pending -= 1;
                if dist[cur as usize] as usize != d {
                    continue;
                }
                let extra = enter(cur);
                for (j, &nb) in neighbors_of(cur).iter().enumerate() {
                    if wall(nb) {
                        continue;
                    }
                    let nd = d as u16 + self.step[cur as usize][j] as u16 + extra;
                    if nd < dist[nb as usize] {
                        dist[nb as usize] = nd;
                        let nb_b = nd as usize % RING;
                        ring[nb_b][len[nb_b]] = nb;
                        len[nb_b] += 1;
                        pending += 1;
                    }
                }
            }
            len[b] = 0;
            d += 1;
        }
        dist
    }

    /// Comme `blocked_costs` du bot du site : une Sentinelle adverse est un mur, traverser
    /// une autre pièce (adverse ou alliée) coûte 2.
    fn blocked(&self, owner: u8, occ: &[u8; SQUARES]) -> [u16; SQUARES] {
        let row = if owner == 1 { SIZE - 1 } else { 0 };
        let sources: [u8; SIZE] = std::array::from_fn(|x| (row * SIZE + x) as u8);
        // occ : 0 vide, sinon 1 + camp * 3 + type (camp 0 ou 1).
        let enemy_sentinel = 1 + (2 - owner) * 3 + 2;
        self.dijkstra(&sources, 1, |c| if occ[c as usize] == 0 { 0 } else if (occ[c as usize] - 1) / 3 == owner - 1 { ALLY } else { SOFT }, |c| occ[c as usize] == enemy_sentinel)
    }

    pub fn evaluate(&self, s: &State, side: u8) -> i32 {
        if s.over {
            return match s.winner {
                None => 0,
                Some(w) if w == side => WIN - s.ply as i32,
                Some(_) => -WIN + s.ply as i32,
            };
        }
        let mut occ = [0u8; SQUARES];
        for p in s.pieces() {
            occ[p.sq as usize] = 1 + (p.owner - 1) * 3 + kind_index(p.kind);
        }
        let blocked = [self.blocked(1, &occ), self.blocked(2, &occ)];
        let nobody_out = s.finished == 0;
        let other = 3 - side;
        let mut total = 100 * (s.scores[side as usize - 1] as i32 - s.scores[other as usize - 1] as i32);
        let mut first = [i32::MAX; 2];
        let mut sentinel = [i32::MAX; 2];
        let mut turns = [0i32; MAX_PIECES];
        for (i, p) in s.pieces().iter().enumerate() {
            let o = p.owner as usize - 1;
            let free = self.costs[o][p.sq as usize] as i32;
            let cost = (blocked[o][p.sq as usize] as i32).min(free + DETOUR);
            let m = p.kind.movement() as i32;
            let t = (cost + m - 1) / m;
            turns[i] = t;
            let strength = p.kind.strength() as i32;
            let mut v = 14 * strength + (7 - t).max(0) * (3 + 2 * strength);
            if p.kind == Kind::Sentinel && nobody_out {
                v += (6 - t).max(0).pow(2) * 5;
            }
            total += if p.owner == side { v } else { -v };
            first[o] = first[o].min(t);
            if p.kind == Kind::Sentinel {
                sentinel[o] = sentinel[o].min(t);
            }
        }
        if nobody_out {
            let plies = |owner: u8, turns: i32| match turns {
                i32::MAX => i32::MAX,
                t if s.to_move == owner => 2 * t - 1,
                t => 2 * t,
            };
            let wins = |me: u8| {
                let them = 3 - me;
                plies(me, sentinel[me as usize - 1]) < plies(them, first[them as usize - 1]) && sentinel[me as usize - 1] <= SRACE_HORIZON
            };
            total += match (wins(side), wins(other)) {
                (true, false) => SRACE,
                (false, true) => -SRACE,
                _ => 0,
            };
        }
        total
    }
}

pub fn kind_index(k: Kind) -> u8 {
    match k {
        Kind::Explorer => 0,
        Kind::Vanguard => 1,
        Kind::Sentinel => 2,
    }
}
