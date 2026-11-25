# Sandbox Platform

Developer sandbox for **EOAN (Open Agri Net)**: a public site with the API catalogue, a
participant portal (sign-up, environment access, try-it console, API history, Help & Support) and an
admin console (participants, products and end-points, Content Management, masters, Support Tickets). Try-it calls are
answered from published samples (mock mode) or routed through the API gateway (Apache APISIX)
of the environment.

## Repository layout

```
sandbox-platform/
├── backend/                 FastAPI + SQLAlchemy 2 + Alembic API (Python 3.12)
│   ├── app/                 controllers → services → repositories → models
│   ├── alembic/             database migrations
│   ├── scripts/             demo catalogue loaders (OpenG2P, A2C), dev helpers
│   ├── tests/               pytest suite (in-memory SQLite)
│   └── .env.example         every backend setting, documented
├── ui/                      Next.js 16 / React 19 web client (public site, portal, console)
│   ├── src/
│   ├── public/
│   ├── Dockerfile           UI image (standalone Next.js server)
│   └── .env.example
├── docker/
│   └── sandbox-api/         API image: Dockerfile + entrypoint (context: repo root)
├── deployment/
│   ├── postgres/initdb/     database snapshot loaded on the first Docker start
│   ├── postgres/empty/      use instead for a clean database
│   ├── a2c/                 A2C OpenAPI spec read by the demo catalogue loader
│   └── farmer-registry/     Farmer Registry Postman collection (source of its gateway routes)
├── docs/
│   └── APISIX_INTEGRATION.md  apps, API products, keys and every APISIX Admin API call
├── .github/workflows/ci.yml backend lint + tests, UI typecheck/lint/build, image builds
├── docker-compose.yml       postgres + api + web (the APISIX gateway is external)
├── .env.example             settings for docker compose
└── DEPLOYMENT.md            Docker deployment guide
```

How apps, API products and keys reach the APISIX gateway (and how to add an endpoint):
[docs/APISIX_INTEGRATION.md](docs/APISIX_INTEGRATION.md).

## Quick start (Docker)

```bash
cp .env.example .env    # set DB_PASSWORD, JWT keys, GATEWAY_UAT_URL, public URLs
docker compose up -d --build
```

Web: <http://localhost:3005> · API: <http://localhost:8010/oan> (health `/oan/health`).
Full guide, settings and troubleshooting: **[DEPLOYMENT.md](DEPLOYMENT.md)**.

## Deployment (DevOps checklist)

