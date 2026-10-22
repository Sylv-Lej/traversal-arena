from pathlib import Path

from revkit.settings import Settings


class Storage:
    """Abstraction over Scaleway Object Storage (S3) with a local-disk fallback.

    Les objets sont **privés** : le bucket n'accorde aucun accès anonyme et rien n'est
    servi en HTTP. La valeur renvoyée par `put()` est une *référence* archivée en base,
    pas une URL publiquement récupérable — accéder au contenu demande les clés S3.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = None
        if settings.uses_s3:
            import boto3

            self._client = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint,
                region_name=settings.s3_region,
                aws_access_key_id=settings.s3_access_key,
                aws_secret_access_key=settings.s3_secret_key,
            )
        else:
            Path(settings.storage_local_dir).mkdir(parents=True, exist_ok=True)

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """Store bytes under ``key`` and return the stored reference (not a public URL)."""
        if self._client:
            self._client.put_object(
                Bucket=self.settings.s3_bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                # Pas d'ACL public-read : l'objet hérite du bucket, qui est privé.
            )
            # Référence archivée en base. Pas une URL : le bucket est privé, le
            # contenu n'est accessible qu'avec les clés S3.
            return f"s3://{self.settings.s3_bucket}/{key}"

        path = Path(self.settings.storage_local_dir) / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return f"file://{path}"


_storage: Storage | None = None


def get_storage(settings: Settings | None = None) -> Storage:
    global _storage
    if _storage is None:
        from revkit.settings import get_settings

        _storage = Storage(settings or get_settings())
    return _storage
