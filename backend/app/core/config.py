from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_env: str = "development"
    app_secret_key: str = ""
    app_debug: bool = True
    allowed_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
    ]

    # Database
    database_url: str = "postgresql+asyncpg://vn_accounting:vn_accounting_dev@localhost:5432/vn_accounting"
    database_url_sync: str = "postgresql://vn_accounting:vn_accounting_dev@localhost:5432/vn_accounting"
    seed_demo_data: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30
    password_reset_token_expire_minutes: int = 30

    # SMTP
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True

    # Sentry
    sentry_dsn: str = ""

    def model_post_init(self, *args, **kwargs):
        if self.app_env == "production":
            if not self.jwt_secret_key:
                raise ValueError("JWT_SECRET_KEY must be set in production")
            if not self.app_secret_key or self.app_secret_key in ("", "changeme"):
                raise ValueError("APP_SECRET_KEY must be set to a secure random value in production")

    # OCR Engine: google (production), paddle (offline fallback), mock (dev/tests)
    ocr_engine: str = "google"  # google | paddle | mock
    paddleocr_lang: str = "vi"
    paddleocr_use_gpu: bool = False
    paddleocr_timeout_seconds: int = 45
    google_application_credentials: str = ""  # path to service-account JSON file

    # Google Cloud Vision (production default)
    google_cloud_project: str = ""  # GCP project ID for billing
    google_cloud_credentials_json: str = ""  # paste full service-account JSON as string
    ocr_timeout_seconds: int = 60  # per-page timeout for OCR operations

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"

    # Cloudflare R2
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "vn-accounting-documents"
    r2_public_url: str = ""
    local_storage_dir: str = "./storage"
    use_celery: bool = False

    # Vietnam GDT
    gdt_api_base_url: str = "https://hoadondientu.gdt.gov.vn:8443"
    gdt_api_username: str = ""
    gdt_api_password: str = ""
    gdt_tax_code: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