What a deployment of this release needs, per environment (dev, staging, production). Every
setting is a variable in `.env` next to `docker-compose.yml`;
[`.env.example`](.env.example) lists them all with local values. `.env` is git-ignored; never
commit secrets. On Kubernetes use the Helm chart `oan-sandbox` in
[oan-helm](https://github.com/Centre-for-Open-Societal-Systems/oan-helm/tree/main/charts/oan-sandbox)
(dev: `environments/dev/values/sandbox.yaml`; steps and Secret keys in
`examples/dev/sandbox.yaml`); the partner routes for the gateway are the chart
[`deploy/apisix-partner-gateway/k8s`](deploy/apisix-partner-gateway/README.md) in this repository.

### Before you start

| Item | Detail |
|---|---|
| Host | Docker Engine 24+ with Compose v2. Nothing else on the host. |
| Images | Two images, built from this repo (CI builds them on every push but does not publish them). `api`: `docker build -f docker/sandbox-api/Dockerfile -t <registry>/oan-sandbox-api:<tag> .` (listens on `8000`). `web`: `docker build -t <registry>/oan-sandbox-web:<tag> --build-arg NEXT_PUBLIC_API_BASE_URL=<public API URL> ui` (listens on `3000`). Or `IMAGE_PREFIX=<registry>/oan-sandbox IMAGE_TAG=<tag> docker compose build api web`. |
| One `web` image per environment | The browser API URL (`PUBLIC_API_URL` / `NEXT_PUBLIC_API_BASE_URL`) is built into the `web` image. Build and tag a `web` image per environment; the `api` image is the same everywhere. |
| PostgreSQL | Included in the stack (`postgres:18-alpine`, database `sandbox_db_oan`, volume `oan_pgdata`). For a managed database, remove the `postgres` service and point `DB_HOST` / `DB_PORT` at it (PostgreSQL 18, to match the snapshot). |
| API gateway (APISIX) | **Not part of this stack.** The environment's existing Apache APISIX must be deployed with the A2C routes and plugins and be reachable from the `api` container. Its proxy URL is `GATEWAY_UAT_URL`; the stack refuses to start without it. Plugins: `jwt-auth` with `key_claim_name: iss` (A2C tokens are RS256, identified by `iss` = `oan_a2c_identity_gateway`; with the default `key` claim every token is `401`), `key-auth` on the `apikey` header, `consumer-restriction` (consumer groups), `ip-restriction`, `limit-count`. Route paths must match the catalogue end-point paths. The sandbox needs no Redis or etcd of its own (only the gateway uses them). |
| Public host names | One for the web app (e.g. `https://sandbox.<domain>`) and one for the API (e.g. `https://api.<domain>/oan`, or the same host under `/oan`), with TLS on a reverse proxy or load balancer. |
| SMTP | An SMTP account for sign-up codes, password-reset links, invitations and support ticket replies. Without it, codes and links only appear in the API log; admin invitation links are also shown in the console to copy (see *After deploying*). |
| Database start mode | **Snapshot** (default): the first start loads `deployment/postgres/initdb` (catalogue, masters, CMS, development accounts). **Clean**: `POSTGRES_INITDB_DIR=./deployment/postgres/empty` + `SEED_ADMIN_PASSWORD` (schema, admin, masters, CMS only). Use clean for production. Either applies only to an **empty** volume. |

### Volumes

| Volume | Mounted at | What | Back up |
|---|---|---|---|
| `oan_pgdata` | `/var/lib/postgresql` (postgres) | Database | Yes (daily `pg_dump`, see DEPLOYMENT.md §6) |
| `oan_uploads` | `/app/uploads` (api) | Participant ID proofs, certificates, product icons and documents | Yes |
| `oan_api_logs` | `/app/logs` (api) | API log files | Ship to the log store |
| `./deployment/a2c` | `/a2c` (api, read-only) | A2C OpenAPI file, read only by `LOAD_DEMO_CATALOGUE` | No (in git) |
| `./deployment/farmer-registry` | `/farmer-registry` (api, read-only) | Farmer Registry Postman collection, read only by `LOAD_DEMO_CATALOGUE` | No (in git) |
| `POSTGRES_INITDB_DIR` | `/docker-entrypoint-initdb.d` (postgres, read-only) | First-start snapshot or empty folder | No (in git) |

### Environment variables

**Required** (the stack does not start without them):

| Variable | Example | Notes |
|---|---|---|
| `DB_PASSWORD` | *(Secret)* | PostgreSQL password. |
| `JWT_ACCESS_TOKEN_KEY`, `JWT_REFRESH_TOKEN_KEY` | *(Secret)* | Two different long random values: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Changing them logs everyone out. |
| `GATEWAY_UAT_URL` | `https://apisix-dev.<domain>` | Proxy URL of the environment's existing APISIX (not the Admin API). Try-it calls for gateway products (A2C) go here. |

**Per environment** (defaults are for a laptop):

| Variable | Example | Notes |
|---|---|---|
| `PUBLIC_API_URL` | `https://api.<domain>/oan` | API URL users' **browsers** call. Build-time: rebuild `web` after changing it. |
| `ALLOWED_ORIGINS` | `https://sandbox.<domain>` | CORS; the public web URL(s), comma-separated. |
| `PORTAL_URL` | `https://sandbox.<domain>` | Web URL used in email links. |
| `API_INTERNAL_URL` | `http://api:8000/oan` | URL the `web` server uses to reach the API inside the network (public pages). Run time. |
| `APP_ENV` | `sandbox` / `uat` / `production` | `production` also turns off the fixed sign-up code below. |
| `MAIL_ENABLED`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TLS` | `true`, …, *(Secret)* | Turn mail on for any shared server. |
| `DEV_FIXED_OTP` | empty | Developer machine only: with `APP_ENV=local` and mail off, a participant password reset accepts this code. Ignored on every other environment and never valid for administrators (without mail, set an admin password with `backend/scripts/set_admin_password.py`). |
| `IMAGE_PREFIX`, `IMAGE_TAG` | `<registry>/oan-sandbox`, `1.0.0` | Images to pull/run (`<prefix>-api`, `<prefix>-web`). |

**Clean-database mode only** (first start on an empty volume):

| Variable | Example | Notes |
|---|---|---|
| `POSTGRES_INITDB_DIR` | `./deployment/postgres/empty` | Default `./deployment/postgres/initdb` loads the development snapshot. |
| `SEED_ADMIN_EMAIL`, `SEED_ADMIN_PASSWORD` | `admin@<domain>`, *(Secret)* | Master administrator. Seeding is idempotent and runs on every start while the password is set; existing rows are kept. |
| `LOAD_DEMO_CATALOGUE` | `true` / `false` | Adds the A2C products and **Farmer Registry - Staff API** (flagged for the gateway) and the OpenG2P demo product. Re-runnable. |

**Optional** (defaults are fine to start):

| Variable | Default | Notes |
|---|---|---|
| `GATEWAY_ENABLED` | `true` | `false`: no try-it call reaches the gateway (they fail, or answer from samples with `SANDBOX_MOCK_RESPONSES=true`). |
| `SANDBOX_MOCK_RESPONSES` | `false` | `true` answers try-it calls for endpoints with no gateway route from their stored samples. Off: everything goes through APISIX. |
| `GATEWAY_PROD_URL` | empty | Production gateway when it exists. |
| `GATEWAY_PROD_ADMIN_URL`, `GATEWAY_PROD_ADMIN_TOKEN` | empty | Production's own APISIX Admin API (viewer key in oauth mode). Production apps' route ids are read from it (apikey / keycloak modes: their consumers are written there); "Pull from gateway" gets a UAT / Production choice. Empty = production apps use `GATEWAY_ADMIN_URL`. |
| `GATEWAY_UAT_PUBLIC_URL`, `GATEWAY_PROD_PUBLIC_URL` | empty (= the URL above) | The gateway as partners reach it from Postman / their code; shown in code samples, the try-it URL and API history. Set it when the API reaches the gateway on an internal address (cluster service, `host.docker.internal`). |
| `GATEWAY_SYNC_ENABLED` | `false` | `true` shows **Pull from gateway** in the console (API Catalogue): reads every route from the gateway's Admin API and adds or updates catalogue end-points. |
| `GATEWAY_TYPE` | `apisix` | `apisix` or `kong`: which Admin API to read. |
| `GATEWAY_ADMIN_URL` | empty | Admin API reachable from the `api` container, e.g. `http://apisix-admin.<ns>:9180` (Kong: `:8001`). Required for the pull. |
| `GATEWAY_ADMIN_TOKEN` | *(Secret)* | APISIX admin key (sent as `X-API-KEY`) or Kong admin token (`Kong-Admin-Token`); empty if the Admin API has no auth. A read-only (viewer) key is enough for the pull; app sync needs a key that can write consumers. |
| `GATEWAY_PARTNER_AUTH` | `apikey` | What the gateway checks. `apikey`: the app's API key. `keycloak`: the app's API key **and** the participant's Keycloak access token in `GATEWAY_PARTNER_TOKEN_HEADER` (`X-Partner-Token`; APISIX `openid-connect`: JWKS signature, `iss`, `exp`, `azp`, the environment role in `oan_environments`), and the app must belong to the token's participant (consumer label `participant_uid`, written by app sync). Try-it as an app sends its key plus the signed-in participant's own token; code samples show both headers. Needs `PARTICIPANT_AUTH_PROVIDER=keycloak` and a gateway built for it (local: `PARTNER_AUTH=keycloak` in `../apisix-gateway`). |
| `GATEWAY_PARTNER_AUTH=oauth` | | OAuth 2.0 client credentials (dev). Every active app key is also a Keycloak client (client_id = API key, client_secret = API secret, `client_credentials` only); its token carries `participant_uid`, `oan_app`, `oan_environments`, `oan_routes`. Partners send only the token in `X-Partner-Token`; the try-it page has **Get token**. Needs `KEYCLOAK_PROVISIONING_ENABLED=true`, `GATEWAY_APP_SYNC_ENABLED=true` (the API refuses to start otherwise) and gateway routes built for it (local `PARTNER_AUTH=oauth` in `../apisix-gateway`; Kubernetes: `deploy/apisix-partner-gateway/k8s`). See DEPLOYMENT.md §7. |
| `GATEWAY_APP_SYNC_ENABLED` | `false` | `true` writes every participant app to APISIX as a consumer (API key + secret, whitelist of the routes its API products grant). Needs `GATEWAY_TYPE=apisix` and `GATEWAY_ADMIN_URL`. |
| `APP_CREDENTIAL_ENCRYPTION_KEY` | *(Secret)* | Fernet key encrypting the stored app keys/secrets. **Required in production**; never change it once keys are issued. Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `GATEWAY_APP_KEY_HEADER`, `MAX_APPS_PER_PARTICIPANT`, `MAX_ACTIVE_CREDENTIALS_PER_APP` | `apikey`, `10`, `2` | Key header the gateway's `key-auth` reads; app and key limits. |
| `SUPPORT_NOTIFY_EMAIL`, `SUPPORT_AUTO_CLOSE_DAYS`, `SUPPORT_MAX_MESSAGES_PER_TICKET` | empty, `0`, `100` | Support tickets are conversations: mailbox told when a participant writes, days after which an answered ticket without a reply closes (0 = never), and the most messages per ticket. |
| `SUPPORT_SLA_HOURS`, `AUDIT_LOG_RETENTION_DAYS` | `72`, `0` | Hours before an unanswered support query shows as overdue (0 = no SLA); days after which audit entries are deleted (0 = keep forever). |
| `APP_KEY_LIFETIME_DAYS`, `APP_KEY_ROTATION_GRACE_DAYS`, `APP_KEY_EXPIRY_WARN_DAYS`, `APP_KEY_MAINTENANCE_MINUTES` | `0`, `7`, `14`, `60` | App key lifecycle: lifetime (0 = never expires), how long a rotated key keeps working, days of warning before expiry, how often the API expires keys and sends warnings (0 = never). |
| `API_DEBUG` | `false` | `true` exposes Swagger at `/docs`. Keep `false` on shared servers. |
| `DB_USER`, `DB_NAME` | `postgres`, `sandbox_db_oan` | |
| `API_HOST_PORT`, `WEB_HOST_PORT` | `8010`, `3005` | Host ports the reverse proxy targets. |
| `POSTGRES_HOST_PORT`, `POSTGRES_BIND` | `5433`, `127.0.0.1` | Keep the database on loopback. |
| `DEFAULT_COUNTRY_CODE`, `SITE_NAME` | `ET`, `EOAN` | `SITE_NAME` is build-time for `web`. |
| `LOG_LEVEL` | `INFO` | |

**OpenG2P Consent Manager partner portal** (optional). An approved participant also signs in
to the Consent Manager (CM) partner portal with its sandbox email and password, and is a
partner in OpenG2P Partner Management (PM), where the CM reads what the partner may do.
Needs Keycloak provisioning (`KEYCLOAK_PROVISIONING_ENABLED=true`, `KEYCLOAK_URL`,
`KEYCLOAK_ADMIN_CLIENT_*`):

| Variable | Example | Notes |
|---|---|---|
| `KEYCLOAK_PROD_URL`, `KEYCLOAK_PROD_PUBLIC_URL`, `KEYCLOAK_PROD_REALM`, `KEYCLOAK_PROD_ADMIN_CLIENT_ID`, `KEYCLOAK_PROD_ADMIN_CLIENT_SECRET` *(Secret)*, `KEYCLOAK_PROD_JWKS_URL` | empty | Production's own Keycloak (oauth): production apps' clients and their **Get token**. Empty realm / client id = the main ones; `KEYCLOAK_PROD_URL` needs the secret. Empty `KEYCLOAK_PROD_URL` = production apps use the main Keycloak. Participant users and the portal sign-in stay on the main Keycloak. |
| `KEYCLOAK_REALM` | `partner` | The CM's partner realm (made by the CM chart with `partnerPortal.enabled`), instead of `oan-partners`. |
| `KEYCLOAK_PORTAL_CLIENT_ID` | `consent-partner-portal` | The CM portal client. Approval gives the user its role `KEYCLOAK_PORTAL_ROLE` (default `PARTNER_OPERATOR`) and the attribute `partner_id` = `PARTNER_ID_PREFIX` + participant id (`oan-p-42`). Empty: portal off. **Never change `PARTNER_ID_PREFIX` once partners exist.** |
| `PM_PROVISIONING_ENABLED` | `true` | Approval onboards **and approves** the participant as PM partner `PARTNER_OAN_P_42`; reject, disable and delete disable it, a new approval enables it. |
| `PM_STAFF_API_URL` | `http://commons-services-pm-staff-portal-api` | PM staff-portal API, reachable from `api`. |
| `PM_TOKEN_URL`, `PM_CLIENT_ID`, `PM_CLIENT_SECRET` | `https://<keycloak>/realms/staff/protocol/openid-connect/token`, `oan-sandbox-pm`, *(Secret)* | Service-account client in the realm PM's staff API trusts, holding PM's admin role (client role `partner_manager` of `partner-management`). Create it in Keycloak once. |
| `PM_PARTNER_JWKS_BASE_URL` | `https://api.<domain>/oan` | This API as PM reaches it. PM reads a partner's keys from `<this>/partners/<partner id>/jwks.json` (the public key the participant gave; empty until then). |
| `PM_DEFAULT_POLICIES` | `[]` | JSON list of PM policies given at onboarding, e.g. `[{"data_controller":"farmer_registry","allowed_data_scopes":["farmer_personal_details"]}]`. `[]`: PM staff add them; the portal shows no access until then. |

Set up once, after the CM is installed: `KC_ADMIN_PASSWORD=… python
backend/scripts/keycloak/setup_partner_realm.py --url https://<keycloak> --realm partner
--portal-client-id consent-partner-portal --env-file .env`. It adds the sandbox's client,
attribute and service account to the CM's realm and checks that the CM's portal client, its
role and the `partner_id` attribute and mapper are there (exit 1 if not). A participant can
sign in to the portal only after its first sandbox sign-in following approval (the sandbox
hands Keycloak the password then); the admin console shows the portal and PM state under the
participant's Keycloak user, with **Sync** to retry.

**Participant sign-in with Keycloak** (optional). With `PARTICIPANT_AUTH_PROVIDER=keycloak`
Keycloak checks the participant's password and issues the tokens; the portal (its sign-in
form, pages and headers) stays as it is. Needs Keycloak provisioning on. The API:

