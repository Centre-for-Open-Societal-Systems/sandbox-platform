# Partner gateway routes (APISIX Ingress Controller)

The OAN partner APIs that apps created in the sandbox call, as APISIX Ingress Controller
resources in the Helm chart `oan-partner-gateway` (`k8s/`).

| Value | API | Gateway path | Operations |
| --- | --- | --- | --- |
| `consentManager.portalApi` | Consent Manager partner portal API (`/consent/v1/partner-portal` of the console host) | `/consent-manager/...` | 16 |
| `consentManager.partnerApi` | Consent Manager partner API (validate, status, receipts, JWKS) | `/consent-manager-partner/...` | 5 |
| `partnerManagement.keysApi` | Partner Management key fetch API | `/partner-management-keys/...` | 4 |
| `aggregationLayer` | Aggregation Layer (DCI search) | `/aggregation-layer/...` | 1 |

Only what partners call. Staff use their own portals, so no staff API is in the chart: not
the registries' staff APIs, the Partner Management admin API or the Consent Manager's staff
routes. The local test gateway (`../apisix-gateway`) still serves those; `build.sh deploy`
leaves them out.

Each API is switched on by `enabled` and has an `ApisixUpstream` (its public host), an
`ApisixPluginConfig` (the plugins every route shares) and an `ApisixRoute` (one rule per
operation, with only its own rate limit, pointing at the plugin config). The prefix is
removed before the call.

The routes check the app's **OAuth access token** (`GATEWAY_PARTNER_AUTH=oauth` in the
sandbox) in the header `X-Partner-Token`:

| Check | Answer when it fails |
| --- | --- |
| A token is sent | `401` `Missing app token (X-Partner-Token)` |
| Signature from the realm's JWKS (`openid-connect`, RS256), `iss` = `keycloak.issuer`, `exp`, `typ` | `401` |
| `oan_environments` holds `environmentRole` (`uat`) | `401` |
| This route's id is in `oan_routes` (the app's approved API products) | `403` `This app has no access to this API` |
| The caller's address is in the app's IP whitelist (`oan_ips`), when it has one | `403` `This app does not accept calls from your IP address` |
| `limit-count`: the app's own limits a minute and a day (`oan_limit_minute`, `oan_limit_day`), and 120 a minute per app and route | `429` |

The upstream then gets `X-OAN-Partner-Id` (the token's `participant_uid`) and `X-OAN-App`;
`X-Partner-Token` is removed. The caller's own `Authorization` (the partner's token, where
the API asks for one) is passed through unchanged.

## Where each plugin lives

| Place | Plugins | Why there |
| --- | --- | --- |
| Global rule (`oan-apisix-gateway`, `gatewayProxy.plugins`) | `request-id`, `prometheus` | every request of the gateway |
| Plugin metadata (`oan-apisix-gateway`, `gatewayProxy.pluginMetadata`) | `http-logger` record format | one format for every call log |
| `ApisixPluginConfig`, one per API (this chart) | `serverless-pre-function`, `openid-connect`, `serverless-post-function`, `proxy-rewrite`, `limit-count`, `http-logger` | the same on every route of the API |
| Route (this chart) | nothing of its own | |

`inlineSharedPlugins: true` writes the shared plugins on every route instead, for an
Ingress Controller that does not resolve `plugin_config_name`. That it does was not checked
on a cluster.

## What the token carries

The sandbox writes these claims on each app key's Keycloak client; the gateway reads them
on every call, so no consumer is needed:

| Claim | From | The gateway |
| --- | --- | --- |
| `oan_app`, `participant_uid` | the app and its owner | names the app (`X-OAN-App`, `X-OAN-Partner-Id`) |
| `oan_environments` | the app's environment | refuses another environment's app (`401`) |
| `oan_routes` | the app's approved API products | refuses a route outside them (`403`) |
| `oan_ips` | the app's IP whitelist (empty = any address) | refuses another caller address (`403`) |
| `oan_limit_minute`, `oan_limit_day` | the most generous limits of the app's products, with `GATEWAY_RATE_LIMIT_ENABLED` (`0` = none) | counts the app's calls per API (`429`) |

A change in the sandbox reaches the gateway with the next token: a token already issued
keeps its values until it expires (five minutes). The app's own limits count per API (all
routes of one API together; each API has its own budget), because APISIX keeps the
counters under the plugin config. With `inlineSharedPlugins` they count per route. The
caller address is the one APISIX sees: behind a proxy, only a trusted one may set it.

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
| `environmentRole` | `uat` | `production` on a production gateway. |
| `<api>.enabled`, `host` | see the values file | An enabled API without its host stops the install. |
| `consentManager.partnerApi.basePath` | `/api/consent-manager-partner` | Path the host serves the API under; empty = the root. |
| `callLog.enabled`, `url` | off | See "Call log". |
| `redis.host` | `apisix-redis-master.api6-gateway.svc.cluster.local` | Shared rate-limit counters; empty = per pod. |

UAT and production are two gateways with their own Keycloak: two releases of this chart,
each with its own values (`keycloak.issuer`, `environmentRole`, hosts).

The sandbox also needs, on the same gateway, the Admin API reachable from its cluster
(`GATEWAY_ADMIN_URL`) with the **viewer** key (`GATEWAY_ADMIN_TOKEN`). In oauth mode it only
reads the routes (their ids go into the app tokens' `oan_routes`) and writes nothing to the
gateway, so the Ingress Controller stays the only writer.

## Regenerate

Do not edit `k8s/templates/apisix-route.yaml`, `apisix-upstream.yaml`,
`apisix-pluginconfig.yaml` or `_shared-plugins.tpl` by hand (`apisix-tls.yaml` and
`_helpers.tpl` are hand-written). They are generated from the ADC config the sandbox is
tested against locally (`../apisix-gateway`):

```bash
cd ../apisix-gateway && sh build.sh deploy
cd ../oansandbox && python deploy/apisix-partner-gateway/generate_k8s_chart.py \
  ../apisix-gateway/generated/deploy/partner-apis.adc.yaml
```

A new API: add it to `PARTNER_APIS` in `build_apisix_config.py` and to `API` and
`PLACEHOLDERS` in `generate_k8s_chart.py`, with its values in `k8s/values.yaml`. An API or
path only staff call goes into `STAFF_ONLY_APIS` / `PARTNER_PATHS` there, so it stays out
of the chart.

Do not run `adc sync` against a gateway the Ingress Controller manages: each overwrites the
other's routes.
