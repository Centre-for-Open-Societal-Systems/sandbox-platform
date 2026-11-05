# Partner gateway routes (APISIX Ingress Controller)

The OAN partner APIs that apps created in the sandbox call, as APISIX Ingress Controller
resources (`ApisixRoute`, `ApisixUpstream` with `externalNodes`, `ApisixTls`) in the Helm chart
`oan-partner-gateway` (`k8s/`), the same shape as the grievance chart. First API: the Farmer Registry staff API (12 operations + its staff token route).

The routes check the app's **OAuth access token** (`GATEWAY_PARTNER_AUTH=oauth` in the
sandbox) in the header `X-Partner-Token`:

| Check | Answer when it fails |
| --- | --- |
| A token is sent | `401` `Missing app token (X-Partner-Token)` |
| Signature from the realm's JWKS (`openid-connect`, RS256), `iss` = `keycloak.issuer`, `exp`, `typ` | `401` |
| `oan_environments` holds `environmentRole` (`uat`) | `401` |
| This route's id is in `oan_routes` (the app's approved API products) | `403` `This app has no access to this API` |
| `limit-count` per app (`X-OAN-App`, from the token) | `429` |

The upstream then gets `X-OAN-Partner-Id` (the token's `participant_uid`) and `X-OAN-App`;
`X-Partner-Token` is removed. The partner's own `Authorization` (the Farmer Registry staff
token) is passed through unchanged.

## Install (DevOps)

Values for dev: `environments/dev/values/oan-partner-gateway.yaml` in
[oan-helm](https://github.com/Centre-for-Open-Societal-Systems/oan-helm); the runbook is its
`docs/apisix-gateway.md`, section 8b.

```bash
helm upgrade --install oan-partner-gateway deploy/apisix-partner-gateway/k8s \
  -n apisix -f <oan-helm>/environments/dev/values/oan-partner-gateway.yaml
kubectl -n apisix get apisixroutes,apisixupstreams,apisixtls -l app=oan-partner-gateway
```

| Value | Dev | Notes |
| --- | --- | --- |
| `hosts` | `partner-api-dev.oanstaging.com` (to confirm) | **Required** (apps share the gateway and are told apart by host). Public host partners call, DNS to the gateway node. The sandbox's `GATEWAY_UAT_URL` is `https://<host>`. |
| `tls.secretName` | `oan-partner-gateway-tls` | Secret (`tls.crt`, `tls.key`) in the release namespace; APISIX terminates TLS for `hosts` (`ApisixTls`). Empty = no `ApisixTls`. |
| `keycloak.issuer` | `https://keycloak.development.oanstaging.com/realms/partner` | Must equal the sandbox's realm as written into tokens. |
| `keycloak.discovery` | empty | `<issuer>/.well-known/openid-configuration` unless APISIX reaches Keycloak elsewhere. |
| `environmentRole` | `uat` | `production` on a production gateway. |
| `farmerRegistry.upstreamHost` | `staff-farmer.development.oanstaging.com` | |
| `farmerRegistry.keycloakHost`, `keycloakRealm` | `keycloak.development.oanstaging.com`, `staff` | `/farmer-registry/auth/token` (the registry's own staff token). |
| `redis.host` | `apisix-valkey.apisix.svc.cluster.local` | Shared rate-limit counters; empty = per pod. |

The sandbox also needs, on the same gateway, the Admin API reachable from its cluster
(`GATEWAY_ADMIN_URL`) with the **viewer** key (`GATEWAY_ADMIN_TOKEN`). In oauth mode it only
reads the routes (their ids go into the app tokens' `oan_routes`) and writes nothing to the
gateway, so the Ingress Controller stays the only writer.

## Regenerate

Do not edit `k8s/templates/apisix-route.yaml` or `apisix-upstream.yaml` by hand (`apisix-tls.yaml` is hand-written). They are generated from the ADC config the
sandbox is tested against locally (`../apisix-gateway`, `PARTNER_AUTH=oauth`):

```bash
cd ../apisix-gateway && PARTNER_AUTH=oauth python build_apisix_config.py
cd ../oansandbox && python deploy/apisix-partner-gateway/generate_k8s_chart.py \
  ../apisix-gateway/generated/farmer-registry.adc.yaml
```

Do not run `adc sync` against a gateway the Ingress Controller manages: each overwrites the
other's routes.
