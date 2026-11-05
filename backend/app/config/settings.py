"""Application settings for the OAN (Open Agri Net) sandbox backend.

Values are read from the environment / `.env`. Every setting has a safe
development default so the app boots without a fully populated `.env`;
production deployments are expected to override the secrets.
"""

import json
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
    #: Turns on /docs, /redoc and /openapi.json. Keep off on shared servers.
    DEBUG: bool = False
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
    GATEWAY_UAT_URL: str = ""
    GATEWAY_PROD_URL: str = ""
    # The same gateway as participants reach it (Postman, their own code), shown
    # in code samples, the try-it request URL and API history. Needed when the
    # API reaches the gateway on an internal address (host.docker.internal, a
    # cluster service name). Empty = the URL above.
    GATEWAY_UAT_PUBLIC_URL: str = ""
    GATEWAY_PROD_PUBLIC_URL: str = ""
    SANDBOX_PROXY_TIMEOUT: int = 30
    #: Answer try-it calls for endpoints with no gateway/upstream from their
    #: stored samples. Off: every call goes through the API gateway.
    SANDBOX_MOCK_RESPONSES: bool = False

    # "Pull from gateway" in the console: reads the gateway's Admin API and
    # creates or updates catalogue end-points from its routes. Off by default;
    # the console shows the button only when this is on.
    GATEWAY_SYNC_ENABLED: bool = False
    #: Which gateway's Admin API to read.
    GATEWAY_TYPE: Literal["apisix", "kong"] = "apisix"
    #: Admin API base URL, e.g. http://apisix-admin:9180 or http://kong-admin:8001.
    GATEWAY_ADMIN_URL: str = ""
    #: APISIX admin key (X-API-KEY) or Kong Enterprise admin token
    #: (Kong-Admin-Token); empty for an Admin API without authentication.
    GATEWAY_ADMIN_TOKEN: str = ""
    GATEWAY_ADMIN_TIMEOUT: int = 15

    # ------------------------------------------------- apps and credentials
    # Participants create apps, each with an API key + secret and a set of
    # API products. With sync on, every app is written to the gateway's Admin
    # API (GATEWAY_ADMIN_URL; APISIX only) as a consumer; the admin key then
    # needs write access. Off: apps and keys live only in the sandbox.
    GATEWAY_APP_SYNC_ENABLED: bool = False
    #: Header the gateway's key-auth reads the API key from.
    GATEWAY_APP_KEY_HEADER: str = "apikey"
    #: What the gateway checks. "apikey": an app's API key (key-auth, above).
    #: "keycloak": the app's API key AND the participant's Keycloak access
    #: token in GATEWAY_PARTNER_TOKEN_HEADER (openid-connect: JWKS signature,
    #: iss, exp, the environment's role), and that the app belongs to the
    #: token's participant (consumer label participant_uid). Try-it then also
    #: sends the signed-in participant's own Keycloak token. Needs
    #: PARTICIPANT_AUTH_PROVIDER=keycloak. Must match how the gateway was built.
    #: "oauth" (OAuth 2.0 client credentials, the standard for server-to-server
    #: calls): every active API key of an app is also a Keycloak confidential
    #: client (client_id = API key, client_secret = API secret) whose access
    #: token carries participant_uid, oan_app, oan_environments and oan_routes
    #: (the routes of the app's approved API products). The partner gets a
    #: token with grant_type=client_credentials and sends only that token in
    #: GATEWAY_PARTNER_TOKEN_HEADER; the gateway checks it (no API key per
    #: call). Needs KEYCLOAK_PROVISIONING_ENABLED and GATEWAY_APP_SYNC_ENABLED.
    GATEWAY_PARTNER_AUTH: Literal["apikey", "keycloak", "oauth"] = "apikey"
    GATEWAY_PARTNER_TOKEN_HEADER: str = "X-Partner-Token"
    #: Fernet key (``Fernet.generate_key()``) encrypting stored keys/secrets.
    #: Required in production; changing it makes stored credentials unreadable.
    APP_CREDENTIAL_ENCRYPTION_KEY: str = ""
    MAX_APPS_PER_PARTICIPANT: int = 10
    #: Active credentials per app - two allows rotating without downtime.
    MAX_ACTIVE_CREDENTIALS_PER_APP: int = 2
    #: Addresses (IP or CIDR) a participant may list for an app's IP whitelist.
    MAX_ALLOWED_IPS_PER_APP: int = 20

    # -------------------------------------------- gateway logs (callback)
    # Apps called directly (Postman, the participant's own servers) never pass
    # through the sandbox. With this on, each app's consumer gets APISIX's
    # http-logger, which posts batches of call records to the sandbox's
    # callback (POST {API_PREFIX}/internal/gateway/logs) so API history shows
    # them too. Off: API history shows try-it calls only, as before.
    GATEWAY_LOG_INGEST_ENABLED: bool = False
    #: The callback URL as APISIX reaches it, e.g.
    #: http://host.docker.internal:8010/oan/internal/gateway/logs.
    GATEWAY_LOG_INGEST_URL: str = ""
    #: Shared secret APISIX sends as "Authorization: Bearer <token>".
    GATEWAY_LOG_INGEST_TOKEN: str = ""
    #: Seconds APISIX waits before sending a part-filled batch.
    GATEWAY_LOG_FLUSH_SECONDS: int = 5

    # --------------------------------------- participant users (Keycloak)
    # Every participant is a Keycloak user (username = email, same password as
    # the portal), created at sign-up. Approving an environment gives the user
    # that environment's role (uat / production) of one shared client
    # (KEYCLOAK_PARTNER_CLIENT_ID); a token is requested with the password
    # grant on that client. The sandbox signs in with its own service-account
    # client (KEYCLOAK_ADMIN_CLIENT_*), never the Keycloak admin user; set it
    # up with scripts/keycloak/setup_partner_realm.py. Off: nothing is created.
    KEYCLOAK_PROVISIONING_ENABLED: bool = False
    #: Keycloak as the API reaches it, e.g. http://host.docker.internal:8080.
    KEYCLOAK_URL: str = ""
    #: Keycloak as participants reach it (token URL shown to them); empty = KEYCLOAK_URL.
    KEYCLOAK_PUBLIC_URL: str = ""
    KEYCLOAK_REALM: str = "oan-partners"
    KEYCLOAK_ADMIN_CLIENT_ID: str = "oan-sandbox-provisioner"
    KEYCLOAK_ADMIN_CLIENT_SECRET: str = ""
    KEYCLOAK_TIMEOUT: int = 15
    #: Approvals that give a role: any of UAT, PRODUCTION.
    KEYCLOAK_ENVIRONMENTS: str = "UAT,PRODUCTION"
    #: Shared client participants get tokens from; holds the environment roles.
    KEYCLOAK_PARTNER_CLIENT_ID: str = "oan-partner-api"

    @property
    def keycloak_environments(self) -> set[str]:
        return {e.strip().upper() for e in self.KEYCLOAK_ENVIRONMENTS.split(",") if e.strip()}

    # ------------------------------------- participant sign-in (Keycloak)
    # "local": the portal sign-in checks the sandbox's own password hash and
    # issues the sandbox's own JWT (as before). "keycloak": Keycloak checks
    # the password and issues the tokens. The portal's sign-in form stays; the
    # API asks Keycloak (direct grant on the confidential client
    # KEYCLOAK_LOGIN_CLIENT_ID), hands the portal Keycloak's access and refresh
    # tokens, and verifies every Keycloak access token itself (signature from
    # the realm's JWKS with RS256 pinned, iss, exp / nbf, typ, azp, jti) plus the
    # sandbox session (x-auth-key) it belongs to. Refresh and sign-out go to
    # Keycloak. A participant not approved yet has no Keycloak user: its
    # sign-in is refused with the same messages as before. Needs Keycloak
    # provisioning on.
    PARTICIPANT_AUTH_PROVIDER: Literal["local", "keycloak"] = "local"
    #: Confidential client (direct access grants only) the sign-in uses.
    KEYCLOAK_LOGIN_CLIENT_ID: str = "oan-sandbox-portal"
    KEYCLOAK_LOGIN_CLIENT_SECRET: str = ""
    #: ``iss`` of the realm's tokens. Empty = {KEYCLOAK_PUBLIC_URL or KEYCLOAK_URL}/realms/{realm}
    #: (Keycloak writes its public hostname, KC_HOSTNAME, into tokens).
    KEYCLOAK_ISSUER: str = ""
    #: Where the realm's signing keys are read. Empty = {KEYCLOAK_URL}/realms/{realm}/protocol/openid-connect/certs.
    KEYCLOAK_JWKS_URL: str = ""
    #: Accepted clock difference with Keycloak, seconds.
    KEYCLOAK_TOKEN_LEEWAY_SECONDS: int = 30
    #: How long the realm's signing keys are reused before they are read again.
    KEYCLOAK_JWKS_CACHE_SECONDS: int = 300

    @property
    def keycloak_login(self) -> bool:
        return self.PARTICIPANT_AUTH_PROVIDER == "keycloak"

    @property
    def keycloak_issuer(self) -> str:
        base = (self.KEYCLOAK_PUBLIC_URL or self.KEYCLOAK_URL).rstrip("/")
        return (self.KEYCLOAK_ISSUER or f"{base}/realms/{self.KEYCLOAK_REALM}").rstrip("/")

    @property
    def keycloak_jwks_url(self) -> str:
        return self.KEYCLOAK_JWKS_URL or (
            f"{self.KEYCLOAK_URL.rstrip('/')}/realms/{self.KEYCLOAK_REALM}/protocol/openid-connect/certs"
        )

    @model_validator(mode="after")
    def _check_keycloak_login(self) -> "Settings":
        if self.keycloak_login and not (
            self.KEYCLOAK_PROVISIONING_ENABLED
            and self.KEYCLOAK_URL
            and self.KEYCLOAK_LOGIN_CLIENT_ID
            and self.KEYCLOAK_LOGIN_CLIENT_SECRET
        ):
            raise ValueError(
                "PARTICIPANT_AUTH_PROVIDER=keycloak needs KEYCLOAK_PROVISIONING_ENABLED, KEYCLOAK_URL, "
                "KEYCLOAK_LOGIN_CLIENT_ID and KEYCLOAK_LOGIN_CLIENT_SECRET."
            )
        if self.GATEWAY_PARTNER_AUTH == "oauth" and not (
            self.KEYCLOAK_PROVISIONING_ENABLED and self.GATEWAY_APP_SYNC_ENABLED
        ):
            raise ValueError(
                "GATEWAY_PARTNER_AUTH=oauth needs KEYCLOAK_PROVISIONING_ENABLED and GATEWAY_APP_SYNC_ENABLED: "
                "every app key is written to Keycloak as an OAuth client."
            )
        if self.GATEWAY_PARTNER_AUTH == "keycloak" and not self.keycloak_login:
            raise ValueError(
                "GATEWAY_PARTNER_AUTH=keycloak needs PARTICIPANT_AUTH_PROVIDER=keycloak: try-it sends "
                "the participant's Keycloak access token to the gateway."
            )
        return self

    # ------------------------- Consent Manager partner portal (OpenG2P CM)
    # The same Keycloak user also signs in to the OpenG2P Consent Manager's
    # partner portal. For that, KEYCLOAK_REALM is the CM's partner realm
    # (`partner`, set up by the CM chart) and an approved participant gets the
    # portal client's role and a `partner_id` user attribute (read into the
    # CM's `partner_id` claim). Empty client id: nothing for the portal.
    #: The CM partner portal client in KEYCLOAK_REALM, e.g. consent-partner-portal.
    KEYCLOAK_PORTAL_CLIENT_ID: str = ""
    #: Portal client role an approved participant holds (PARTNER_OPERATOR or PARTNER_ADMIN).
    KEYCLOAK_PORTAL_ROLE: str = "PARTNER_OPERATOR"
    #: User attribute the CM's token mapper reads into the `partner_id` claim.
    KEYCLOAK_PARTNER_ID_ATTRIBUTE: str = "partner_id"
    #: A participant's partner ID: this prefix + its participant id (oan-p-42).
    #: Do not change it once partners exist: it is their ID in the CM and PM.
    PARTNER_ID_PREFIX: str = "oan-p-"

    # -------------------------------------- Partner Management (OpenG2P PM)
    # An approved participant is also onboarded (and approved) as a partner in
    # OpenG2P Partner Management, where the CM reads the partner's access
    # policies from; reject / disable / delete disables it there. The sandbox
    # signs in to PM's staff API with its own service-account client (in the
    # realm PM trusts, holding PM's admin role). Needs Keycloak provisioning
    # on. Off: nothing is sent to PM.
    PM_PROVISIONING_ENABLED: bool = False
    #: PM staff-portal API as the sandbox reaches it, e.g. http://commons-services-pm-staff-portal-api.
    PM_STAFF_API_URL: str = ""
    #: Token endpoint of the realm PM's staff API trusts (client-credentials grant).
    PM_TOKEN_URL: str = ""
    PM_CLIENT_ID: str = "oan-sandbox-pm"
    PM_CLIENT_SECRET: str = ""
    PM_TIMEOUT: int = 15
    #: This API as PM reaches it, e.g. https://api.sandbox.example.org/oan. PM
    #: reads a partner's keys from <this>/partners/<partner_id>/jwks.json when
    #: it needs them (PM requires a key or a JWKS URL to onboard).
    PM_PARTNER_JWKS_BASE_URL: str = ""
    #: Access policies given at onboarding: a JSON list of PM PolicyInput
    #: objects. "[]": none - PM staff add them; the portal shows no access until then.
    PM_DEFAULT_POLICIES: str = "[]"

    @field_validator("PM_DEFAULT_POLICIES")
    @classmethod
    def _check_pm_policies(cls, v: str) -> str:
        try:
            value = json.loads(v or "[]")
        except ValueError as exc:
            raise ValueError("PM_DEFAULT_POLICIES must be JSON.") from exc
        if not isinstance(value, list) or not all(isinstance(p, dict) for p in value):
            raise ValueError("PM_DEFAULT_POLICIES must be a JSON list of objects.")
        return v or "[]"

    @property
    def pm_default_policies(self) -> list[dict]:
        return json.loads(self.PM_DEFAULT_POLICIES)

    # --------------------------------------------- rate limits per product
    # API products carry an optional per-minute limit and per-day quota; an
    # app gets the most generous of its approved products' values as an
    # APISIX limit-count on its consumer (429 when crossed). Off: no limits.
    GATEWAY_RATE_LIMIT_ENABLED: bool = False
    #: "local" counts per APISIX node; "redis" shares counts between nodes.
    GATEWAY_RATE_LIMIT_POLICY: Literal["local", "redis"] = "local"
    #: Redis as APISIX reaches it (policy "redis").
    GATEWAY_RATE_LIMIT_REDIS_HOST: str = ""
    GATEWAY_RATE_LIMIT_REDIS_PORT: int = 6379
    GATEWAY_RATE_LIMIT_REDIS_PASSWORD: str = ""

    # --------------------------------------------------------------- logging
    LOG_LEVEL: str = "INFO"
    LOG_TO_DB: bool = True
    LOG_DIR: str = "logs"

    # OTP / registration policy
    OTP_LENGTH: int = 6
    OTP_TTL_SECONDS: int = 300
    OTP_MAX_REQUESTS_PER_HOUR: int = 5
    #: Code a participant password reset accepts while mail cannot be sent
    #: (MAIL_ENABLED=false), so testers can reset without SMTP. Honoured only
    #: when ENV=local - anyone who knows it can reset any participant account -
    #: and never for administrators. Empty = always random codes.
    DEV_FIXED_OTP: str = ""
    #: Wrong codes allowed before an OTP is discarded.
    OTP_MAX_ATTEMPTS: int = 5

    # Sign-in / reset throttling (per account and per client IP).
    LOGIN_MAX_FAILURES: int = 5
    LOGIN_LOCKOUT_SECONDS: int = 900
    AUTH_RATE_LIMIT_PER_MINUTE: int = 20

    # Sessions (x-auth-key) end after this much inactivity, and at the latest
    # this long after sign-in.
    SESSION_IDLE_TIMEOUT_SECONDS: int = 2 * 3600
    SESSION_MAX_AGE_SECONDS: int = 24 * 3600

    #: Proxies whose X-Forwarded-For / X-Real-IP is believed (IPs or CIDRs).
    #: Empty = use the socket address only.
    TRUSTED_PROXIES: str = "127.0.0.1,::1"

    @model_validator(mode="after")
    def _check_fixed_otp(self) -> "Settings":
        code = self.DEV_FIXED_OTP
        if code and not (code.isdigit() and len(code) == self.OTP_LENGTH):
            raise ValueError(
                f"DEV_FIXED_OTP must be {self.OTP_LENGTH} digits (e.g. 000000) or empty."
            )
        return self

    @model_validator(mode="after")
    def _check_secrets(self) -> "Settings":
        """Refuse to start a shared server with guessable signing keys."""
        if self.ENV == "local" or self.is_sqlite:
            return self
        weak = {"", "change-me-access-secret", "change-me-refresh-secret"}
        for name in ("JWT_ACCESS_TOKEN_KEY", "JWT_REFRESH_TOKEN_KEY"):
            value = getattr(self, name)
            if value in weak or len(value) < 32:
                raise ValueError(f"{name} must be a random value of at least 32 characters.")
        if self.JWT_ACCESS_TOKEN_KEY == self.JWT_REFRESH_TOKEN_KEY:
            raise ValueError("JWT_ACCESS_TOKEN_KEY and JWT_REFRESH_TOKEN_KEY must differ.")
        return self

    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def _strip_origins(cls, v: str) -> str:
        return ",".join(part.strip() for part in v.split(",") if part.strip())

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o for o in self.ALLOWED_ORIGINS.split(",") if o]

    @property
    def mail_active(self) -> bool:
        """True when mail can actually be sent (enabled and an SMTP host set)."""
        return self.MAIL_ENABLED and bool(self.SMTP_HOST)

    @property
    def fixed_otp(self) -> str | None:
        """The development code in force, or None when real codes are sent.

        Only a developer's own machine (ENV=local) with mail off uses it.
        """
        if self.MAIL_ENABLED or self.ENV != "local":
            return None
        return self.DEV_FIXED_OTP or None

    @property
    def trusted_proxies_list(self) -> list[str]:
        return [p.strip() for p in self.TRUSTED_PROXIES.split(",") if p.strip()]

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