* signs in with the confidential client `KEYCLOAK_LOGIN_CLIENT_ID` (`oan-sandbox-portal`,
  direct grant, secret `KEYCLOAK_LOGIN_CLIENT_SECRET`; the browser never sees the secret) and
  hands the portal Keycloak's access token (`x-access-token`) and refresh token, plus its own
  session handle (`x-auth-key`);
* verifies every access token itself: signature from the realm's JWKS with **RS256 pinned**
  (`alg: none` or HMAC tokens never pass), `iss` = `KEYCLOAK_ISSUER`, `exp` / `nbf` / `iat`
  (`KEYCLOAK_TOKEN_LEEWAY_SECONDS`), `typ` = `Bearer`, `azp` = the login client (tokens of other
  clients, e.g. the CM partner portal, are refused), `jti`, and the token's Keycloak session
  (`sid`) must be the one the sandbox session was opened with;
* refreshes with Keycloak's refresh grant (rotated refresh tokens are kept by the portal, which
  refreshes by itself on a `401`) and ends the Keycloak session at sign-out; rejecting,
  disabling or deleting a participant ends all its Keycloak sessions.

The password is Keycloak's: change or reset it there (or in the portal, which hands it to
Keycloak). A participant approved before Keycloak held its password is let in once by the
sandbox's own check, which hands Keycloak the password; Keycloak checks every sign-in after
that. A participant not approved yet has no Keycloak user and gets the same messages as before.
Set up the client with `setup_partner_realm.py` (it writes `KEYCLOAK_LOGIN_CLIENT_SECRET` and
reports whether the realm has brute-force detection and refresh-token rotation on; turn both on).
`KEYCLOAK_ISSUER` must be what Keycloak writes into tokens: its public hostname (`KC_HOSTNAME`),
e.g. `https://auth.<domain>/realms/partner`; empty = `KEYCLOAK_PUBLIC_URL`/realms/`KEYCLOAK_REALM`.

