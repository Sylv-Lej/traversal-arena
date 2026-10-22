from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Params de connexion "style libpq" (psql/Lampion) qu'asyncpg ne comprend pas :
# on les retire de l'URL et on gère le SSL via connect_args.
_LIBPQ_ONLY_PARAMS = {"sslmode", "channel_binding"}
_SSL_MODES = {"require", "verify-ca", "verify-full", "prefer", "allow", "disable"}


class Settings(BaseSettings):
    """Base settings shared by every site. Override / extend per site if needed.

    Tout passe par l'environnement (12-factor). La base est TOUJOURS Postgres
    (Lampion), y compris en local : il n'y a pas de repli SQLite, pour que le code
    exécuté en dev soit exactement celui qui tourne en production. Le stockage, lui,
    tombe sur le disque local tant que les clés S3 sont absentes.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "revkit-app"
    # CORS. Vide = aucune origine autorisée (défaut sûr) : le navigateur ne parle
    # plus directement à l'API, il passe par la route serveur du front.
    frontend_origin: str = ""

    # --- Sécurité ---
    # Clé partagée front(serveur) <-> API. Fail-closed : vide = tout est refusé.
    api_key: str = ""
    # Schéma OpenAPI et UI /docs : désactivés par défaut, activés en dev.
    expose_docs: bool = False
    # Limitation de débit (fenêtre glissante, en mémoire).
    rate_limit_requests: int = 20
    rate_limit_window_seconds: float = 60.0

    # --- Database ---
    # Connection string Lampion (postgresql://...), résolue par le Makefile. Requise.
    database_url: str = ""

    # --- Object storage (Scaleway Object Storage, S3-compatible) ---
    # Leave empty in local dev -> files are written to `storage_local_dir` instead.
    s3_bucket: str = ""
    s3_endpoint: str = "https://s3.fr-par.scw.cloud"
    s3_region: str = "fr-par"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    storage_local_dir: str = "./uploads"

    @field_validator("expose_docs", mode="before")
    @classmethod
    def _empty_means_false(cls, value):
        """`EXPOSE_DOCS=` (vide) doit valoir False, pas planter au démarrage.

        Une variable d'environnement déclarée mais vide est courante (compose,
        Terraform, CI). Sans ça, pydantic refuse la chaîne vide et le backend ne
        démarre pas du tout — une panne totale pour un réglage cosmétique.
        """
        if isinstance(value, str) and not value.strip():
            return False
        return value

    @property
    def sqlalchemy_url(self) -> str:
        if not self.database_url:
            raise RuntimeError(
                "DATABASE_URL manquant. La base est toujours Lampion (Postgres), même "
                "en local : lance via `make dev` / `make dev-back`, qui la résout depuis "
                "LAMPION_API_KEY."
            )
        # Normalise to the async driver.
        url = self.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        # Drop libpq-only params (ex. Lampion renvoie ?sslmode=require) :
        # asyncpg les rejette. Le SSL est réappliqué via db_connect_args.
        parts = urlsplit(url)
        if parts.query:
            kept = [
                (k, v)
                for k, v in parse_qsl(parts.query, keep_blank_values=True)
                if k not in _LIBPQ_ONLY_PARAMS
            ]
            url = urlunsplit(parts._replace(query=urlencode(kept)))
        return url

    @property
    def db_connect_args(self) -> dict:
        """connect_args pour create_async_engine. SSL pour Postgres distant (Lampion).

        On repasse le `sslmode` libpq tel quel à asyncpg, qui en implémente la
        sémantique exacte. `ssl=True` ne convient pas : il vérifie comme
        verify-full, alors que Lampion renvoie `sslmode=require` et présente un
        certificat signé par une CA privée -> CERTIFICATE_VERIFY_FAILED.
        """
        if not self.database_url:
            return {}
        mode = dict(parse_qsl(urlsplit(self.database_url).query)).get("sslmode", "").lower()
        if mode in _SSL_MODES:
            return {"ssl": mode}
        return {}

    @property
    def uses_s3(self) -> bool:
        return bool(self.s3_bucket and self.s3_access_key and self.s3_secret_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
