# Partner gateway routes (APISIX Ingress Controller)

The OAN partner APIs that apps created in the sandbox call, as APISIX Ingress Controller
resources in the Helm chart `oan-partner-gateway` (`k8s/`).

**Helm owns APISIX.** Every route, upstream and plugin comes from [`apis.yaml`](apis.yaml)
(API-as-code), turned into the chart by `generate_k8s_chart.py`, reviewed in a PR and
installed with `helm upgrade`. The sandbox never writes to the gateway. An app's access is
an **OAuth scope** in its token: Helm says which scope a route needs, the sandbox decides
which scopes an app gets (its approved API products), Keycloak puts them into the token.

| Value | API | Gateway path | Scope | Operations |
| --- | --- | --- | --- | --- |
| `consentManager.portalApi` | Consent Manager partner portal API (`/consent/v1/partner-portal` of the console host) | `/consent-manager/...` | `oan:consent-manager-portal` | 16 |
| `consentManager.partnerApi` | Consent Manager partner API (validate, status, receipts, JWKS) | `/consent-manager-partner/...` | `oan:consent-manager-partner` | 5 |
| `partnerManagement.keysApi` | Partner Management key fetch API | `/partner-management-keys/...` | `oan:partner-management-keys` | 4 |
| `aggregationLayer` | Aggregation Layer (DCI search) | `/aggregation-layer/...` | `oan:aggregation-layer` | 1 |

Only what partners call. Staff use their own portals, so no staff API is in the chart: not
the registries' staff APIs, the Partner Management admin API or the Consent Manager's staff
routes.

Each API is switched on by `enabled` and has an `ApisixUpstream` (its public host), an
`ApisixPluginConfig` (the plugins every route shares, with the API's scope) and an
`ApisixRoute` (one rule per operation, pointing at the plugin config). The prefix is
removed before the call (plus `<api>.basePath`, if the host serves the API under a path).

## Add a route or an API

| Change | Edit | Sandbox |
| --- | --- | --- |
| New operation of an existing API | add `{method, path}` under its `operations` in `apis.yaml` | **nothing**: apps holding the API's scope can call it once the route is live. To document it, pull from the gateway or import the API's OpenAPI |
| Operation that needs its own scope (e.g. a write call) | add `scope:` to that operation | the new scope goes into an API product (`gateway-scopes.json` → `GATEWAY_SCOPES`) |
| New API | new entry in `apis.yaml` (`name`, `values`, `prefix`, `scope`, `operations`) and its block in `k8s/values.yaml` | once: an API product for its scope |
| Plugin, limit, timeout | `generate_k8s_chart.py` (plugin logic) or values | nothing |

Then:

```bash
python deploy/apisix-partner-gateway/generate_k8s_chart.py   # no arguments, deterministic
git diff deploy/apisix-partner-gateway                        # review: templates + gateway-scopes.json
helm upgrade --install oan-partner-gateway deploy/apisix-partner-gateway/k8s -n api6-gateway -f ...
```

Do not edit `k8s/templates/apisix-route.yaml`, `apisix-upstream.yaml`,
`apisix-pluginconfig.yaml`, `_shared-plugins.tpl` or `gateway-scopes.json` by hand
(`apisix-tls.yaml` and `_helpers.tpl` are hand-written). Scope names never change once
partners hold them: add a new scope instead.

`gateway-scopes.json` is the scope map for the sandbox (setting `GATEWAY_SCOPES`): `"/prefix"`
→ scope per API, and `"METHOD /path"` → scope for each operation with its own. The sandbox
matches the exact operation first, then the longest path prefix, so it knows the scope of
every catalogue end-point without reading the gateway.

An operation with its own scope does not point at the API's plugin config: its route
carries the plugins inline with that scope (APISIX merges a route's plugins with its plugin
config's, so the check is never split between the two).

## Security model

Every call carries the app's **OAuth access token** (`GATEWAY_PARTNER_AUTH=oauth` in the
sandbox): a Keycloak client-credentials token (client = the app key) in `X-Partner-Token`.

| # | Check (plugin) | Answer when it fails |
| --- | --- | --- |
| 1 | Client-sent `X-OAN-*`, `X-Userinfo`, `X-Access-Token` are removed, so a caller cannot pose as an app (`serverless-pre-function`) | – |
| 2 | A token is sent | `401` `Missing app token (X-Partner-Token)` |
| 3 | Signature from the realm's JWKS (RS256, no `none` / unsupported algorithms), `iss` = `keycloak.issuer`, `exp`, `typ` = Bearer (`openid-connect`) | `401` |
| 4 | `oan_environments` holds `environmentRole`: a UAT app never opens production | `401` |
| 5 | `aud` holds `keycloak.audience` (`oan-partner-gateway`): a token issued for another service of the realm is refused | `401` `Token not issued for this gateway` |
| 6 | The token's `scope` holds the route's scope (exact match of one space-separated value). With `legacyRouteIds`, the route id in `oan_routes` also grants it | `403` `This app has no access to this API` |
| 7 | The caller's address is in the app's IP whitelist (`oan_ips`, IPs or CIDRs), when it has one | `403` `This app does not accept calls from your IP address` |
| 8 | `limit-count`: the app's own limits a minute and a day (`oan_limit_minute`, `oan_limit_day`), and 120 a minute per app and route | `429` |
| 9 | mTLS to the upstream: APISIX presents `upstreamTls` (client certificate) | the upstream's edge refuses calls without it |

The upstream then gets `X-OAN-Partner-Id` (the token's `participant_uid`) and `X-OAN-App`
(set before checks 5–8, so a refused call is still logged against its app);
`X-Partner-Token` is removed. The caller's own `Authorization` (the partner's credential,
where the API asks for one) is passed through unchanged: the API still checks its partner.

**No way around the gateway.** The upstream hosts are public, so the gateway's checks hold
only if partners cannot call those hosts directly. Set `upstreamTls.secretName` (a client
certificate of a CA only the gateway holds) and make the upstream's edge (the reverse proxy
or ingress in front of each API) require that certificate on the partner paths. The edge
configuration lives with the upstream (oan-helm), not in this chart. Until it is in place,
direct calls still reach the APIs, which then check only their own partner credential.