*Switch it on* (a running deployment with Keycloak provisioning already on):

1. Keep `KEYCLOAK_REALM` where the participants' Keycloak users already are. Moving to another
   realm (e.g. the CM's `partner`) leaves the existing users behind; that is a separate migration.
2. `KC_ADMIN_PASSWORD=… python backend/scripts/keycloak/setup_partner_realm.py --url <keycloak>
   --realm <KEYCLOAK_REALM> --env-file .env`: creates `oan-sandbox-portal` and writes
   `KEYCLOAK_LOGIN_CLIENT_SECRET` (and the provisioner's secret) into `.env`, never on screen.
3. In Keycloak (realm settings): **Security defenses → Brute force detection** on, **Tokens →
   Revoke refresh token** on (refresh-token rotation). The script reports either if it is off.
4. In `.env`: `PARTICIPANT_AUTH_PROVIDER=keycloak`. `KEYCLOAK_URL` is Keycloak as the `api`
   container reaches it (e.g. `http://host.docker.internal:8080`), `KEYCLOAK_PUBLIC_URL` (or
   `KEYCLOAK_ISSUER`) the hostname written into tokens (e.g. `http://localhost:8080`).
5. `docker compose up -d --build api web` (migration `d5e9f3a1b2c7` adds
   `participant_token.keycloak_sid`). Sessions opened before the switch end; participants sign
   in again.

*Check it works:*

* API log after a sign-in: `POST …/realms/<realm>/protocol/openid-connect/token "HTTP/1.1 200 OK"`
  followed by `POST /oan/participant/auth/login -> 200`
  (`docker compose logs api | grep -E "openid-connect/token|auth/login|auth/refresh"`).
* The access token (browser local storage, participant session `access_token`), decoded: header
  `alg: RS256` with a `kid`; payload `iss` = the realm, `azp: oan-sandbox-portal`,
  `typ: Bearer`, `sid`, `participant_uid`, `exp - iat` = the realm's access-token lifespan. The
  sandbox's own tokens have `HS256`, `role: participant`, `typ: access` and no `iss` / `azp`.
* The signature proves it: Keycloak → realm → **Realm settings → Keys**, the `RS256` key's
  *Kid* equals the token's `kid`, and its **Public key** (wrapped in `-----BEGIN PUBLIC KEY-----`
  / `-----END PUBLIC KEY-----`) verifies the token (e.g. "Signature Verified" in a JWT
  debugger; the same key is at `<realm>/protocol/openid-connect/certs`). Offline, with the
  API's own checks: `docker exec -i oan-sandbox-api-1 python -c "import sys,json; from
  app.integrations.keycloak_oidc import verify_access_token as v; print(json.dumps(v(sys.stdin.read().strip()), indent=1))"`
  with the token on stdin. A token is a live credential until it expires: do not share it or
  paste a production one into an online tool.
* Refresh: stay signed in past the access-token lifespan (5 minutes by default) and open a
  page. It opens without a new sign-in; the log shows `POST /oan/participant/auth/refresh -> 200`
  and a Keycloak `openid-connect/token` call, and the session's `refresh_token` in local
  storage changes (rotation). A refresh token that was already used is refused (`401`).
* Sign-out: the log shows `DELETE …/admin/realms/<realm>/sessions/<sid>`; the user's
  **Sessions** tab in Keycloak no longer lists it.
* A password changed in Keycloak (Users → the participant → Credentials) is the one the portal
  sign-in accepts from then on.

*Switch back:* `PARTICIPANT_AUTH_PROVIDER=local` in `.env`, then `docker compose up -d api`.
Participants sign in again with the sandbox's own check (passwords changed only in Keycloak are
not known to it).

