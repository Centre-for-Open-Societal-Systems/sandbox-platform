# Partner gateway: Helm owns APISIX, access by OAuth scopes

**Status:** Implemented 2026-11-18 with the recommended options (D1 one scope per API, D2
scope list from the chart's `gateway-scopes.json`, D3 sandbox creates client scopes, D4 pull
kept for the catalogue, D5 oan-helm default `oauth`, D6 whole API per scope with a console
warning), plus token audience, upstream mTLS (bypass prevention) and optional
`private_key_jwt` for production clients. Not committed. See `DEPLOYMENT.md` (OAuth app
tokens) and `deploy/apisix-partner-gateway/README.md`.
**Date:** 2026-11-18

**Goal:** every change to APISIX (routes, plugins, upstreams) is made **only through Helm**.
The sandbox never writes to APISIX and does not need its Admin API to give an app access.

**Short answer:** replace the route ids in the app token (`oan_routes`) with standard
**OAuth 2.0 scopes**. Helm says which scope each route needs; the sandbox decides which
scopes an app gets (its approved API products); Keycloak puts them in the token; APISIX
compares the two. Route ids, the Admin API and "Pull from gateway" leave the access path.

## Contents

1. [What happens today](#1-what-happens-today)
2. [The standard approach](#2-the-standard-approach)
3. [Proposed design](#3-proposed-design)
4. [What changes where](#4-what-changes-where)
5. [Day-to-day: who does what](#5-day-to-day-who-does-what)
6. [Moving existing apps](#6-moving-existing-apps)
7. [Decisions needed](#7-decisions-needed)
8. [Risks and limits](#8-risks-and-limits)

---

## 1. What happens today

With `GATEWAY_PARTNER_AUTH=oauth` (dev) the sandbox already writes **nothing** to APISIX.
The routes and plugins come from the `oan-partner-gateway` chart. One link is left:

```
Helm route ──(APISIX makes an internal route id)──▶ Admin API
                                                      │  sandbox reads it (pull)
Sandbox: product endpoints (method+path) ↔ route ids ─┘
   └──▶ Keycloak client claim  oan_routes = ["3f2a…", "9c1d…"]
         └──▶ token ──▶ APISIX: "is my route id in oan_routes?"
```

- The sandbox must read the Admin API to learn the route ids (a viewer key).
- Ids belong to APISIX. When Helm renames a route, its id changes and apps lose it until
  the sandbox pulls again (since 18 Nov: daily auto-pull + automatic re-sync).
- A new route in an existing API needs a pull plus an administrator in the sandbox
  before any app can call it.
- The `oan-sandbox` chart default is still `partnerAuth: apikey`, which **writes**
  consumers to APISIX.

## 2. The standard approach

Developer portals in front of an OAuth gateway (Apigee, Kong Konnect, Azure APIM, AWS API
Gateway with Cognito, WSO2) split the work the same way:

| Who | Owns | Example |
|---|---|---|
| **Gateway config (GitOps / Helm)** | Routes, upstreams, plugins, and **which scope each route requires** | `POST /consent-manager-partner/validate` needs `consent-manager-partner` |
| **Identity provider (Keycloak)** | Apps (clients), their secrets, and **which scopes each app may get** | client `abc123` may get `consent-manager-partner` |
| **Developer portal (sandbox)** | Catalogue, docs, sign-up, approval: it **decides** the scopes and writes them to Keycloak | product "Consent Manager – Partner" = scope `consent-manager-partner` |
| **Gateway at run time** | Checks the token's signature and that it holds the route's scope | `scope` claim contains `consent-manager-partner`, otherwise 403 |

The shared contract is a **scope name**, written in both Helm and the sandbox. Gateway
internals (route ids, consumers) never reach the portal. This is OAuth 2.0 (RFC 6749 §3.3
scopes; RFC 9068 JWT access tokens carry them in `scope`).

## 3. Proposed design

### 3.1 Scope names

One scope per partner API. If an API needs separate access for reading and writing, it
gets two scopes:

```
consent-manager-portal            Consent Manager partner portal API
consent-manager-partner           Consent Manager partner API
partner-management-keys           Partner Management key fetch API
aggregation-layer                 Aggregation Layer (DCI search)
# optional split (D1):
consent-manager-partner:read      GET routes
consent-manager-partner:write     POST/PUT/PATCH/DELETE routes
```

The names are kept short and stable. They never change once partners hold them.

### 3.2 Helm (`oan-partner-gateway`)

- `values.yaml`: each API gets `scope` (default = the API key name). Optionally a route
  can override it with `routes.<name>.scope`.
- The generator writes the required scope into the shared plugin config of each API. A
  route that overrides it gets its own value.
- The existing `serverless-post-function` check changes from route ids to scopes:

  ```lua
  -- before: granted when ctx.route_id is in claims.oan_routes
  -- after:  granted when the route's required scope is in the token's scope claim
  local wanted = "consent-manager-partner"        -- written by Helm
  local granted = false
  for s in string.gmatch(claims.scope or "", "%S+") do
    if s == wanted then granted = true break end
  end
  if not granted then return 403, {message = "This app has no access to this API"} end
  ```

  IP whitelist (`oan_ips`), limits (`oan_limit_*`), `X-OAN-App` and the call log stay as
  they are.
- The claim schema requires `scope` instead of `oan_routes`. During the move both are
  accepted (section 6).

### 3.3 Keycloak

Each scope is a Keycloak **client scope** (type *Optional*) in the partner realm. Its name
is the scope name, and it has *Include in token scope* turned on. When the sandbox
approves a product, it attaches the product's scopes to the app's client as default
client scopes. Keycloak then writes them into the standard `scope` claim. No custom claim
is needed.

Where the client scopes come from (D3):
- (a) the sandbox creates a missing client scope when an administrator first uses it in
  a product; or
- (b) they are created once per realm by `setup_partner_realm.py`, and with each new API.

### 3.4 Sandbox

- **API product** gets a field **Gateway scopes** (list). The admin picks the scopes from a
  list (D2 decides where the list comes from).
- **App sync** (oauth mode) writes the union of the scopes of the app's approved products
  onto its Keycloak client. It writes no `oan_routes` and reads nothing from APISIX.
- **Catalogue / try-it / docs** do not change. Endpoints still describe the APIs. Each
  catalogue product can show the scope it needs ("Requires: consent-manager-partner").
- **Pull from gateway** stays, but **only for the catalogue** (new routes appear
  unpublished as documentation), or it is replaced by OpenAPI import. With D4 = off, the
  sandbox needs no Admin API key at all.
- `oan-sandbox` chart default becomes `partnerAuth: oauth`. The consumer-writing modes
  (`apikey`, `keycloak`) are kept only for the local test gateway, or removed (D5).

## 4. What changes where

| Repo | File / place | Change |
|---|---|---|
| sandbox-platform | `apisix-gateway/build_apisix_config.py` + `deploy/apisix-partner-gateway/generate_k8s_chart.py` | Scope per API / route; post-function checks `scope` (plus `oan_routes` during the move). The generator script moves into this repo; today it lives only on one machine |
| sandbox-platform | `deploy/apisix-partner-gateway/k8s/values.yaml` | `scope` per API, optional per-route override |
| sandbox-platform | backend: `ApiProduct.gateway_scopes`, migration, `app_gateway_service` (scopes → Keycloak client scopes), `keycloak.py` (client scope helpers) | New |
| sandbox-platform | UI: API product form (scope picker), catalogue badge | New |
| sandbox-platform | `setup_partner_realm.py` | Client scopes per API (if D3 = b) |
| oan-helm | `charts/oan-sandbox/values.yaml` | `partnerAuth: oauth` default |
| oan-helm | `environments/*/values/oan-partner-gateway.yaml` | Nothing, unless a scope is renamed |

## 5. Day-to-day: who does what

| Change | Helm | Sandbox |
|---|---|---|
| Plugin, limit, upstream, timeout | `helm upgrade` | nothing |
| **New route** in an existing API | add the route, `helm upgrade` | **nothing**. Apps holding the API's scope can call it at once (docs: optional pull or OpenAPI import) |
| Route renamed / path changed | `helm upgrade` | nothing |
| Route moved to a stricter scope (e.g. `:write`) | set `routes.<name>.scope` | nothing. Apps without that scope get 403 |
| **New API** | new API block with its `scope` | once: create a product with that scope (and the client scope, if D3 = b) |
| App approved / product added / IP changed | – | as today. Effective with the next token (≤ 5 min) |

## 6. Moving existing apps

1. **Helm release N:** the post-function grants a route when the token holds **either** the
   route's scope **or** its id in `oan_routes`. Nothing breaks.
2. **Sandbox:** migration fills `gateway_scopes` on every API product from the APIs its
   endpoints belong to. App sync writes **both** `scope` and `oan_routes` for one release.
3. Check API history / gateway logs: no call is granted only by `oan_routes`.
4. **Helm release N+1:** the `oan_routes` check is removed. **Sandbox:** `oan_routes`, route
   resolution and the route snapshot are removed from the access path.

## 7. Decisions needed

| # | Question | Options | Recommended |
|---|---|---|---|
| D1 | How fine-grained are scopes? | (a) one per API; (b) per API with `:read` / `:write`; (c) any per-route scope chosen in Helm | **(a) now**. Helm can add (b)/(c) later without sandbox code changes |
| D2 | Where does the sandbox get the list of scope names for the product form? | (a) an admin master list in the console ("Gateway scopes"); (b) a setting `GATEWAY_SCOPES` from Helm values; (c) read from the pulled routes | **(b)**: one list in Helm values, given to both charts, so names cannot drift |
| D3 | Who creates Keycloak client scopes? | (a) the sandbox, on first use; (b) `setup_partner_realm.py` / realm config | **(a)**. The sandbox already manages clients in that realm |
| D4 | Keep "Pull from gateway"? | (a) keep, catalogue only (daily auto-pull); (b) remove, OpenAPI import only | **(a)** for now, as documentation help |
| D5 | Consumer-writing modes `apikey` / `keycloak` | (a) keep for the local test gateway only; (b) remove | **(a)**, and the `oan-sandbox` chart default becomes `oauth` |
| D6 | One product = whole API? | Products that today hold a subset of an API's endpoints keep that subset only as documentation; access becomes the whole API (or its `:read`/`:write` half) | Confirm that no partner needs part of an API |

## 8. Risks and limits

- **Coarser access:** a scope opens every route that requires it. Split APIs or scopes
  (D1) where a partner must see only part of an API.
- **Name drift:** a scope typed differently in Helm and in a product gives 403. D2 (b) and
  a console warning for unknown scopes reduce this.
- **Token size:** many scopes make tokens longer. This is fine for tens of scopes.
- **Five-minute tokens:** a removed product still works until the token expires. This is
  the same as today.
- **Keycloak is on the access path:** this is the same as today. APISIX caches the realm
  keys (JWKS) and does not call Keycloak per request.
