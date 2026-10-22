//! Coups légaux, les mêmes que `legal_moves` du moteur (vérifié par les tests, à l'ordre
//! près) mais moins chers : marches précalculées pour le relief, Dijkstra limité aux cases
//! atteintes, attaques cherchées depuis les pièces adverses (≤ 6) au lieu des 100 cases.
//! Le mode `tactical` ne produit que les sorties et les attaques (recherche de calme).

use traversal_bot::core::config::{Kind, LEAP_OVER_PIECES, SIZE, SPECIAL_MOVES_CAN_ATTACK, SQUARES, VANGUARD_CHARGE_COST};
use traversal_bot::core::movegen::{combat, exit_row, neighbors_of, step_cost};
use traversal_bot::core::state::NONE;
use traversal_bot::core::{Move, MoveKind, Special, State};

const SPECIALS: [(Special, i32, i32); 8] = [
    (Special::Diag, 1, 1),
    (Special::Diag, 1, -1),
    (Special::Diag, -1, 1),
    (Special::Diag, -1, -1),
    (Special::Leap, 0, 2),
    (Special::Leap, 2, 0),
    (Special::Leap, 0, -2),
    (Special::Leap, -2, 0),
];

pub struct Gen {
    /// Marche de chaque case vers sa k-ième voisine (`neighbors_of`).
    step: [[u8; 4]; SQUARES],
}

impl Gen {
    pub fn new(heights: &[u8; SQUARES]) -> Gen {
        let mut step = [[0u8; 4]; SQUARES];
        for sq in 0..SQUARES as u8 {
            for (k, &nb) in neighbors_of(sq).iter().enumerate() {
                step[sq as usize][k] = step_cost(heights, sq, nb);
            }
        }
        Gen { step }
    }

    /// Coups du camp au trait ; `tactical` : sorties et attaques seulement (sans passe).
    pub fn moves(&self, s: &State, tactical: bool) -> Vec<Move> {
        let mut out = Vec::with_capacity(if tactical { 8 } else { 96 });
        if s.over {
            return out;
        }
        for (i, p) in s.pieces().iter().enumerate() {
            if p.owner == s.to_move {
                self.piece_moves(s, i as u8, tactical, &mut out);
            }
        }
        if out.is_empty() && !tactical {
            out.push(Move::PASS); // R4.8
        }
        out
    }