*When it fails:*

| Symptom | Cause |
|---|---|
| Every sign-in `502` "Sign-in is unavailable"; log: Keycloak refused the sandbox's login client | `KEYCLOAK_LOGIN_CLIENT_SECRET` wrong or the client missing / not confidential: rerun `setup_partner_realm.py` |
| `unauthorized_client: Client not allowed for direct access grants` (Keycloak) | **Direct access grants** off on `oan-sandbox-portal` (the script turns it on) |
| Sign-in `200`, then every page `401` | `iss` in the token is not `KEYCLOAK_ISSUER` (Keycloak's public hostname differs), or the `api` container cannot read the JWKS at `KEYCLOAK_URL` |
| "Your account needs an action before you can sign in" | The Keycloak user has a required action (e.g. *Update password*, *Verify email*): clear it or finish it |
| "No such email address or password." for the right password | Keycloak holds a different password (changed there), or brute-force detection locked the user (Keycloak → Users → the participant) |
| Signed out every 5 minutes | The `web` image predates the silent refresh: rebuild `web` |

### Reverse proxy

TLS terminates on the proxy: web host → `web` (`WEB_HOST_PORT`), API host or `/oan` path →
`api` (`API_HOST_PORT`). Forward `X-Forwarded-*` headers (the API runs with
`--proxy-headers`). Allow uploads of at least 25 MB on the API route (`MAX_UPLOAD_MB`).
Do not expose PostgreSQL.

### Deploy

```bash
cp .env.example .env        # fill in the variables above
docker compose pull         # or: docker compose build api web
docker compose up -d
docker compose ps           # postgres, api and web all "(healthy)"
```

The `api` container waits for the database, runs `alembic upgrade head`, seeds if
`SEED_ADMIN_PASSWORD` is set, loads the demo catalogue if asked, then starts. No manual
migration step.

### After deploying

1. `GET https://api.<domain>/oan/health` answers `200` with `"database": "up"` and the
   expected `env`.
2. The web app opens on its public URL; the API catalogue lists the products (snapshot: 14
   products; clean + demo catalogue: A2C + OpenG2P).
3. Log in to the admin console. **Snapshot mode: change the passwords of the development
   accounts** (`admin@openagrinet.org`, `participant@openagrinet.org`) at once. Clean mode:
   remove `SEED_ADMIN_PASSWORD` from `.env` after the first start.
4. Add a console user under **User Management → Admin Users** without a password. The
   **Invitation link** dialog shows the set-password link (`<PORTAL_URL>/admin/set-password?token=…`)
   with **Copy**; with mail on it is emailed too. Open it (or send it to the user) to set the
   password. The link works once, for 24 hours. For a user who has not set a password yet, the
   row menu's **New invitation link** makes a new one (the old one stops working); users who
   have a password use the password reset instead. The link sets the account's password, so
   send it only to that user.
5. Sign up a test participant: the code arrives by email (mail on). Approve it under
   **UAT Approval Pending** in the console.
6. Try-it for a gateway product (A2C) reaches APISIX: the API log shows the call to
   `GATEWAY_UAT_URL` and APISIX answers (a `401` without credentials still proves the
   route; a valid A2C token gives `200`, a `401` with one means `jwt-auth` is not keyed on
   `iss`). A `404` means no matching route; a connection error means the `api` container
   cannot reach APISIX.
7. Password reset and invitation links point at `PORTAL_URL`.
8. Schedule backups of `oan_pgdata` and `oan_uploads`; ship `oan_api_logs` to the log store.

### Upgrades

Pull (or build) the new images with the new `IMAGE_TAG`, then `docker compose up -d`; the
`api` container applies new migrations on start. Rebuild `web` whenever `PUBLIC_API_URL` or
`SITE_NAME` changes. `docker compose down -v` **deletes all data**; never run it on a shared
server.

## Local development

- **Backend** — see [backend/README.md](backend/README.md):
  `python -m venv venv`, `pip install -r requirements.txt`, copy `.env.example` to `.env`,
  `python -m alembic upgrade head`, `uvicorn app.main:app --reload --port 8010`.
- **UI** — see [ui/README.md](ui/README.md):
  `npm ci`, copy `.env.example` to `.env`, `npm run dev -- -p 3005`.

Checks (the same as CI):

| Part | Command |
| --- | --- |
| Backend lint | `cd backend && ruff check app tests` |
| Backend tests | `cd backend && pytest` (CI: `pytest --cov=app --cov-report=xml:coverage.xml`) |
| UI unit tests | `cd ui && npm test` (Vitest + Testing Library; `npm run test:coverage` writes `coverage/lcov.info`) |
| UI | `cd ui && npm run typecheck && npm run lint && npm run build` |
| SonarQube | both coverage reports, then `sonar-scanner -Dsonar.host.url=<server> -Dsonar.token=<token>` from the repository root (`sonar-project.properties`; gate *Sonar way*). Next.js route files (`ui/src/app/**`) are left out of coverage, still analysed. |

## Apps, environments and keys

- Participants create **UAT apps**. Once their account is approved for production, **Move to production**
  on an active UAT app makes a **production app**: same name and API products, its own description,
  IP whitelist, and its **own API key + secret** after an administrator
  approves it (production apps and their product requests always wait for an administrator).
- A key works only in its app's environment: tokens name only that environment (`oan_environments`),
  try-it refuses another environment's app, code samples show only a key of that environment.
- Portal: My Apps has a **UAT / Production** toggle; the choice is remembered in the browser and the try-it
  page starts in it. Console Apps & Keys filters by environment.
- Production request (account): the partner's **signing key** - X.509 certificate (PEM / DER) or its public
  key, checked (no private key, valid dates, RSA ≥ 2048 / EC P-256 / P-384 / Ed25519, both must match).
  Approving production stores it as the partner's key (`/oan/partners/{id}/jwks.json`). Admins preview the
  uploaded documents in a dialog.
- Details and production settings: [DEPLOYMENT.md](DEPLOYMENT.md), section *UAT and production apps*.

## Branches and pull requests

| Branch | Purpose |
| --- | --- |
| `develop` | Integration branch; all work is merged here first |
| `staging` | Release candidate deployed to staging |
| `main` | Released code |

Work happens on a fork. Create a branch from `develop` (or work on the fork's `develop`), push it
to the fork and open a pull request into `Centre-for-Open-Societal-Systems/sandbox-platform`
**`develop`**. `develop` → `staging` → `main` is promoted by pull request.

```bash
git remote add upstream https://github.com/Centre-for-Open-Societal-Systems/sandbox-platform.git
git fetch upstream
git checkout -b feature/<name> upstream/develop
```
