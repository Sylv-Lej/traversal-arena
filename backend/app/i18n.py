"""Messages de l'API en anglais.

Le code écrit ses messages en français (langue de référence). Le relais du front transmet
la langue du joueur (`x-lang`) ; pour `en`, le gestionnaire d'erreurs (`main.py`) remplace
le message par sa traduction. Un message absent d'ici reste en français : à ajouter.
"""

from app.services.accounts import LOGIN_LOCK_S, MIN_PASSWORD

LANGS = ("fr", "en")

EN: dict[str, str] = {
    # Comptes
    "Ce lien n'est plus valable : redemande un email de réinitialisation.":
        "This link is no longer valid: request a new reset email.",
    "Email ou mot de passe incorrect.": "Incorrect email or password.",
    "Mot de passe actuel incorrect.": "Current password is incorrect.",
    "Cette adresse est déjà utilisée : connecte-toi plutôt.": "This email is already in use: log in instead.",
    "Crée d'abord un compte.": "Create an account first.",
    "Tu as déjà un compte.": "You already have an account.",
    "Adresse email invalide.": "Invalid email address.",
    "Mot de passe trop long.": "Password is too long.",
    f"Mot de passe trop court ({MIN_PASSWORD} caractères minimum).":
        f"Password is too short ({MIN_PASSWORD} characters minimum).",
    f"Trop d'essais pour cette adresse : réessaie dans {LOGIN_LOCK_S // 60} minutes, "
    "ou utilise « mot de passe oublié ».":
        f"Too many attempts for this email: try again in {LOGIN_LOCK_S // 60} minutes, "
        "or use “forgot password”.",
    "Pseudo invalide (3 à 20 caractères).": "Invalid username (3 to 20 characters).",
    "Pseudo invalide : 3 à 20 lettres, chiffres, espaces ou - . '":
        "Invalid username: 3 to 20 letters, digits, spaces or - . '",
    "Joueur introuvable.": "Player not found.",
    "Choisis le pays que tu représentes.": "Choose the country you represent.",
    "Pays inconnu.": "Unknown country.",
    # Parties
    "Ce n'est pas ton tour.": "It’s not your turn.",
    "Tu ne joues pas cette partie.": "You’re not playing in this game.",
    # Confirmation d'adresse
    "Ton adresse est déjà confirmée.": "Your email address is already confirmed.",
    "Email déjà envoyé : réessaie dans une minute.": "Email already sent: try again in a minute.",
    "Ce lien n'est plus valable : redemande un email de confirmation.":
        "This link is no longer valid: request a new confirmation email.",
    "Confirme ton adresse email pour inscrire un bot.": "Confirm your email address to enter a bot.",
    # Arène des bots
    "Crée un compte pour inscrire un bot.": "Create an account to enter a bot.",
    "Nom de bot invalide (3 à 24 caractères).": "Invalid bot name (3 to 24 characters).",
    "Fichier illisible.": "Unreadable file.",
    "Fichier trop gros (1 Mo au plus).": "File too large (1 MB max).",
    "Ce n'est pas un module WebAssembly (.wasm).": "This is not a WebAssembly module (.wasm).",
    "Trop d'envois aujourd'hui. Réessaie demain.": "Too many uploads today. Try again tomorrow.",
    "Ce nom de bot est déjà pris.": "This bot name is already taken.",
    "Tu as déjà un bot de ce nom : envoie le fichier comme mise à jour.": "You already have a bot with this name: upload the file as an update.",
    "Trop de bots en lice : retires-en un d'abord.": "Too many bots competing: retire one first.",
    "Bot introuvable.": "Bot not found.",
    "Tâche inconnue ou déjà rendue.": "Unknown or already returned job.",
    "Partie refusée.": "Game rejected.",
    "Bilan refusé.": "Review rejected.",
    # Import de parties (traversalgame.com)
    "Lien de partie traversalgame.com invalide.": "Invalid traversalgame.com game link.",
    "traversalgame.com ne répond pas : réessaie plus tard.": "traversalgame.com is not responding: try again later.",
    "L'import de parties n'est pas configuré.": "Game import is not configured.",
    "Partie introuvable sur traversalgame.com.": "Game not found on traversalgame.com.",
    "Cette partie n'est pas terminée.": "This game is not over.",
    "Plateau non pris en charge.": "Unsupported board.",
    "Mise en place des pièces non prise en charge.": "Unsupported piece setup.",
    "Un coup de cette partie est illégal selon nos règles : partie non importée.":
        "A move in this game is illegal under our rules: game not imported.",
    "Arène non configurée.": "Arena not configured.",
    "Authentification requise.": "Authentication required.",
    "Module introuvable.": "Module not found.",
    "Requête trop volumineuse.": "Request too large.",
    "Partie introuvable.": "Game not found.",
    "Revanche introuvable.": "Rematch not found.",
    "Annulation impossible.": "The game can’t be aborted.",
    "Aucune proposition de nulle.": "No draw offer.",
    "Impossible d'abandonner.": "You can’t resign this game.",
    "La partie a déjà commencé.": "The game has already started.",
    "La partie n'est pas en cours.": "The game is not in progress.",
    "La partie n'est pas terminée.": "The game is not over.",
    "Le bot refuse la nulle.": "The bot declines the draw.",
    "Pas de nulle possible.": "A draw isn’t possible.",
    "Position périmée : rafraîchis la partie.": "Outdated position: refresh the game.",
    "Temps écoulé.": "Time’s up.",
    "Tu es déjà dans cette partie.": "You’re already in this game.",
    "Type de partie inconnu.": "Unknown game type.",
    "Le mode Tactique se joue en match.": "Tactic is played as a match.",
    "Pas de revanche pendant un match : lance un nouveau match.": "No rematch inside a match: start a new match.",
    "Match introuvable.": "Match not found.",
    "Le match a déjà commencé.": "The match has already started.",
    "Tu es déjà dans ce match.": "You’re already in this match.",
    "Ce n'est pas le moment de choisir une carte.": "It’s not time to choose a map.",
    "Carte indisponible.": "Map not available.",
    "Puzzle introuvable.": "Puzzle not found.",
    "Aucun puzzle disponible.": "No puzzle available.",
    "Ce puzzle est terminé.": "This puzzle is over.",
    "Mode de Rush inconnu.": "Unknown Rush mode.",
    "Rush introuvable.": "Rush not found.",
    "Mode inconnu.": "Unknown mode.",
    "Niveau de bot inconnu.": "Unknown bot level.",
    "Terrain inconnu.": "Unknown terrain.",
    "Action inconnue.": "Unknown action.",
    "Seule une partie terminée peut être analysée.": "Only a finished game can be reviewed.",
    "Coup illégal.": "Illegal move.",
    "La partie est terminée.": "The game is over.",
    # Bac à sable (page Règles)
    "Hauteurs hors limites.": "Heights out of range.",
    "Pièces en double.": "Duplicate pieces.",
    # Limites
    "Trop de parties ouvertes en même temps.": "Too many games open at once.",
    "Trop de requêtes. Réessaie dans un instant.": "Too many requests. Try again in a moment.",
}


def lang_of(value: str | None) -> str:
    return value if value in LANGS else "fr"


def translate(message: str, lang: str) -> str:
    if lang == "en" and isinstance(message, str):
        return EN.get(message, message)
    return message
