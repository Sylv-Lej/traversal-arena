//! Simulations Traversal.
//!
//! ```text
//! traversal-cli tournament --a sommet --b montblanc --games 200 [--boards boards.json] [--threads 8] [--seed 1]
//! traversal-cli bench --level montblanc [--positions 50]
//! ```
//!
//! Un niveau est un nom (`galet`, `sentier`, `crete`, `sommet`, `montblanc` : copies de
//! `bot.LEVELS` côté Python), éventuellement suivi de réglages qui le modifient
//! (`montblanc,insight=0` : Mont Blanc sans compréhension = l'ancien bot), ou une spec
//! complète `depth=6,beam=10,noise=0,ms=800,insight=3`. Chaque plateau est joué deux fois,
//! couleurs inversées (l'équité ne dépend pas du plateau).

use std::collections::HashMap;
use std::process::exit;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use traversal_core::config::SQUARES;
use traversal_core::{apply_move, choose_move, new_game, Level, Rng, State};

const DEFAULT_BOARDS: &str = include_str!("../../boards.json");

fn preset(name: &str) -> Option<Level> {
    // Miroir de `LEVELS` (backend/app/bot/__init__.py).
    let (depth, beam, noise, ms, insight) = match name {
        "galet" | "1" => (1, 999, 90.0, 200, 0),
        "sentier" | "2" => (1, 999, 25.0, 300, 0),
        "crete" | "3" => (2, 12, 8.0, 600, 1),
        "sommet" | "4" => (3, 9, 2.0, 1000, 2),
        "montblanc" | "mont-blanc" | "5" => (4, 7, 0.0, 1800, 3),
        _ => return None,
    };
    Some(Level { depth, beam, noise, budget: Duration::from_millis(ms), insight, tuning: Default::default(), stop: None })
}

fn parse_level(spec: &str) -> Level {
    let mut parts = spec.split(',').peekable();
    // Un nom de niveau en tête sert de base ; sinon on part de Mont Blanc.
    let mut l = match parts.peek().and_then(|p| preset(p)) {
        Some(l) => {
            parts.next();
            l
        }
        None => preset("montblanc").unwrap(),
    };
    for part in parts {
        let (k, v) = part.split_once('=').unwrap_or_else(|| die(&format!("spec de niveau invalide : {spec}")));
        let num = |v: &str| v.parse::<f64>().unwrap_or_else(|_| die(&format!("valeur invalide : {part}")));
        match k {
            "depth" => l.depth = num(v) as u8,
            "beam" => l.beam = num(v) as usize,
            "noise" => l.noise = num(v),
            "ms" => l.budget = Duration::from_millis(num(v) as u64),
            "insight" => l.insight = num(v) as u8,
            // Poids des notions (voir `Tuning`).
            "qplies" => l.tuning.qplies = num(v) as u8,
            "ally" => l.tuning.ally = num(v) as u16,
            "soft" => l.tuning.soft = num(v) as u16,
            "detour" => l.tuning.detour = num(v) as u16,
            "blend" => l.tuning.blend = num(v) as i32,
            "guard_extra" => l.tuning.guard_extra = num(v) as usize,
            "srace" => l.tuning.srace = num(v) as i32,
            "srace_horizon" => l.tuning.srace_horizon = num(v) as i32,
            _ => die(&format!("paramètre inconnu : {k}")),
        }
    }
    l
}

fn die(msg: &str) -> ! {
    eprintln!("{msg}");
    exit(2)
}

fn load_boards(path: Option<&String>) -> Vec<[u8; SQUARES]> {
    let text = match path {
        Some(p) => std::fs::read_to_string(p).unwrap_or_else(|e| die(&format!("{p} : {e}"))),
        None => DEFAULT_BOARDS.to_string(),
    };
    let raw: Vec<Vec<u8>> = serde_json::from_str(&text).unwrap_or_else(|e| die(&format!("plateaux : {e}")));
    raw.into_iter()
        .map(|b| b.try_into().unwrap_or_else(|_| die("chaque plateau doit avoir 100 cases")))
        .collect()
}

/// Joue une partie ; renvoie le vainqueur (None : nulle), le nombre de demi-coups et la
/// raison de la fin.
fn play(board: [u8; SQUARES], red: Level, blue: Level, seed: u64) -> (Option<u8>, u16, &'static str) {
    let mut rng = Rng::new(seed);
    let mut s: State = new_game(board);
    while !s.over {
        let level = if s.to_move == 1 { red } else { blue };
        let c = choose_move(&s, level, &mut rng);
        s = apply_move(&s, &c.mv);
    }
    (s.winner, s.ply, s.reason.map_or("?", |r| r.name()))
}

/// Écart d'Elo correspondant à un score (0..1), et sa marge à 95 %.
fn elo(score: f64, games: f64) -> (f64, f64) {
    let p = score.clamp(0.001, 0.999);
    let diff = -400.0 * (1.0 / p - 1.0).log10();
    let se = (p * (1.0 - p) / games).sqrt();
    let hi = (p + 1.96 * se).clamp(0.001, 0.999);
    let margin = -400.0 * (1.0 / hi - 1.0).log10() - diff;
    (diff, margin)
}

