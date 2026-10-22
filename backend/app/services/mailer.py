"""Envoi d'emails via Scaleway Transactional Email (TEM).

Configuré par l'environnement (12-factor) :
- MAIL_FROM            adresse d'expédition, sur un domaine VÉRIFIÉ dans TEM
- TEM_SECRET_KEY       clé IAM Scaleway limitée à TEM (pas la clé d'admin du projet)
- TEM_PROJECT_ID       projet Scaleway du domaine
- TEM_REGION           défaut fr-par
- PUBLIC_URL           URL publique du site, pour les liens (défaut http://localhost:3000)

Sans configuration (dev local, tests), rien n'est envoyé : le message est écrit dans les
logs du backend et gardé dans `outbox` — le lien de réinitialisation se lit là.
"""

import logging
import os

import httpx

log = logging.getLogger("traversal.mail")

outbox: list[dict] = []  # messages non envoyés (dev / tests)


def public_url() -> str:
    return os.getenv("PUBLIC_URL", "http://localhost:3000").rstrip("/")


async def send(to: str, subject: str, text: str, html: str) -> None:
    sender = os.getenv("MAIL_FROM", "")
    key = os.getenv("TEM_SECRET_KEY", "")
    project = os.getenv("TEM_PROJECT_ID", "")
    region = os.getenv("TEM_REGION", "fr-par")
    if not (sender and key and project):
        outbox.append({"to": to, "subject": subject, "text": text, "html": html})
        log.warning("[email non envoyé — TEM non configuré] à %s : %s\n%s", to, subject, text)
        return
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"https://api.scaleway.com/transactional-email/v1alpha1/regions/{region}/emails",
            headers={"X-Auth-Token": key},
            json={
                "from": {"email": sender, "name": "Traversal Bot Arena"},
                "to": [{"email": to}],
                "subject": subject,
                "text": text,
                "html": html,
                "project_id": project,
            },
        )
    if r.status_code >= 300:
        # On journalise sans jamais renvoyer l'erreur au visiteur (pas d'énumération).
        log.error("TEM %s : %s", r.status_code, r.text[:300])


RESET_MAIL = {
    "fr": {
        "subject": "Réinitialise ton mot de passe Traversal",
        "hello": "Bonjour {name},",
        "asked": "Quelqu'un (sans doute toi) a demandé à réinitialiser le mot de passe de ton compte Traversal.",
        "open": "Pour choisir un nouveau mot de passe, ouvre ce lien (valable 1 heure) :",
        "button": "Choisir un nouveau mot de passe",
        "valid": "Ce lien est valable 1 heure.",
        "ignore": "Si tu n'es pas à l'origine de cette demande, ignore simplement cet email : ton mot de passe ne change pas.",
    },
    "en": {
        "subject": "Reset your Traversal password",
        "hello": "Hi {name},",
        "asked": "Someone (probably you) asked to reset the password of your Traversal account.",
        "open": "To choose a new password, open this link (valid for 1 hour):",
        "button": "Choose a new password",
        "valid": "This link is valid for 1 hour.",
        "ignore": "If you didn't request this, just ignore this email: your password won't change.",
    },
}


async def send_password_reset(to: str, name: str, token: str, lang: str = "fr") -> None:
    m = RESET_MAIL.get(lang, RESET_MAIL["fr"])
    link = f"{public_url()}/reset?token={token}"
    text = f"{m['hello'].format(name=name)}\n\n{m['asked']} {m['open']}\n\n{link}\n\n{m['ignore']}\n"
    html = (
        f"<p>{_esc(m['hello'].format(name=name))}</p>"
        f"<p>{_esc(m['asked'])}</p>"
        f'<p><a href="{link}" style="background:#81b64c;color:#fff;padding:10px 18px;'
        f'border-radius:6px;text-decoration:none;font-weight:bold">{_esc(m["button"])}</a></p>'
        f"<p>{_esc(m['valid'])} {_esc(m['ignore'])}</p>"
    )
    await send(to, m["subject"], text, html)


VERIFY_MAIL = {
    "fr": {
        "subject": "Confirme ton adresse email — Traversal Bot Arena",
        "hello": "Bonjour {name},",
        "why": "Pour inscrire des bots dans l'arène, confirme que cette adresse est bien la tienne :",
        "button": "Confirmer mon adresse",
        "valid": "Ce lien est valable 48 heures.",
        "ignore": "Si tu n'as pas créé de compte, ignore simplement cet email.",
    },
    "en": {
        "subject": "Confirm your email address — Traversal Bot Arena",
        "hello": "Hi {name},",
        "why": "To enter bots in the arena, confirm that this address is yours:",
        "button": "Confirm my address",
        "valid": "This link is valid for 48 hours.",
        "ignore": "If you didn't create an account, just ignore this email.",
    },
}


async def send_email_verification(to: str, name: str, token: str, lang: str = "fr") -> None:
    m = VERIFY_MAIL.get(lang, VERIFY_MAIL["fr"])
    link = f"{public_url()}/verify?token={token}"
    text = f"{m['hello'].format(name=name)}\n\n{m['why']}\n\n{link}\n\n{m['valid']} {m['ignore']}\n"
    html = (
        f"<p>{_esc(m['hello'].format(name=name))}</p>"
        f"<p>{_esc(m['why'])}</p>"
        f'<p><a href="{link}" style="background:#81b64c;color:#fff;padding:10px 18px;'
        f'border-radius:6px;text-decoration:none;font-weight:bold">{_esc(m["button"])}</a></p>'
        f"<p>{_esc(m['valid'])} {_esc(m['ignore'])}</p>"
    )
    await send(to, m["subject"], text, html)


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
