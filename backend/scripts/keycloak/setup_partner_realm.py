"""One-time Keycloak setup for participant users.

Creates or updates:

* the realm ``oan-partners`` (no self-registration, brute-force protection,
  TLS required for external clients);
* the user-profile attribute ``participant_uid`` (only admins can see or
  change it);
* the shared client ``oan-partner-api`` participants get tokens from: public,
  password grant only (no browser login, no client credentials), with the
  client roles ``uat``, ``production`` and token claims
  ``participant_uid`` and ``oan_environments`` (the roles held);
* the confidential service-account client ``oan-sandbox-provisioner`` with
  only the realm-management roles the sandbox needs: manage-users,
  view-users, query-users, view-clients, query-clients, manage-clients (app
  keys as OAuth clients with GATEWAY_PARTNER_AUTH=oauth);
* the confidential client ``oan-sandbox-portal`` the portal sign-in uses with
  ``PARTICIPANT_AUTH_PROVIDER=keycloak``: direct access grants only (no
  browser login, no service account), token claim ``participant_uid``, only
  its own roles in its tokens. Its secret goes to KEYCLOAK_LOGIN_CLIENT_SECRET.

Consent Manager partner portal (``--portal-client-id``): use the CM's partner
realm (``--realm partner``, created by the CM chart; this script does not
create it) and the script checks that its portal client, the client role and
the ``partner_id`` user attribute are in place - they belong to the CM chart,
so they are reported, not changed.

``--delete-old-clients`` removes the per-participant clients ``oanp-*`` made
before 26 Oct 2026 (one client per participant did not scale).

The Keycloak admin login is used only here; the sandbox itself signs in as
the provisioner (KEYCLOAK_ADMIN_CLIENT_ID / KEYCLOAK_ADMIN_CLIENT_SECRET).
The provisioner's and the login client's secrets are written into the given
.env files and never printed.

    KC_ADMIN_USER=admin KC_ADMIN_PASSWORD=... python scripts/keycloak/setup_partner_realm.py \\
        --url http://localhost:8080 --env-file ../.env --env-file .env
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import httpx

PROVISIONER_ROLES = ("manage-users", "view-users", "query-users", "view-clients", "query-clients",
                     # GATEWAY_PARTNER_AUTH=oauth: one OAuth client per app key
                     "manage-clients")
ENVIRONMENT_ROLES = {
    "uat": "May call the OAN UAT APIs",
    "production": "May call the OAN production APIs",
}
UID_ATTRIBUTE = "participant_uid"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=os.environ.get("KC_URL", "http://localhost:8080"))
    parser.add_argument("--realm", default="oan-partners")
    parser.add_argument("--client-id", default="oan-sandbox-provisioner")
    parser.add_argument("--partner-client-id", default="oan-partner-api")
    parser.add_argument("--login-client-id", default="oan-sandbox-portal",
                        help="Confidential client of the portal sign-in (PARTICIPANT_AUTH_PROVIDER=keycloak)")
    parser.add_argument("--token-lifespan", type=int, default=300, help="Partner access-token lifetime (s)")
    parser.add_argument("--env-file", action="append", default=[], help="Write KEYCLOAK_ADMIN_CLIENT_SECRET here")
    parser.add_argument("--portal-client-id", default="", help="CM partner portal client to check, e.g. consent-partner-portal")
    parser.add_argument("--portal-role", default="PARTNER_OPERATOR")
    parser.add_argument("--partner-id-attribute", default="partner_id")
    parser.add_argument("--delete-old-clients", action="store_true", help="Remove the old oanp-* clients")
    args = parser.parse_args()
    user, password = os.environ.get("KC_ADMIN_USER", "admin"), os.environ.get("KC_ADMIN_PASSWORD")
    if not password:
        print("Set KC_ADMIN_PASSWORD (the Keycloak admin user's password).", file=sys.stderr)
        return 2

    base = args.url.rstrip("/")
    token = httpx.post(
        f"{base}/realms/master/protocol/openid-connect/token",
        data={"grant_type": "password", "client_id": "admin-cli", "username": user, "password": password},
        timeout=15,
    )
    token.raise_for_status()
    http = httpx.Client(base_url=f"{base}/admin/realms", timeout=30,
                        headers={"Authorization": f"Bearer {token.json()['access_token']}"})
    realm = args.realm

    if args.portal_client_id and http.get(f"/{realm}").status_code == 404:
        print(f"realm '{realm}' does not exist: install the Consent Manager with its partner portal first.",
              file=sys.stderr)
        return 1
    if http.get(f"/{realm}").status_code == 404:
        http.post("", json={
            "realm": realm,
            "displayName": "OAN partners",
            "enabled": True,
            "sslRequired": "external",
            "registrationAllowed": False,
            "loginWithEmailAllowed": False,
            "bruteForceProtected": True,
            "accessTokenLifespan": args.token_lifespan,
        }).raise_for_status()
        print(f"realm '{realm}' created")
    else:
        print(f"realm '{realm}' exists")

    _user_profile_attribute(http, realm)
    _partner_client(http, realm, args.partner_client_id, args.token_lifespan)
    provisioner = _provisioner(http, realm, args.client_id)
    login_client = _login_client(http, realm, args.login_client_id, args.partner_client_id)
    _report_realm(http, realm)
    portal_ok = not args.portal_client_id or _check_portal(http, realm, args)

    if args.delete_old_clients:
        old = [c for c in http.get(f"/{realm}/clients", params={"max": 10000}).json()
               if c["clientId"].startswith("oanp-")]
        for client in old:
            http.delete(f"/{realm}/clients/{client['id']}").raise_for_status()
        print(f"old per-participant clients deleted: {len(old)}")

    secret = http.get(f"/{realm}/clients/{provisioner}/client-secret").json()["value"]
    login_secret = http.get(f"/{realm}/clients/{login_client}/client-secret").json()["value"]
    for env_file in args.env_file:
        _set_env(Path(env_file), "KEYCLOAK_ADMIN_CLIENT_SECRET", secret)
        _set_env(Path(env_file), "KEYCLOAK_LOGIN_CLIENT_SECRET", login_secret)
        print(f"KEYCLOAK_ADMIN_CLIENT_SECRET, KEYCLOAK_LOGIN_CLIENT_SECRET written to {env_file}")
    if not args.env_file:
        print("No --env-file given: read the secret in the Keycloak console (Clients > Credentials).")
    print(f"done: {base}/admin/master/console/#/{realm}/users")
    return 0 if portal_ok else 1


def _user_profile_attribute(http: httpx.Client, realm: str) -> None:
    """Declare participant_uid (Keycloak drops unknown attributes otherwise)."""
    profile = http.get(f"/{realm}/users/profile").json()
    if any(a["name"] == UID_ATTRIBUTE for a in profile.get("attributes", [])):
        print(f"user attribute '{UID_ATTRIBUTE}' exists")
        return
    profile.setdefault("attributes", []).append({
        "name": UID_ATTRIBUTE,
        "displayName": "OAN participant UID",
        "permissions": {"view": ["admin"], "edit": ["admin"]},
        "multivalued": False,
    })
    http.put(f"/{realm}/users/profile", json=profile).raise_for_status()
    print(f"user attribute '{UID_ATTRIBUTE}' added")


def _check_portal(http: httpx.Client, realm: str, args: argparse.Namespace) -> bool:
    """The CM partner portal pieces the sandbox relies on (made by the CM chart)."""
    ok = True
    found = http.get(f"/{realm}/clients", params={"clientId": args.portal_client_id}).json()
    if not found:
        print(f"MISSING: client '{args.portal_client_id}' in realm '{realm}'", file=sys.stderr)
        return False
    roles = {r["name"] for r in http.get(f"/{realm}/clients/{found[0]['id']}/roles").json()}
    if args.portal_role not in roles:
        print(f"MISSING: role '{args.portal_role}' of client '{args.portal_client_id}'", file=sys.stderr)
        ok = False
    profile = http.get(f"/{realm}/users/profile").json()
    if not any(a["name"] == args.partner_id_attribute for a in profile.get("attributes", [])):
        print(f"MISSING: user attribute '{args.partner_id_attribute}' (Keycloak drops undeclared attributes)",
              file=sys.stderr)
        ok = False
    mappers = http.get(f"/{realm}/clients/{found[0]['id']}/protocol-mappers/models").json()
    if not any(m.get("config", {}).get("claim.name") == args.partner_id_attribute for m in mappers):
        print(f"MISSING: a mapper putting '{args.partner_id_attribute}' into '{args.portal_client_id}' tokens",
              file=sys.stderr)
        ok = False
    if ok:
        print(f"partner portal: client '{args.portal_client_id}', role '{args.portal_role}', "
              f"attribute + claim '{args.partner_id_attribute}' in place")
    return ok


def _partner_client(http: httpx.Client, realm: str, client_id: str, lifespan: int) -> None:
    body = {
        "clientId": client_id,
        "name": "OAN partner API login",
        "description": "Participants get access tokens here (password grant); roles = approved environments",
        "enabled": True,
        "protocol": "openid-connect",
        "publicClient": True,
        "serviceAccountsEnabled": False,
        "standardFlowEnabled": False,
        "implicitFlowEnabled": False,
        "directAccessGrantsEnabled": True,
        "frontchannelLogout": False,
        "redirectUris": [],
        "webOrigins": [],
        "fullScopeAllowed": False,
        "attributes": {"access.token.lifespan": str(lifespan)},
    }
    found = http.get(f"/{realm}/clients", params={"clientId": client_id}).json()
    if found:
        uuid = found[0]["id"]
        http.put(f"/{realm}/clients/{uuid}", json={**found[0], **body}).raise_for_status()
        print(f"client '{client_id}' updated")
    else:
        http.post(f"/{realm}/clients", json=body).raise_for_status()
        uuid = http.get(f"/{realm}/clients", params={"clientId": client_id}).json()[0]["id"]
        print(f"client '{client_id}' created")

    existing = {r["name"] for r in http.get(f"/{realm}/clients/{uuid}/roles").json()}
    for name, description in ENVIRONMENT_ROLES.items():
        if name not in existing:
            http.post(f"/{realm}/clients/{uuid}/roles", json={"name": name, "description": description}).raise_for_status()
    # fullScopeAllowed is off: the token carries only this client's roles.
    roles = [r for r in http.get(f"/{realm}/clients/{uuid}/roles").json() if r["name"] in ENVIRONMENT_ROLES]
    http.post(f"/{realm}/clients/{uuid}/scope-mappings/clients/{uuid}", json=roles).raise_for_status()
    print(f"client roles: {', '.join(ENVIRONMENT_ROLES)}")

    mappers = {m["name"] for m in http.get(f"/{realm}/clients/{uuid}/protocol-mappers/models").json()}
    wanted = [
        {
            "name": UID_ATTRIBUTE,
            "protocol": "openid-connect",
            "protocolMapper": "oidc-usermodel-attribute-mapper",
            "config": {
                "user.attribute": UID_ATTRIBUTE, "claim.name": UID_ATTRIBUTE, "jsonType.label": "String",
                "access.token.claim": "true", "id.token.claim": "false", "userinfo.token.claim": "false",
                "introspection.token.claim": "true",
            },
        },
        {
            "name": "oan_environments",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-usermodel-client-role-mapper",
            "config": {
                "usermodel.clientRoleMapping.clientId": client_id, "claim.name": "oan_environments",
                "multivalued": "true", "jsonType.label": "String",
                "access.token.claim": "true", "id.token.claim": "false", "userinfo.token.claim": "false",
                "introspection.token.claim": "true",
            },
        },
    ]
    for mapper in wanted:
        if mapper["name"] not in mappers:
            http.post(f"/{realm}/clients/{uuid}/protocol-mappers/models", json=mapper).raise_for_status()
    print(f"token claims: {UID_ATTRIBUTE}, oan_environments")


def _login_client(http: httpx.Client, realm: str, client_id: str, partner_client_id: str) -> str:
    """The portal sign-in's confidential client: direct grant only, claims participant_uid and
    oan_environments (the partner client's roles held), so a gateway that checks partner
    tokens accepts the portal's own token for try-it calls."""
    body = {
        "clientId": client_id,
        "name": "OAN sandbox portal sign-in",
        "description": "The sandbox API signs participants in here (direct grant, client secret)",
        "enabled": True,
        "protocol": "openid-connect",
        "publicClient": False,
        "clientAuthenticatorType": "client-secret",
        "serviceAccountsEnabled": False,
        "standardFlowEnabled": False,
        "implicitFlowEnabled": False,
        "directAccessGrantsEnabled": True,
        "frontchannelLogout": False,
        "redirectUris": [],
        "webOrigins": [],
        # Only the partner client's environment roles in its tokens (scope mapping below).
        "fullScopeAllowed": False,
    }
    found = http.get(f"/{realm}/clients", params={"clientId": client_id}).json()
    if found:
        uuid = found[0]["id"]
        http.put(f"/{realm}/clients/{uuid}", json={**found[0], **body}).raise_for_status()
        print(f"client '{client_id}' updated")
    else:
        http.post(f"/{realm}/clients", json=body).raise_for_status()
        uuid = http.get(f"/{realm}/clients", params={"clientId": client_id}).json()[0]["id"]
        print(f"client '{client_id}' created")
    mappers = {m["name"] for m in http.get(f"/{realm}/clients/{uuid}/protocol-mappers/models").json()}
    if UID_ATTRIBUTE not in mappers:
        http.post(f"/{realm}/clients/{uuid}/protocol-mappers/models", json={
            "name": UID_ATTRIBUTE,
            "protocol": "openid-connect",
            "protocolMapper": "oidc-usermodel-attribute-mapper",
            "config": {
                "user.attribute": UID_ATTRIBUTE, "claim.name": UID_ATTRIBUTE, "jsonType.label": "String",
                "access.token.claim": "true", "id.token.claim": "false", "userinfo.token.claim": "false",
                "introspection.token.claim": "true",
            },
        }).raise_for_status()
    partner = http.get(f"/{realm}/clients", params={"clientId": partner_client_id}).json()[0]["id"]
    roles = [r for r in http.get(f"/{realm}/clients/{partner}/roles").json() if r["name"] in ENVIRONMENT_ROLES]
    http.post(f"/{realm}/clients/{uuid}/scope-mappings/clients/{partner}", json=roles).raise_for_status()
    if "oan_environments" not in mappers:
        http.post(f"/{realm}/clients/{uuid}/protocol-mappers/models", json={
            "name": "oan_environments",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-usermodel-client-role-mapper",
            "config": {
                "usermodel.clientRoleMapping.clientId": partner_client_id, "claim.name": "oan_environments",
                "multivalued": "true", "jsonType.label": "String",
                "access.token.claim": "true", "id.token.claim": "false", "userinfo.token.claim": "false",
                "introspection.token.claim": "true",
            },
        }).raise_for_status()
    print(f"token claims: {UID_ATTRIBUTE}, oan_environments ({partner_client_id} roles)")
    return uuid


def _report_realm(http: httpx.Client, realm: str) -> None:
    """Realm settings the sign-in relies on; reported, not changed (the realm may be the CM's)."""
    settings = http.get(f"/{realm}").json()
    if not settings.get("bruteForceProtected"):
        print("NOTE: brute-force detection is off in this realm (Realm settings > Security defenses).")
    if not settings.get("revokeRefreshToken"):
        print("NOTE: refresh tokens are not rotated (Realm settings > Tokens > Revoke refresh token).")


def _provisioner(http: httpx.Client, realm: str, client_id: str) -> str:
    clients = http.get(f"/{realm}/clients", params={"clientId": client_id}).json()
    if not clients:
        http.post(f"/{realm}/clients", json={
            "clientId": client_id,
            "name": "OAN sandbox (manages participant users)",
            "enabled": True,
            "publicClient": False,
            "clientAuthenticatorType": "client-secret",
            "serviceAccountsEnabled": True,
            "standardFlowEnabled": False,
            "implicitFlowEnabled": False,
            "directAccessGrantsEnabled": False,
            "redirectUris": [],
            "webOrigins": [],
        }).raise_for_status()
        clients = http.get(f"/{realm}/clients", params={"clientId": client_id}).json()
        print(f"client '{client_id}' created")
    provisioner = clients[0]["id"]

    account = http.get(f"/{realm}/clients/{provisioner}/service-account-user").json()["id"]
    management = http.get(f"/{realm}/clients", params={"clientId": "realm-management"}).json()[0]["id"]
    path = f"/{realm}/users/{account}/role-mappings/clients/{management}"
    available = {r["name"]: r for r in http.get(f"/{realm}/clients/{management}/roles").json()}
    current = {r["name"]: r for r in http.get(path).json()}
    # Exactly these roles: anything else (e.g. manage-clients from the old setup) is taken away.
    extra = [role for name, role in current.items() if name not in PROVISIONER_ROLES]
    if extra:
        http.request("DELETE", path, json=extra).raise_for_status()
    http.post(path, json=[available[name] for name in PROVISIONER_ROLES]).raise_for_status()
    print(f"service account roles: {', '.join(PROVISIONER_ROLES)}"
          + (f" (removed: {', '.join(r['name'] for r in extra)})" if extra else ""))
    return provisioner


def _set_env(path: Path, name: str, value: str) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    line = f"{name}={value}"
    if re.search(rf"^{name}=.*$", text, flags=re.M):
        text = re.sub(rf"^{name}=.*$", lambda _: line, text, flags=re.M)
    else:
        text = text.rstrip("\n") + f"\n{line}\n"
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
