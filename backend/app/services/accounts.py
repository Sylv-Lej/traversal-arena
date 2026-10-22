"""Comptes : chacun commence invité, et peut « réclamer » son compte avec un email et un
mot de passe (il garde alors son pseudo, ses parties et son classement).

Mots de passe hachés en argon2id ; vérification hors de la boucle asyncio (coûteuse
exprès, ~50 ms).
"""

import asyncio
import logging
import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.countries import normalize_country
from app.services import limits, mailer
from app.services.store import Player, store

log = logging.getLogger("traversal.accounts")
_hasher = PasswordHasher()
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
MIN_PASSWORD = 8


class AccountError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def normalize_email(email: str) -> str:
    email = email.strip().lower()
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise AccountError(422, "Adresse email invalide.")
    return email


def check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise AccountError(422, f"Mot de passe trop court ({MIN_PASSWORD} caractères minimum).")
    if len(password) > 256:
        raise AccountError(422, "Mot de passe trop long.")


async def signup(me: Player, email: str, password: str, country: str | None, lang: str = "fr") -> Player:
    """Transforme le compte invité courant en compte permanent (avec le pays représenté),
    et envoie le lien de confirmation de l'adresse."""
    if not me.is_guest:
        raise AccountError(409, "Tu as déjà un compte.")
    email = normalize_email(email)
    check_password(password)
    code = normalize_country(country)
    if code is None:
        raise AccountError(422, "Choisis le pays que tu représentes.")
    if await store.email_taken(email):
        raise AccountError(409, "Cette adresse est déjà utilisée : connecte-toi plutôt.")
    me.password_hash = await asyncio.to_thread(_hasher.hash, password)
    me.email = email
    me.country = code
    me.email_verified_at = None
    await store.save_player(me)
    _background(_send_verification(me.id, lang))
    return me


# Anti-force brute PAR ADRESSE (en plus de la limite par IP) : après 5 échecs, plus
# d'essai pendant 15 min. Compté pour toute adresse, qu'elle ait un compte ou non : le
# blocage ne révèle pas l'existence du compte.
LOGIN_FAILURES = 5
LOGIN_LOCK_S = 15 * 60


async def login(email: str, password: str) -> tuple[Player, str]:
    email = normalize_email(email)
    fail_key = f"loginfail:{email}"
    if await limits.count(fail_key, LOGIN_LOCK_S) >= LOGIN_FAILURES:
        raise AccountError(429, f"Trop d'essais pour cette adresse : réessaie dans {LOGIN_LOCK_S // 60} minutes, "
                                "ou utilise « mot de passe oublié ».")
    player = await store.player_by_email(email)
    stored = player.password_hash if player else None
    try:
        # Même sans compte, on hache pour ne pas révéler par le temps de réponse
        # si l'adresse existe.
        await asyncio.to_thread(_hasher.verify, stored or _DUMMY, password)
        if player is None:
            raise VerifyMismatchError
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        await limits.hit(fail_key, LOGIN_FAILURES, LOGIN_LOCK_S)
        raise AccountError(401, "Email ou mot de passe incorrect.") from None
    await limits.forget(fail_key)
    if _hasher.check_needs_rehash(stored):
        player.password_hash = await asyncio.to_thread(_hasher.hash, password)
        await store.save_player(player)
    return player, await store.new_session(player)


async def _verify(player: Player | None, password: str) -> bool:
    try:
        await asyncio.to_thread(_hasher.verify, (player.password_hash if player else None) or _DUMMY, password)
        return player is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# Anti-spam : au plus un email de réinitialisation par adresse et par minute (compté en
# base : vrai pour toutes les instances).
RESET_MAIL_INTERVAL_S = 60
_mail_tasks: set[asyncio.Task] = set()


async def forgot_password(email: str, lang: str = "fr") -> None:
    """Envoie un lien de réinitialisation si le compte existe. Répond pareil, et aussi
    vite, dans tous les cas : ni la réponse ni sa durée ne révèlent si une adresse a un
    compte (l'email part en arrière-plan)."""
    try:
        email = normalize_email(email)
    except AccountError:
        return
    if not await limits.hit(f"resetmail:{email}", 1, RESET_MAIL_INTERVAL_S):
        return
    _background(_send_reset(email, lang))


def _background(coro) -> None:
    """Email envoyé en arrière-plan : la réponse ne dépend pas de l'envoi."""
    task = asyncio.get_running_loop().create_task(coro)
    _mail_tasks.add(task)  # garde une référence : sinon la tâche peut être ramassée
    task.add_done_callback(_mail_tasks.discard)


async def _send_reset(email: str, lang: str) -> None:
    try:
        player = await store.player_by_email(email)
        if player is None or player.is_guest:
            return
        token = await store.create_reset(player)
        await mailer.send_password_reset(email, player.name, token, lang)
    except Exception:
        log.exception("email de réinitialisation non envoyé")


# --- Confirmation de l'adresse -----------------------------------------------------------

VERIFY_MAIL_INTERVAL_S = 60


async def _send_verification(player_id: str, lang: str) -> None:
    try:
        player = await store.get_player(player_id)
        if player is None or player.is_guest or player.email_verified_at:
            return
        token = await store.create_verification(player)
        await mailer.send_email_verification(player.email, player.name, token, lang)
    except Exception:
        log.exception("email de confirmation non envoyé")


async def resend_verification(me: Player, lang: str = "fr") -> None:
    if me.is_guest:
        raise AccountError(409, "Crée d'abord un compte.")
    if me.email_verified_at:
        raise AccountError(409, "Ton adresse est déjà confirmée.")
    if not await limits.hit(f"verifymail:{me.id}", 1, VERIFY_MAIL_INTERVAL_S):
        raise AccountError(429, "Email déjà envoyé : réessaie dans une minute.")
    _background(_send_verification(me.id, lang))


async def verify_email(token: str) -> Player:
    player = await store.consume_verification(token)
    if player is None:
        raise AccountError(400, "Ce lien n'est plus valable : redemande un email de confirmation.")
    return player


async def flush_mails() -> None:
    """Tests : attend les emails en cours d'envoi."""
    if _mail_tasks:
        await asyncio.gather(*list(_mail_tasks), return_exceptions=True)


async def reset_password(token: str, password: str) -> tuple[Player, str]:
    """Nouveau mot de passe via le lien reçu : déconnecte tous les appareils, puis ouvre
    une session neuve (le relais la pose en cookie)."""
    check_password(password)
    player = await store.consume_reset(token)
    if player is None:
        raise AccountError(400, "Ce lien n'est plus valable : redemande un email de réinitialisation.")
    player.password_hash = await asyncio.to_thread(_hasher.hash, password)
    await store.save_player(player)
    await store.end_sessions_of(player.id)
    return player, await store.new_session(player)


async def change_password(me: Player, current: str, new: str, session_token: str) -> None:
    """Changement de mot de passe connecté : les AUTRES appareils sont déconnectés."""
    if me.is_guest:
        raise AccountError(409, "Crée d'abord un compte.")
    if not await _verify(me, current):
        raise AccountError(401, "Mot de passe actuel incorrect.")
    check_password(new)
    me.password_hash = await asyncio.to_thread(_hasher.hash, new)
    await store.save_player(me)
    await store.end_sessions_of(me.id, keep_token=session_token)


_DUMMY = _hasher.hash("pas-un-vrai-mot-de-passe")