### What the token carries

The sandbox writes these on each app key's Keycloak client; the gateway reads them from the
token on every call (it fetches only the realm's keys, and caches them):

| Claim | From | The gateway |
| --- | --- | --- |
| `scope` | Keycloak client scopes = the scopes of the app's approved API products | refuses a route whose scope is missing (`403`) |
| `aud` | the sandbox's `GATEWAY_TOKEN_AUDIENCE` | refuses a token meant for something else (`401`) |
| `oan_app`, `participant_uid` | the app and its owner | names the app (`X-OAN-App`, `X-OAN-Partner-Id`) |
| `oan_environments` | the app's environment | refuses another environment's app (`401`) |
| `oan_ips` | the app's IP whitelist (empty = any address) | refuses another caller address (`403`) |
| `oan_limit_minute`, `oan_limit_day` | the most generous limits of the app's products, with `GATEWAY_RATE_LIMIT_ENABLED` (`0` = none) | counts the app's calls (`429`) |
| `oan_routes` | migration only (`legacyRouteIds`) | grants a route by id |

A change in the sandbox reaches the gateway with the next token: a token already issued
keeps its values until it expires (five minutes). The app's own limits count per API (all
routes of one API together), because APISIX keeps the counters under the plugin config; with
`inlineSharedPlugins`, or for an operation with its own scope, they count per route. The
caller address is the one APISIX sees: behind a proxy, only a trusted one may set it.

## Migration from route ids to scopes

1. Upgrade the sandbox: it writes `scope` (Keycloak client scopes) and `aud` on every app
   client, next to `oan_routes`, and re-syncs the apps.
2. Install this chart (0.3.0) with `legacyRouteIds: true`: a route is granted by scope or,
   for an app not re-synced yet, by its id.
3. When every app is re-synced (tokens live five minutes), set `legacyRouteIds: false`.
   From then on route ids are not used and the sandbox needs nothing from the Admin API to
   give access.

## Where each plugin lives

