"""Schéma Postgres (Lampion). Les migrations vivent dans `migrations/` (Alembic).

Une partie n'est PAS stockée en photo d'état : on garde le relief, les coups et le
résultat, et l'état est reconstruit en rejouant les coups (déterministe, et l'historique
coup par coup vient gratuitement). Les colonnes score/ply/winner/reason ne servent qu'à
lister les parties sans les rejouer.
"""

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    LargeBinary,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    true,
)

metadata = MetaData()

players = Table(
    "players",
    metadata,
    Column("id", String(16), primary_key=True),
    Column("name", String(32), nullable=False),
    Column("email", String(254), unique=True, nullable=True),
    Column("password_hash", String(255), nullable=True),
    Column("is_bot", Boolean, nullable=False, default=False),
    Column("created_at", Float, nullable=False),
    Column("last_seen", Float, nullable=False),
    # Pays représenté (ISO 3166-1 alpha-2), choisi à l'inscription : drapeau à côté du pseudo.
    Column("country", String(2), nullable=True),
    # Adresse confirmée (lien reçu par email) : exigée pour inscrire un bot dans l'arène.
    Column("email_verified_at", Float, nullable=True),
    Index("ix_players_last_seen", "last_seen"),
)

sessions = Table(
    "sessions",
    metadata,
    # SHA-256 du jeton : une fuite de la base ne donne aucune session utilisable.
    Column("token_hash", String(64), primary_key=True),
    Column("player_id", String(16), ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
    Column("created_at", Float, nullable=False),
    # Dernière utilisation (mise à jour au plus une fois par heure) : expiration glissante.
    Column("last_used", Float, nullable=True),
    Index("ix_sessions_player", "player_id"),
    Index("ix_sessions_last_used", "last_used"),
)

password_resets = Table(
    "password_resets",
    metadata,
    # Comme les sessions : seul le SHA-256 du jeton est stocké.
    Column("token_hash", String(64), primary_key=True),
    Column("player_id", String(16), ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
    Column("created_at", Float, nullable=False),
    Column("expires_at", Float, nullable=False),
)

# Liens de confirmation d'adresse (comme `password_resets`) : liés à l'adresse visée, un
# lien envoyé avant un changement d'adresse ne confirme pas la nouvelle.
email_verifications = Table(
    "email_verifications",
    metadata,
    Column("token_hash", String(64), primary_key=True),
    Column("player_id", String(16), ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
    Column("email", String(254), nullable=False),
    Column("created_at", Float, nullable=False),
    Column("expires_at", Float, nullable=False),
)

ratings = Table(
    "ratings",
    metadata,
    Column("player_id", String(16), ForeignKey("players.id", ondelete="CASCADE"), primary_key=True),
    Column("time_class", String(16), primary_key=True),
    Column("rating", Float, nullable=False),
    Column("rd", Float, nullable=False),
    Column("vol", Float, nullable=False),
    Column("games", Integer, nullable=False),
    Column("wins", Integer, nullable=False),
    Column("losses", Integer, nullable=False),
    Column("draws", Integer, nullable=False),
    Index("ix_ratings_board", "time_class", "rating"),
)

games = Table(
    "games",
    metadata,
    Column("id", String(16), primary_key=True),
    Column("mode", String(8), nullable=False),
    Column("status", String(10), nullable=False),
    Column("terrain_mode", String(16), nullable=False),
    Column("seed", BigInteger, nullable=False),
    Column("heights", JSON, nullable=False),
    Column("move_limit", Integer, nullable=False),
    # Mise en place des pièces au début (`engine.config.SETUPS`) ; NULL : « classic ».
    Column("setup", String(8), nullable=True),
    Column("p1_id", String(16), ForeignKey("players.id"), nullable=True),
    Column("p2_id", String(16), ForeignKey("players.id"), nullable=True),
    Column("created_by", String(16), ForeignKey("players.id"), nullable=False),
    Column("bot_level", Integer, nullable=True),
    Column("initial_ms", Integer, nullable=True),
    Column("increment_ms", Integer, nullable=False),
    Column("remaining", JSON, nullable=False),
    Column("turn_started_at", Float, nullable=True),
    Column("version", Integer, nullable=False),
    Column("rated", Boolean, nullable=False),
    Column("time_class", String(16), nullable=False),
    Column("draw_offer", Integer, nullable=True),
    Column("rematch_offer", Integer, nullable=True),
    Column("rematch_id", String(16), nullable=True),
    Column("rating_before", JSON, nullable=True),
    Column("rating_after", JSON, nullable=True),
    # Résumé (listes de parties sans rejouer les coups).
    Column("ply", Integer, nullable=False),
    Column("score1", Integer, nullable=False),
    Column("score2", Integer, nullable=False),
    Column("winner", Integer, nullable=True),
    Column("reason", String(16), nullable=True),
    Column("created_at", Float, nullable=False),
    Column("ended_at", Float, nullable=True),
    # Bilan de partie (JSON), calculé à la demande et gardé pour tout le monde.
    Column("analysis", JSON, nullable=True),
    # Rang avant/après (figé en fin de partie classée).
    Column("rank_change", JSON, nullable=True),
    # Échéance de la pendule (ou du premier coup) : balayée par toutes les instances.
    Column("deadline_at", Float, nullable=True),
    # Manche d'un match tactique (sinon NULL).
    Column("match_id", String(16), ForeignKey("matches.id", ondelete="CASCADE"), nullable=True),
    Column("round", Integer, nullable=True),
    # Partie importée d'un autre site (mode « import ») : sa référence là-bas (une partie
    # n'est importée qu'une fois) et ce qu'on en garde (pseudos, classements, lien).
    Column("import_ref", String(64), unique=True, nullable=True),
    Column("imported", JSON, nullable=True),
    Index("ix_games_p1", "p1_id", "created_at"),
    Index("ix_games_p2", "p2_id", "created_at"),
    Index("ix_games_creator", "created_by", "created_at"),
    Index("ix_games_status", "status"),
    Index("ix_games_deadline", "deadline_at"),
    Index("ix_games_mode_ended", "mode", "ended_at"),
)

moves = Table(
    "moves",
    metadata,
    Column("game_id", String(16), ForeignKey("games.id", ondelete="CASCADE"), primary_key=True),
    Column("ply", Integer, primary_key=True),
    Column("side", Integer, nullable=False),
    Column("piece_id", String(8), nullable=False),
    Column("kind", String(8), nullable=False),
    Column("special", String(8), nullable=True),
    Column("frm", Integer, nullable=True),
    Column("to", Integer, nullable=True),
    Column("path", JSON, nullable=False),
    Column("notation", String(24), nullable=False),
    Column("combat", JSON, nullable=True),
    Column("captured_id", String(8), nullable=True),
    Column("remaining_ms", Integer, nullable=True),
)


# --- Files de travail partagées entre instances (SELECT … FOR UPDATE SKIP LOCKED) -------

bot_jobs = Table(
    "bot_jobs",
    metadata,
    Column("game_id", String(16), ForeignKey("games.id", ondelete="CASCADE"), primary_key=True),
    Column("version", Integer, nullable=False),  # version de la partie à laquelle répondre
    Column("run_after", Float, nullable=False),
    Column("claimed_at", Float, nullable=True),
    Index("ix_bot_jobs_run_after", "run_after"),
)

analysis_jobs = Table(
    "analysis_jobs",
    metadata,
    Column("game_id", String(16), ForeignKey("games.id", ondelete="CASCADE"), primary_key=True),
    Column("status", String(10), nullable=False),  # queued | running | error
    Column("done", Integer, nullable=False),
    Column("total", Integer, nullable=False),
    Column("created_at", Float, nullable=False),
    Column("claimed_at", Float, nullable=True),
)

seeks = Table(
    "seeks",
    metadata,
    Column("player_id", String(16), ForeignKey("players.id", ondelete="CASCADE"), primary_key=True),
    Column("time_control", String(8), nullable=False),
    Column("terrain", String(16), nullable=False),  # "random" si classée
    Column("rated", Boolean, nullable=False, server_default=true()),
    Column("rating", Float, nullable=False),
    Column("created_at", Float, nullable=False),
    Column("polled_at", Float, nullable=False),
    Column("game_id", String(16), nullable=True),
    Index("ix_seeks_tc", "time_control", "created_at"),
)

# Limites de débit PARTAGÉES entre instances (connexion, inscription, emails…) : un
# compteur par clé et par fenêtre fixe. Les limites à fort trafic (coups) restent en
# mémoire, par instance, pour ne pas ajouter d'aller-retour à la base.
rate_hits = Table(
    "rate_hits",
    metadata,
    Column("key", String(200), primary_key=True),
    Column("window_start", Float, primary_key=True),
    Column("count", Integer, nullable=False),
    Index("ix_rate_hits_window", "window_start"),
)

# Spectateurs d'une partie, comptés PAR INSTANCE (chaque instance tient ses flux SSE) :
# total = somme des lignes encore fraîches (une instance disparue cesse de compter).
game_watchers = Table(
    "game_watchers",
    metadata,
    Column("game_id", String(16), ForeignKey("games.id", ondelete="CASCADE"), primary_key=True),
    Column("instance", String(16), primary_key=True),
    Column("count", Integer, nullable=False),
    Column("updated_at", Float, nullable=False),
)

# Match tactique : 2 manches (+ décisive), bans et choix du type de carte avant chaque
# manche. L'état détaillé des manches (bans, choix, parties, vainqueurs) est en JSON.
matches = Table(
    "matches",
    metadata,
    Column("id", String(16), primary_key=True),
    Column("mode", String(8), nullable=False),
    Column("status", String(10), nullable=False),  # waiting | veto | playing | finished | aborted
    Column("p1_id", String(16), ForeignKey("players.id"), nullable=True),
    Column("p2_id", String(16), ForeignKey("players.id"), nullable=True),
    Column("created_by", String(16), ForeignKey("players.id"), nullable=False),
    Column("bot_level", Integer, nullable=True),
    Column("round", Integer, nullable=False),
    Column("step", Integer, nullable=False),
    Column("rounds", JSON, nullable=False),
    Column("score", JSON, nullable=False),
    Column("winner", Integer, nullable=True),
    Column("rated", Boolean, nullable=False),
    Column("rating_before", JSON, nullable=True),
    Column("rating_after", JSON, nullable=True),
    Column("rank_change", JSON, nullable=True),
    Column("deadline_at", Float, nullable=True),  # délai du ban / choix en cours
    Column("version", Integer, nullable=False),
    Column("created_at", Float, nullable=False),
    Column("ended_at", Float, nullable=True),
    Index("ix_matches_p1", "p1_id", "created_at"),
    Index("ix_matches_p2", "p2_id", "created_at"),
    Index("ix_matches_deadline", "deadline_at"),
)

# --- Puzzles (comme sur chess.com) ------------------------------------------------------
# Générés à partir de parties bot contre bot (app/puzzles.py), chargés au démarrage.
# Chaque puzzle a son propre classement Glicko-2, qui bouge quand des joueurs le tentent.
puzzles = Table(
    "puzzles",
    metadata,
    Column("id", String(16), primary_key=True),
    Column("terrain", String(16), nullable=False),
    Column("start", JSON, nullable=False),  # position avant le coup de l'adversaire
    Column("solution", JSON, nullable=False),  # coup adverse, puis joueur / réponse en alternance
    # Variantes acceptées : [{"m": coup, "r": réponse, "next": [...]}, …] (None : la solution seule).
    Column("tree", JSON, nullable=True),
    Column("themes", JSON, nullable=False),
    Column("side", Integer, nullable=False),  # camp du joueur
    Column("rating", Float, nullable=False),
    Column("rd", Float, nullable=False),
    Column("vol", Float, nullable=False),
    Column("plays", Integer, nullable=False),
    Column("solves", Integer, nullable=False),
    Column("created_at", Float, nullable=False),
    Index("ix_puzzles_rating", "rating"),
)

# Une tentative d'un joueur sur un puzzle (classée, rejouée, du jour, ou dans un Rush).
puzzle_attempts = Table(
    "puzzle_attempts",
    metadata,
    Column("id", String(16), primary_key=True),
    Column("player_id", String(16), ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
    Column("puzzle_id", String(16), ForeignKey("puzzles.id", ondelete="CASCADE"), nullable=False),
    Column("mode", String(8), nullable=False),  # rated | retry | daily | rush
    Column("rush_id", String(16), ForeignKey("puzzle_rushes.id", ondelete="CASCADE"), nullable=True),
    Column("step", Integer, nullable=False),  # prochain coup attendu dans la solution
    Column("status", String(8), nullable=False),  # playing | solved | failed
    Column("rated", Boolean, nullable=False),
    Column("hinted", Boolean, nullable=False),
    Column("revealed", Boolean, nullable=False),
    Column("wrong", JSON, nullable=True),  # coup raté (pour l'afficher)
    Column("line", JSON, nullable=True),  # coups joués (variante comprise) ; None : la solution
    Column("rating_before", Float, nullable=True),
    Column("rating_after", Float, nullable=True),
    Column("daily", String(10), nullable=True),  # AAAA-MM-JJ du puzzle du jour
    Column("started_at", Float, nullable=False),
    Column("ended_at", Float, nullable=True),
    Index("ix_attempts_player", "player_id", "started_at"),
    Index("ix_attempts_player_puzzle", "player_id", "puzzle_id"),
)

# Puzzle Rush : un maximum de puzzles (de plus en plus durs) en temps limité, 3 erreurs.
puzzle_rushes = Table(
    "puzzle_rushes",
    metadata,
    Column("id", String(16), primary_key=True),
    Column("player_id", String(16), ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
    Column("mode", String(10), nullable=False),  # 3min | 5min | survival
    Column("status", String(8), nullable=False),  # running | over
    Column("score", Integer, nullable=False),
    Column("strikes", Integer, nullable=False),
    Column("attempt_id", String(16), nullable=True),
    Column("started_at", Float, nullable=False),
    Column("deadline_at", Float, nullable=True),
    Column("ended_at", Float, nullable=True),
    Index("ix_rushes_board", "mode", "score"),
    Index("ix_rushes_player", "player_id", "started_at"),
)


# --- Arène des bots (ARENA.md) ----------------------------------------------------------
# Un bot de la communauté = un module WebAssembly envoyé par un joueur. Chaque VERSION est
# un joueur bot à part (`players`, `is_bot`) : ses parties (`games`, mode « arena »)
# restent attachées à la version qui les a jouées.
arena_bots = Table(
    "arena_bots",
    metadata,
    Column("id", String(16), ForeignKey("players.id", ondelete="CASCADE"), primary_key=True),
    Column("owner_id", String(16), ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
    Column("name", String(24), nullable=False),
    Column("version", Integer, nullable=False),
    Column("status", String(10), nullable=False),  # pending | active | rejected | retired
    Column("error", String(300), nullable=True),  # pourquoi la validation a échoué
    # Le module lui-même (1 Mo au plus) ; effacé quand la version ne joue plus.
    Column("wasm", LargeBinary, nullable=True),
    Column("sha256", String(64), nullable=False),
    Column("size", Integer, nullable=False),
    Column("created_at", Float, nullable=False),
    Column("activated_at", Float, nullable=True),
    Index("ix_arena_bots_owner", "owner_id", "name", "version", unique=True),
    Index("ix_arena_bots_status", "status"),
    Index("ix_arena_bots_sha", "sha256"),
)

# File des parties à jouer par le runner (`traversal-arena work`), et des validations.
arena_jobs = Table(
    "arena_jobs",
    metadata,
    Column("id", String(16), primary_key=True),
    Column("kind", String(8), nullable=False),  # check | game | analyse
    Column("red_id", String(16), ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
    Column("blue_id", String(16), ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
    Column("terrain", String(16), nullable=False),
    Column("seed", BigInteger, nullable=False),
    Column("heights", JSON, nullable=False),
    Column("status", String(8), nullable=False),  # queued | running
    Column("attempts", Integer, nullable=False),
    Column("created_at", Float, nullable=False),
    Column("claimed_at", Float, nullable=True),
    # Bilan (`analyse`) : la partie analysée par le bot rouge (le n°1 de l'arène) et orque.
    Column("game_id", String(16), ForeignKey("games.id", ondelete="CASCADE"), nullable=True),
    Index("ix_arena_jobs_queue", "status", "created_at"),
)

# Classement de l'arène (Bradley-Terry sur toutes les parties, recalculé par lots).
arena_ratings = Table(
    "arena_ratings",
    metadata,
    Column("player_id", String(16), ForeignKey("players.id", ondelete="CASCADE"), primary_key=True),
    Column("rating", Float, nullable=False),
    Column("margin", Float, nullable=False),  # demi-intervalle de confiance à 95 %
    Column("games", Integer, nullable=False),
    Column("wins", Integer, nullable=False),
    Column("losses", Integer, nullable=False),
    Column("draws", Integer, nullable=False),
    Column("updated_at", Float, nullable=False),
)
