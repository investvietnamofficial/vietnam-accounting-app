"""Document storage service.

Uses Cloudflare R2 when credentials are configured. In development it falls
back to local filesystem storage so the MVP works without cloud setup.

Security notes:
- R2 buckets MUST be private (block public access). Use signed URLs for all
  downloads to enforce authentication and prevent unauthorised document access.
- R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY must never be committed to source
  control or baked into Docker images — always load from secrets/env vars.
"""
import uuid
from pathlib import Path
from urllib.parse import unquote, urlparse

try:
    import boto3
except ImportError:  # local MVP mode can run without boto3 installed
    boto3 = None
from app.core.config import get_settings

settings = get_settings()


class R2Service:
    def __init__(self):
        self.use_local = not all([
            settings.r2_account_id,
            settings.r2_access_key_id,
            settings.r2_secret_access_key,
            settings.r2_public_url,
        ])
        self.local_root = Path(settings.local_storage_dir).resolve()
        self.client = None
        if not self.use_local:
            if boto3 is None:
                raise RuntimeError("boto3 is required when R2 storage is configured")
            self.client = boto3.client(
                "s3",
                endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
                aws_access_key_id=settings.r2_access_key_id,
                aws_secret_access_key=settings.r2_secret_access_key,
            )

    async def upload(self, content: bytes, filename: str, mime_type: str, folder: str = "") -> str:
        """Upload file to R2, return internal R2 path for signed-URL retrieval."""
        key = f"{folder}/{uuid.uuid4()}_{filename}".lstrip("/")
        if self.use_local:
            path = self.local_root / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            return f"local://{path}"

        self.client.put_object(Bucket=settings.r2_bucket_name, Key=key, Body=content, ContentType=mime_type)
        # Return the S3/R2 key; callers should use get_signed_download_url() for access
        return key

    async def get_signed_download_url(self, key: str, expires_seconds: int = 3600) -> str:
        """
        Generate a time-limited signed URL for secure document download.
        This is the ONLY supported way to access R2 documents — never expose
        raw R2_PUBLIC_URL links directly to clients.
        """
        if self.use_local:
            return f"local://{self.local_root / key}"

        if not key.startswith("local://"):
            # Detect if R2_PUBLIC_URL bucket appears publicly accessible
            public_check = f"{settings.r2_public_url}/{key}"
            # Warn operators; in production, prefer disabling public access entirely
            # self._warn_if_public_bucket()  # re-enable after verification
            try:
                url = self.client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": settings.r2_bucket_name, "Key": key},
                    ExpiresIn=expires_seconds,
                )
                return url
            except Exception as exc:
                raise RuntimeError(f"Failed to generate signed URL for {key}: {exc}")
        return key

    async def download(self, url: str) -> bytes:
        """Download file from R2 by key or signed URL."""
        if url.startswith("local://"):
            parsed = urlparse(url)
            return Path(unquote(parsed.path)).read_bytes()

        # If it's a full URL (signed URL), extract the key from the path
        key = url.replace(f"{settings.r2_public_url}/", "")
        response = self.client.get_object(Bucket=settings.r2_bucket_name, Key=key)
        return response["Body"].read()