| Place | Plugins | Why there |
| --- | --- | --- |
| Global rule (`oan-apisix-gateway`, `gatewayProxy.plugins`) | `request-id`, `prometheus` | every request of the gateway |
| Plugin metadata (`oan-apisix-gateway`, `gatewayProxy.pluginMetadata`) | `http-logger` record format | one format for every call log |
| `ApisixPluginConfig`, one per API (this chart) | `proxy-rewrite`, `serverless-pre-function`, `openid-connect`, `serverless-post-function`, `http-logger`, `limit-count` | the same on every route of the API |
| Route (this chart) | nothing of its own, except an operation with its own scope (all of the above, inline) | |

`inlineSharedPlugins: true` writes the shared plugins on every route instead, for an
Ingress Controller that does not resolve `plugin_config_name`. That it does was not checked
on a cluster.

## Call log

`callLog.enabled` adds `http-logger` to the shared plugins: APISIX posts a record of every
call to `callLog.url` (the sandbox's `POST /oan/internal/gateway/logs`), and the sandbox
shows the calls of its apps in API history (source Direct). It needs
`GATEWAY_LOG_INGEST_ENABLED=true` and `GATEWAY_LOG_INGEST_TOKEN` in the sandbox, and in the
APISIX pods the variable `OAN_SANDBOX_LOG_INGEST_AUTHORIZATION` = `Bearer <that token>`
(the plugin reads it at run time with `$env://`, so the token is in no route). A call
refused before the app is known (no token, a bad token) is not stored.

## Install (DevOps)

Values for dev: `environments/dev/values/oan-partner-gateway.yaml` in
[oan-helm](https://github.com/Centre-for-Open-Societal-Systems/oan-helm); starting points
for a UAT and a production gateway: its `examples/gateway/`. The runbook is its
`docs/apisix-gateway.md`, sections 8b and 8c.

```bash
helm upgrade --install oan-partner-gateway deploy/apisix-partner-gateway/k8s \
  -n api6-gateway -f <oan-helm>/environments/dev/values/gateway-common.yaml \
  -f <oan-helm>/environments/dev/values/oan-partner-gateway.yaml
kubectl -n api6-gateway get apisixroutes,apisixupstreams,apisixpluginconfigs,apisixtls -l app=oan-partner-gateway
```

| Value | Dev | Notes |
| --- | --- | --- |
| `hosts` | `partner-api-dev.oanstaging.com` (to confirm) | **Required** (apps share the gateway and are told apart by host). Public host partners call, DNS to the gateway node. The sandbox's `GATEWAY_UAT_URL` is `https://<host>`. |
| `tls.secretName` | `oan-partner-gateway-tls` | Secret (`tls.crt`, `tls.key`) in the release namespace; APISIX terminates TLS for `hosts` (`ApisixTls`). Empty = no `ApisixTls`. |
| `keycloak.issuer` | `https://keycloak.development.oanstaging.com/realms/partner` | Must equal the sandbox's realm as written into tokens. |
| `keycloak.discovery` | empty | `<issuer>/.well-known/openid-configuration` unless APISIX reaches Keycloak elsewhere. |
| `keycloak.audience` | `oan-partner-gateway` | Must equal the sandbox's `GATEWAY_TOKEN_AUDIENCE`. Empty = `aud` not checked. |
| `environmentRole` | `uat` | `production` on a production gateway. |
| `legacyRouteIds` | `true` | See "Migration". |
| `upstreamTls.secretName`, `namespace` | empty | Client certificate for mTLS to the upstreams; per API `<api>.upstreamTls`. See "No way around the gateway". |
| `<api>.enabled`, `host` | see the values file | An enabled API without its host stops the install. |
| `<api>.basePath` | `/api/consent-manager-partner` for `consentManager.partnerApi` | Path the host serves the API under; empty = the root. |
| `callLog.enabled`, `url` | off | See "Call log". |
| `redis.host` | `apisix-redis-master.api6-gateway.svc.cluster.local` | Shared rate-limit counters; empty = per pod. |

UAT and production are two gateways with their own Keycloak: two releases of this chart,
each with its own values (`keycloak.issuer`, `environmentRole`, hosts).

Do not run `adc sync` against a gateway the Ingress Controller manages: each overwrites the
other's routes.
