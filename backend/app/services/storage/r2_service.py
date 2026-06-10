"""Document storage service.

Uses Cloudflare R2 when credentials are configured. In development it falls
back to local filesystem storage so the MVP works without cloud setup.
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
        """Upload file to R2, return public URL."""
        key = f"{folder}/{uuid.uuid4()}_{filename}".lstrip("/")
        if self.use_local:
            path = self.local_root / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            return f"local://{path}"

        self.client.put_object(Bucket=settings.r2_bucket_name, Key=key, Body=content, ContentType=mime_type)
        return f"{settings.r2_public_url}/{key}"

    async def download(self, url: str) -> bytes:
        """Download file from R2 by URL."""
        if url.startswith("local://"):
            parsed = urlparse(url)
            return Path(unquote(parsed.path)).read_bytes()

        key = url.replace(f"{settings.r2_public_url}/", "")
        response = self.client.get_object(Bucket=settings.r2_bucket_name, Key=key)
        return response["Body"].read()