fn tournament(args: &HashMap<String, String>) {
    let a = parse_level(args.get("a").map(String::as_str).unwrap_or("sommet"));
    let b = parse_level(args.get("b").map(String::as_str).unwrap_or("montblanc"));
    let games: usize = args.get("games").map_or(100, |v| v.parse().unwrap_or_else(|_| die("--games")));
    let threads: usize = args
        .get("threads")
        .map_or_else(|| thread::available_parallelism().map_or(4, |n| n.get()), |v| v.parse().unwrap_or_else(|_| die("--threads")));
    let seed: u64 = args.get("seed").map_or(1, |v| v.parse().unwrap_or_else(|_| die("--seed")));
    let boards = Arc::new(load_boards(args.get("boards")));
    println!("A = {a:?}\nB = {b:?}\n{games} parties, {threads} threads, {} plateaux", boards.len());

    let next = Arc::new(AtomicUsize::new(0));
    let results = Arc::new(Mutex::new(Vec::with_capacity(games)));
    let t0 = Instant::now();
    let workers: Vec<_> = (0..threads)
        .map(|_| {
            let (next, results, boards) = (next.clone(), results.clone(), boards.clone());
            thread::spawn(move || loop {
                let g = next.fetch_add(1, Ordering::Relaxed);
                if g >= games {
                    break;
                }
                // Parties 2k et 2k+1 : même plateau, couleurs inversées.
                let board = boards[(g / 2) % boards.len()];
                let a_red = g % 2 == 0;
                let (red, blue) = if a_red { (a, b) } else { (b, a) };
                let (winner, plies, reason) = play(board, red, blue, seed.wrapping_mul(1_000_003).wrapping_add(g as u64));
                let a_side = if a_red { 1 } else { 2 };
                let points = match winner {
                    None => 0.5,
                    Some(w) if w == a_side => 1.0,
                    Some(_) => 0.0,
                };
                results.lock().unwrap().push((points, plies, reason));
            })
        })
        .collect();
    for w in workers {
        w.join().expect("thread");
    }
    let res = results.lock().unwrap();
    let n = res.len() as f64;
    let wins = res.iter().filter(|r| r.0 == 1.0).count();
    let draws = res.iter().filter(|r| r.0 == 0.5).count();
    let score: f64 = res.iter().map(|r| r.0).sum::<f64>() / n;
    let plies: f64 = res.iter().map(|r| r.1 as f64).sum::<f64>() / n;
    let (diff, margin) = elo(score, n);
    println!(
        "A : {wins} V / {draws} N / {} D  — score {:.1} %  — Elo(A) − Elo(B) ≈ {diff:+.0} ± {margin:.0}",
        res.len() - wins - draws,
        100.0 * score
    );
    println!("{plies:.1} demi-coups par partie en moyenne, {:.1} s", t0.elapsed().as_secs_f64());
    // Comment se finissent les parties (gagnées par A / perdues par A).
    let mut ends: Vec<(&str, usize, usize)> = Vec::new();
    for r in res.iter() {
        let slot = match ends.iter().position(|e| e.0 == r.2) {
            Some(i) => i,
            None => {
                ends.push((r.2, 0, 0));
                ends.len() - 1
            }
        };
        if r.0 == 1.0 {
            ends[slot].1 += 1;
        } else if r.0 == 0.0 {
            ends[slot].2 += 1;
        }
    }
    let ends: Vec<String> = ends.iter().map(|(k, w, l)| format!("{k} : {w} V / {l} D")).collect();
    println!("fins (pour A) : {}", ends.join(" · "));
}

fn bench(args: &HashMap<String, String>) {
    let level = parse_level(args.get("level").map(String::as_str).unwrap_or("montblanc"));
    let positions: usize = args.get("positions").map_or(40, |v| v.parse().unwrap_or_else(|_| die("--positions")));
    let boards = load_boards(args.get("boards"));
    let mut rng = Rng::new(7);
    let opening = preset("crete").unwrap();
    let (mut nodes, mut depth, mut secs) = (0u64, 0u64, 0f64);
    for i in 0..positions {
        // Position de milieu de partie : quelques coups joués par un bot rapide.
        let mut s = new_game(boards[i % boards.len()]);
        for _ in 0..(6 + rng.below(14)) {
            if s.over {
                break;
            }
            s = apply_move(&s, &choose_move(&s, opening, &mut rng).mv);
        }
        if s.over {
            continue;
        }
        let t = Instant::now();
        let c = choose_move(&s, level, &mut rng);
        secs += t.elapsed().as_secs_f64();
        nodes += c.nodes;
        depth += c.depth as u64;
    }
    println!(
        "{level:?}\n{positions} positions : profondeur moyenne {:.2}, {:.0} nœuds/s, {:.0} ms par coup",
        depth as f64 / positions as f64,
        nodes as f64 / secs.max(1e-9),
        1000.0 * secs / positions as f64
    );
}

fn main() {
    let argv: Vec<String> = std::env::args().skip(1).collect();
    let Some(cmd) = argv.first() else {
        die("usage : traversal-cli tournament|bench [--clé valeur …]");
    };
    let mut args = HashMap::new();
    let mut it = argv[1..].iter();
    while let Some(k) = it.next() {
        let key = k.strip_prefix("--").unwrap_or_else(|| die(&format!("argument inattendu : {k}")));
        let val = it.next().unwrap_or_else(|| die(&format!("valeur manquante pour --{key}")));
        args.insert(key.to_string(), val.clone());
    }
    match cmd.as_str() {
        "tournament" => tournament(&args),
        "bench" => bench(&args),
        _ => die(&format!("commande inconnue : {cmd}")),
    }
}
