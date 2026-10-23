//! Bilan d'une partie (tâche `analyse`), joué dans le processus enfant cloisonné.
//!
//! Pour chaque position de la partie : le bot WebAssembly (le n°1 de l'arène) choisit son
//! coup, avec le même fuel qu'en partie et une instance neuve par position (le bilan ne
//! dépend que de la position) ; puis orque (`traversal-analysis`, natif, budget de nœuds
//! fixe) note ce coup et le coup réellement joué. Le backend en tire précision,
//! appréciations et courbe (`app/analysis.py`), après avoir vérifié chaque coup du bot.
//!
//! Orque n'est pas publié : ce module n'existe qu'avec la fonctionnalité `analysis`
//! (image du site), le dépôt public du SDK en est privé (`scripts/sync_sdk.sh`).

use serde_json::{json, Value};
use traversal_core::config::SQUARES;
use traversal_core::state::NONE;
use traversal_core::{find_move, legal_moves, Kind, Move, MoveKind, Piece, State};
use wasmtime::{Engine, Module};

use crate::sandbox::{self, Bot, Fault};

/// Budget d'orque par recherche, si la tâche n'en donne pas (le backend le fixe).
const DEFAULT_NODES: u64 = 60_000;

/// Position au format du backend (`native.pack`) :
/// `[heights[100], [[owner, kind, sq], …], to_move, ply, [score1, score2], finished, move_limit]`.
fn state_of(v: &Value) -> Option<State> {
    let heights: [u8; SQUARES] = v[0].as_array()?.iter().map(|h| h.as_u64().map(|x| x as u8)).collect::<Option<Vec<_>>>()?.try_into().ok()?;
    let pieces = v[1]
        .as_array()?
        .iter()
        .map(|p| Some(Piece { owner: p[0].as_u64()? as u8, kind: Kind::parse(p[1].as_str()?)?, sq: p[2].as_u64()? as u8 }))
        .collect::<Option<Vec<_>>>()?;
    let n = |i: usize| v[i].as_u64();
    Some(State::new(heights, &pieces, n(2)? as u8, n(3)? as u16, [v[4][0].as_u64()? as u8, v[4][1].as_u64()? as u8], n(5)? as u8, n(6)? as u16))
}

/// Coup `[pièce | -1, type, case | -1]` parmi les coups légaux.
fn move_of(s: &State, v: &Value) -> Option<Move> {
    let kind = MoveKind::parse(v[1].as_str()?)?;
    if kind == MoveKind::Pass {
        return legal_moves(s).into_iter().find(|m| m.kind == MoveKind::Pass);
    }
    let byte = |x: i64| if x < 0 { NONE } else { x as u8 };
    find_move(s, byte(v[0].as_i64()?), kind, byte(v[2].as_i64()?))
}

fn same(a: &Move, b: &Move) -> bool {
    a.piece == b.piece && a.kind == b.kind && a.to == b.to
}

pub fn run(engine: &Engine, job: &Value, bot: &[u8]) -> Value {
    let fuel = job["fuel"].as_u64().unwrap_or(crate::DEFAULT_FUEL);
    let nodes = job["nodes"].as_u64().unwrap_or(DEFAULT_NODES);
    let module: Result<Module, Fault> = sandbox::compile(engine, bot);
    let mut out = Vec::new();
    let (mut fuel_used, mut calls) = (0u64, 0u64);
    for (i, pos) in job["positions"].as_array().map(Vec::as_slice).unwrap_or_default().iter().enumerate() {
        let Some(s) = state_of(&pos["state"]) else { return json!({"error": format!("position {i} illisible")}) };
        let Some(played) = move_of(&s, &pos["played"]) else { return json!({"error": format!("coup {i} illégal")}) };
        let moves = legal_moves(&s);
        if moves.len() <= 1 {
            out.push(json!({"bot": crate::wire_move(&played), "botScore": 0, "playedScore": 0, "depth": 0}));
            continue;
        }
        // Le coup du bot (une faute ne fait pas échouer le bilan : orque prend le relais).
        let pick = match &module {
            Ok(m) => Bot::new(engine, m, false).and_then(|mut b| {
                let r = b.choose(&s, &moves, pos["seed"].as_u64().unwrap_or(i as u64), fuel);
                fuel_used += b.fuel_used;
                calls += 1;
                r
            }),
            Err(f) => Err(f.clone()),
        };
        // Orque note le coup du bot, puis le coup joué. Bot en faute : le coup d'orque.
        let (bot_move, bot_score, played_score, depth, fault) = match pick {
            Ok(k) => {
                let b = moves[k];
                let a = traversal_analysis::analyse(&s, &b, nodes);
                let p = if same(&b, &played) { a.played_score } else { traversal_analysis::analyse(&s, &played, nodes).played_score };
                (b, a.played_score, p, a.depth, None)
            }
            Err(f) => {
                let a = traversal_analysis::analyse(&s, &played, nodes);
                (a.best, a.best_score, a.played_score, a.depth, Some(f.code()))
            }
        };
        out.push(json!({
            "bot": crate::wire_move(&bot_move),
            "fault": fault,
            "botScore": bot_score,
            "playedScore": played_score,
            "depth": depth,
        }));
    }
    json!({"positions": out, "fuel": fuel_used / calls.max(1)})
}