    fn piece_moves(&self, s: &State, i: u8, tactical: bool, out: &mut Vec<Move>) {
        let piece = s.piece(i);
        let budget = piece.kind.movement() as usize;
        // Dijkstra à seaux (coûts ≤ 5) sur les cases vides ; `reached` dans l'ordre des coûts.
        let mut dist = [NONE; SQUARES];
        let mut buckets = [[0u8; 64]; 6];
        let mut counts = [0usize; 6];
        let mut reached = [0u8; 64];
        let mut n = 0;
        dist[piece.sq as usize] = 0;
        buckets[0][0] = piece.sq;
        counts[0] = 1;
        for d in 0..=budget {
            let mut k = 0;
            while k < counts[d] {
                let cur = buckets[d][k];
                k += 1;
                if dist[cur as usize] as usize != d {
                    continue;
                }
                reached[n] = cur;
                n += 1;
                for (j, &nb) in neighbors_of(cur).iter().enumerate() {
                    if s.at(nb).is_some() {
                        continue;
                    }
                    let nd = d + self.step[cur as usize][j] as usize;
                    if nd <= budget && nd < dist[nb as usize] as usize {
                        dist[nb as usize] = nd as u8;
                        buckets[nd][counts[nd]] = nb;
                        counts[nd] += 1;
                    }
                }
            }
        }

        // R4 Déplacements.
        if !tactical {
            for &sq in &reached[1..n] {
                out.push(Move { piece: i, kind: MoveKind::Move, to: sq, cost: dist[sq as usize], special: Special::None, attack: 0, defense: 0 });
            }
        }

        // R7 Attaques : depuis chaque pièce adverse, la meilleure case atteinte voisine.
        let mut attacked = [NONE; 6];
        let mut na = 0;
        for (j, t) in s.pieces().iter().enumerate() {
            if t.owner == piece.owner {
                continue;
            }
            let mut cost = NONE as usize;
            for (k, &nb) in neighbors_of(t.sq).iter().enumerate() {
                let d = dist[nb as usize];
                if d != NONE {
                    cost = cost.min(d as usize + self.step[t.sq as usize][k] as usize);
                }
            }
            if cost > budget {
                continue;
            }
            let charge = piece.kind == Kind::Vanguard && cost == VANGUARD_CHARGE_COST as usize;
            let (attack, defense) = combat(s, i, j as u8, charge);
            if attack >= defense {
                out.push(Move { piece: i, kind: MoveKind::Attack, to: t.sq, cost: cost as u8, special: Special::None, attack, defense });
                attacked[na] = t.sq;
                na += 1;
            }
        }

        // R6 Sortie.
        let row = exit_row(piece.owner) as usize * SIZE;
        let mut exit_cost = NONE;
        for x in 0..SIZE {
            let d = dist[row + x];
            if d != NONE && d as usize + 1 <= budget && d < exit_cost {
                exit_cost = d;
            }
        }

        // R5 Coups spéciaux de l'Explorateur, sauf vers une case déjà atteinte normalement.
        if piece.kind == Kind::Explorer {
            let (x, y) = ((piece.sq % SIZE as u8) as i32, (piece.sq / SIZE as u8) as i32);
            for (kind, dx, dy) in SPECIALS {
                let (nx, ny) = (x + dx, y + dy);
                if !(0..SIZE as i32).contains(&nx) || !(0..SIZE as i32).contains(&ny) {
                    continue;
                }
                if kind == Special::Leap && !LEAP_OVER_PIECES {
                    let middle = ((y + dy / 2) * SIZE as i32 + (x + dx / 2)) as u8;
                    if s.at(middle).is_some() {
                        continue;
                    }
                }
                let dest = (ny * SIZE as i32 + nx) as u8;
                match s.at(dest) {
                    None if dist[dest as usize] == NONE && !tactical => {
                        out.push(Move { piece: i, kind: MoveKind::Move, to: dest, cost: 0, special: kind, attack: 0, defense: 0 });
                    }
                    Some(j) if s.piece(j).owner != piece.owner && SPECIAL_MOVES_CAN_ATTACK && !attacked[..na].contains(&dest) => {
                        let (attack, defense) = combat(s, i, j, false);
                        if attack >= defense {
                            out.push(Move { piece: i, kind: MoveKind::Attack, to: dest, cost: 0, special: kind, attack, defense });
                        }
                    }
                    _ => {}
                }
            }
        }

        if exit_cost != NONE {
            out.push(Move { piece: i, kind: MoveKind::Exit, to: NONE, cost: exit_cost + 1, special: Special::None, attack: 0, defense: 0 });
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use traversal_bot::core::{apply_move, legal_moves, new_game, Rng};

    fn sorted(mut v: Vec<Move>) -> Vec<(u8, u8, u8, u8, u8, u8, u8)> {
        let mut out: Vec<_> = v.drain(..).map(|m| (m.piece, m.kind as u8, m.to, m.special as u8, m.cost, m.attack, m.defense)).collect();
        out.sort();
        out
    }

    #[test]
    fn same_moves_as_the_engine() {
        let mut rng = Rng::new(3);
        let mut positions = 0;
        for b in 0..60 {
            let mut heights = [0u8; SQUARES];
            for h in heights.iter_mut() {
                *h = (rng.below(7) as u8).min(rng.below(7) as u8 + b % 3);
            }
            let gen = Gen::new(&heights);
            let mut s = new_game(heights);
            while !s.over {
                let all = legal_moves(&s);
                assert_eq!(sorted(gen.moves(&s, false)), sorted(all.clone()));
                let tactical: Vec<Move> = all.iter().copied().filter(|m| matches!(m.kind, MoveKind::Exit | MoveKind::Attack)).collect();
                assert_eq!(sorted(gen.moves(&s, true)), sorted(tactical));
                // Plutôt les attaques et sorties : des positions variées, avec des prises.
                let pick = all.iter().position(|m| m.kind == MoveKind::Attack && rng.below(2) == 0).unwrap_or(rng.below(all.len()));
                s = apply_move(&s, &all[pick]);
                positions += 1;
            }
        }
        assert!(positions > 3000, "{positions} positions");
    }
}
