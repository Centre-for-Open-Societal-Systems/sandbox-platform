"""Application settings for the OAN (Open Agri Net) sandbox backend.

Values are read from the environment / `.env`. Every setting has a safe
development default so the app boots without a fully populated `.env`;
production deployments are expected to override the secrets.
"""

from functools import lru_cache
from typing import Literal
from urllib.parse import quote_plus

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ------------------------------------------------------------------ app
    APP_NAME: str = "OAN Sandbox Backend"
    APP_DESCRIPTION: str = (
        "Open Agri Net — developer sandbox for agricultural data exchange. "
        "Open to every member country."
    )
    APP_VERSION: str = "1.0.0"
    ENV: Literal["local", "sandbox", "uat", "production"] = "sandbox"
    DEBUG: bool = True
    API_PREFIX: str = "/oan"
    PORT: int = 8000

    # The default country every tenant-scoped record falls back to. OAN is
    # multi-country by design; Ethiopia is simply the first onboarded member.
    DEFAULT_COUNTRY_CODE: str = "ET"

    # -------------------------------------------------------------- database
    DB_DRIVER: str = "postgresql+psycopg"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = ""
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "sandbox_db_oan"
    DB_SCHEMA: str = "public"
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # Set this to override the assembled URL entirely (e.g. sqlite for tests).
    DATABASE_URL_OVERRIDE: str = ""

    # ------------------------------------------------------------------ auth
    JWT_ACCESS_TOKEN_KEY: str = "change-me-access-secret"
    JWT_REFRESH_TOKEN_KEY: str = "change-me-refresh-secret"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRES: int = 3600  # seconds
    JWT_REFRESH_TOKEN_EXPIRES: int = 86400  # seconds
    BCRYPT_ROUNDS: int = 10

    # Payloads from the browser are RSA-sealed before transit (`post_data`).
    RSA_PRIVATE_KEY_PATH: str = "keys/private_key.pem"
    RSA_PUBLIC_KEY_PATH: str = "keys/public_key.pem"
    RSA_PAYLOAD_ENABLED: bool = False

    # ----------------------------------------------------------------- redis
    REDIS_ENABLED: bool = False
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_EXPIRY: int = 86400

    # ------------------------------------------------------------------ cors
    ALLOWED_ORIGINS: str = "http://localhost:3000"
    #: Web client base URL used in email links; defaults to the first allowed origin.
    PORTAL_URL: str = ""

    # ---------------------------------------------------------------- upload
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_MB: int = 25
    ALLOWED_UPLOAD_EXTENSIONS: str = "pdf,png,jpg,jpeg,webp,csv,xlsx,json,yaml,yml"

    # Object storage. `local` writes to UPLOAD_DIR; `gcs`/`s3` need credentials.
    STORAGE_BACKEND: Literal["local", "gcs", "s3"] = "local"
    STORAGE_BUCKET: str = ""

    # ------------------------------------------------------------------ mail
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "no-reply@openagrinet.org"
    SMTP_TLS: bool = True
    MAIL_ENABLED: bool = False

    # ------------------------------------------------- upstream api gateway
    # The Indian stack fronted its APIs with WSO2 + APISIX. OAN keeps the same
    # seam so a member country can plug in whichever gateway it operates.
    # Endpoints flagged "served through the gateway" (on the endpoint or its
    # product) and without an upstream URL of their own are called on the
    # gateway proxy of the requested environment. GATEWAY_BASE_URL is the
    # fallback for an environment without its own URL.
    GATEWAY_ENABLED: bool = False
    GATEWAY_BASE_URL: str = ""
    GATEWAY_SANDBOX_URL: str = ""
    GATEWAY_UAT_URL: str = ""
    GATEWAY_PROD_URL: str = ""
    GATEWAY_ADMIN_TOKEN: str = ""
    SANDBOX_PROXY_TIMEOUT: int = 30

    # --------------------------------------------------------------- logging
    LOG_LEVEL: str = "INFO"
    LOG_TO_DB: bool = True
    LOG_DIR: str = "logs"

    # OTP / registration policy
    OTP_LENGTH: int = 6
    OTP_TTL_SECONDS: int = 300
    OTP_MAX_REQUESTS_PER_HOUR: int = 5
    #: Code every sign-up gets while mail cannot be sent (MAIL_ENABLED=false),
    #: so testers can verify without SMTP. Never used when mail is on or when
    #: ENV=production. Set empty to always generate random codes.
    DEV_FIXED_OTP: str = "000000"

    @model_validator(mode="after")
    def _check_fixed_otp(self) -> "Settings":
        code = self.DEV_FIXED_OTP
        if code and not (code.isdigit() and len(code) == self.OTP_LENGTH):
            raise ValueError(
                f"DEV_FIXED_OTP must be {self.OTP_LENGTH} digits (e.g. 000000) or empty."
            )
        return self

    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def _strip_origins(cls, v: str) -> str:
        return ",".join(part.strip() for part in v.split(",") if part.strip())

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o for o in self.ALLOWED_ORIGINS.split(",") if o]

    @property
    def fixed_otp(self) -> str | None:
        """The development code in force, or None when real codes are sent."""
        if self.MAIL_ENABLED or self.ENV.lower() in ("production", "prod"):
            return None
        return self.DEV_FIXED_OTP or None

    @property
    def portal_url(self) -> str:
        url = self.PORTAL_URL or (self.allowed_origins_list[0] if self.allowed_origins_list else "")
        return url.rstrip("/")

    @property
    def allowed_upload_extensions_set(self) -> set[str]:
        return {
            e.strip().lower().lstrip(".")
            for e in self.ALLOWED_UPLOAD_EXTENSIONS.split(",")
            if e.strip()
        }

    @property
    def DATABASE_URL(self) -> str:
        if self.DATABASE_URL_OVERRIDE:
            return self.DATABASE_URL_OVERRIDE
        # quote_plus so passwords containing @ : / # still parse correctly.
        return (
            f"{self.DB_DRIVER}://{quote_plus(self.DB_USER)}:{quote_plus(self.DB_PASSWORD)}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
