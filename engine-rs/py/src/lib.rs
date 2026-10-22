//! Module Python `traversal_rs`, utilisé par `backend/app/bot/native.py`.
//!
//! Une position circule sous forme de tuple :
//! `(heights[100], [(owner, kind, sq), …], to_move, ply, (score1, score2), finished, move_limit)`
//! où l'ordre des pièces est celui de `GameState.pieces` ; un coup est
//! `(indice de pièce | -1, type, case | -1)`.

use std::time::Duration;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use traversal_core::config::{self, SQUARES};
use traversal_core::{bot, Kind, Level, Move, MoveKind, Piece, Rng, State};

type PyState = (Vec<u8>, Vec<(u8, String, u8)>, u8, u16, (u8, u8), u8, u16);
type PyMove = (i32, &'static str, i32);
/// Coup détaillé (tests d'équivalence) : pièce, type, case, coût, spécial, attaque, défense.
type PyMoveFull = (i32, &'static str, i32, u8, Option<&'static str>, u8, u8);

fn state_of(s: PyState) -> PyResult<State> {
    let (heights, pieces, to_move, ply, (s1, s2), finished, move_limit) = s;
    let heights: [u8; SQUARES] = heights
        .try_into()
        .map_err(|_| PyValueError::new_err("heights : 100 cases attendues"))?;
    let pieces = pieces
        .into_iter()
        .map(|(owner, kind, sq)| {
            let kind = Kind::parse(&kind).ok_or_else(|| PyValueError::new_err(format!("pièce inconnue : {kind}")))?;
            Ok(Piece { owner, kind, sq })
        })
        .collect::<PyResult<Vec<_>>>()?;
    Ok(State::new(heights, &pieces, to_move, ply, [s1, s2], finished, move_limit))
}

fn py_state(s: &State) -> PyState {
    let pieces = s.pieces().iter().map(|p| (p.owner, p.kind.name().to_string(), p.sq)).collect();
    (s.heights.to_vec(), pieces, s.to_move, s.ply, (s.scores[0], s.scores[1]), s.finished, s.move_limit)
}

fn idx(v: u8) -> i32 {
    if v == traversal_core::state::NONE {
        -1
    } else {
        v as i32
    }
}

fn py_move(m: &Move) -> PyMove {
    (idx(m.piece), m.kind.name(), idx(m.to))
}

fn find(state: &State, mv: (i32, String, i32)) -> PyResult<Move> {
    let (piece, kind, to) = mv;
    let kind = MoveKind::parse(&kind).ok_or_else(|| PyValueError::new_err(format!("type de coup inconnu : {kind}")))?;
    let piece = if piece < 0 { traversal_core::state::NONE } else { piece as u8 };
    let to = if to < 0 { traversal_core::state::NONE } else { to as u8 };
    if kind == MoveKind::Pass {
        return traversal_core::legal_moves(state)
            .into_iter()
            .find(|m| m.kind == MoveKind::Pass)
            .ok_or_else(|| PyValueError::new_err("Coup illégal."));
    }
    traversal_core::find_move(state, piece, kind, to).ok_or_else(|| PyValueError::new_err("Coup illégal."))
}

/// Coup du bot : `(pièce, type, case)`, puis (profondeur atteinte, score, nœuds).
/// `insight` : compréhension du jeu (0 = bot de référence, identique au Python).
#[pyfunction]
#[pyo3(signature = (state, depth, beam, noise, budget_ms, seed, insight = 0))]
#[allow(clippy::too_many_arguments)]
fn choose_move(
    py: Python<'_>,
    state: PyState,
    depth: u8,
    beam: usize,
    noise: f64,
    budget_ms: u64,
    seed: u64,
    insight: u8,
) -> PyResult<(PyMove, (u8, i32, u64))> {
    let s = state_of(state)?;
    if s.over {
        return Err(PyValueError::new_err("La partie est terminée."));
    }
    let level = Level { depth, beam, noise, budget: Duration::from_millis(budget_ms), insight, tuning: Default::default(), stop: None };
    // La recherche ne touche à aucun objet Python : on rend la main aux autres threads.
    let c = py.allow_threads(|| bot::choose_move(&s, level, &mut Rng::new(seed)));
    Ok((py_move(&c.mv), (c.depth, c.score, c.nodes)))
}

/// Bilan d'un coup joué par le moteur d'analyse (le bot « orque », `engine-rs/analysis`) :
/// `(meilleur coup, score du meilleur, score du coup joué, profondeur)`, en `max_nodes`
/// nœuds par recherche. Analyser les positions d'une partie dans l'ordre (la table de
/// transposition passe d'une position à la suivante).
#[pyfunction]
fn analyse_deep(py: Python<'_>, state: PyState, played: (i32, String, i32), max_nodes: u64)
    -> PyResult<(PyMove, i32, i32, i32)> {
    let s = state_of(state)?;
    if s.over {
        return Err(PyValueError::new_err("La partie est terminée."));
    }
    let played = find(&s, played)?;
    let a = py.allow_threads(|| traversal_analysis::analyse(&s, &played, max_nodes));
    Ok((py_move(&a.best), a.best_score, a.played_score, a.depth))
}

/// Coups légaux détaillés (pour les tests d'équivalence avec le moteur Python).
#[pyfunction]
fn legal_moves(state: PyState) -> PyResult<Vec<PyMoveFull>> {
    let s = state_of(state)?;
    Ok(traversal_core::legal_moves(&s)
        .iter()
        .map(|m| (idx(m.piece), m.kind.name(), idx(m.to), m.cost, m.special.name(), m.attack, m.defense))
        .collect())
}

/// Position après le coup, puis (terminée, vainqueur, raison).
#[pyfunction]
fn apply_move(state: PyState, mv: (i32, String, i32)) -> PyResult<(PyState, (bool, Option<u8>, Option<&'static str>))> {
    let s = state_of(state)?;
    if s.over {
        return Err(PyValueError::new_err("La partie est terminée."));
    }
    let m = find(&s, mv)?;
    let after = traversal_core::apply_move(&s, &m);
    Ok((py_state(&after), (after.over, after.winner, after.reason.map(|r| r.name()))))
}

/// Évaluation du bot, du point de vue de `side` (`insight = 0` : celle du Python).
#[pyfunction]
#[pyo3(signature = (state, side, insight = 0))]
fn evaluate(state: PyState, side: u8, insight: u8) -> PyResult<i32> {
    let s = state_of(state)?;
    Ok(bot::Ctx::with_insight(&s.heights, insight, Default::default()).evaluate(&s, side))
}

/// Constantes du moteur (comparées à `app/engine/config.py` par les tests).
#[pyfunction]
fn constants() -> Vec<(&'static str, i64)> {
    let k = |kind: Kind| (kind.movement() as i64, kind.strength() as i64);
    let (me, se) = k(Kind::Explorer);
    let (mv, sv) = k(Kind::Vanguard);
    let (ms, ss) = k(Kind::Sentinel);
    vec![
        ("SIZE", config::SIZE as i64),
        ("MIN_HEIGHT", config::MIN_HEIGHT as i64),
        ("MAX_HEIGHT", config::MAX_HEIGHT as i64),
        ("MAX_STEP", config::MAX_STEP as i64),
        ("LEAP_OVER_PIECES", config::LEAP_OVER_PIECES as i64),
        ("SPECIAL_MOVES_CAN_ATTACK", config::SPECIAL_MOVES_CAN_ATTACK as i64),
        ("VANGUARD_CHARGE_COST", config::VANGUARD_CHARGE_COST as i64),
        ("FINISHERS_TO_END", config::FINISHERS_TO_END as i64),
        ("MOVE_LIMIT", config::MOVE_LIMIT as i64),
        ("MOVEMENT.explorer", me),
        ("MOVEMENT.vanguard", mv),
        ("MOVEMENT.sentinel", ms),
        ("STRENGTH.explorer", se),
        ("STRENGTH.vanguard", sv),
        ("STRENGTH.sentinel", ss),
        ("WIN", bot::WIN as i64),
    ]
}

#[pymodule]
fn traversal_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(choose_move, m)?)?;
    m.add_function(wrap_pyfunction!(analyse_deep, m)?)?;
    m.add_function(wrap_pyfunction!(legal_moves, m)?)?;
    m.add_function(wrap_pyfunction!(apply_move, m)?)?;
    m.add_function(wrap_pyfunction!(evaluate, m)?)?;
    m.add_function(wrap_pyfunction!(constants, m)?)?;
    Ok(())
}
