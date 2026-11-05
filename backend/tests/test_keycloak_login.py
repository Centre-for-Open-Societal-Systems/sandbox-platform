"""Participant sign-in with Keycloak (PARTICIPANT_AUTH_PROVIDER=keycloak): Keycloak checks
the password and issues the tokens; the API verifies every token itself (RS256 from the
realm's JWKS, iss, exp, typ, azp, sid) and binds it to the sandbox session."""

from __future__ import annotations

import secrets
import time
import uuid

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config.settings import settings
from app.integrations import keycloak, keycloak_oidc
from app.models.participant import Participant, ParticipantToken
from tests.conftest import PARTICIPANT_PASSWORD
from tests.test_iam_users import FakeKeycloak

ISSUER = "https://auth.example.org/realms/partner"
CLIENT = "oan-sandbox-portal"
PROFILE = "/oan/participant/profile"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
KID = "test-key-1"


class FakeRealm(FakeKeycloak):
    """Keycloak's admin API (users) plus its token endpoint (direct + refresh grant)."""

    def __init__(self):
        super().__init__()
        self.sessions: dict[str, dict] = {}  # sid -> {"user": id, "refresh": token}
        self.grants: list[str] = []
        self.lifespan = 300

    def install(self, monkeypatch):
        super().install(monkeypatch)
        for name, value in {"KEYCLOAK_REALM": "partner", "PARTICIPANT_AUTH_PROVIDER": "keycloak",
                            "KEYCLOAK_LOGIN_CLIENT_ID": CLIENT, "KEYCLOAK_LOGIN_CLIENT_SECRET": "login-secret",
                            "KEYCLOAK_ISSUER": ISSUER}.items():
            monkeypatch.setattr(settings, name, value)
        monkeypatch.setattr(keycloak, "delete_session", self.delete_session)
        monkeypatch.setattr(keycloak_oidc.httpx, "post", self.post)
        monkeypatch.setattr(keycloak_oidc, "_jwks_client", lambda: self)
        return self

    # --- JWKS (stands in for PyJWKClient)
    def get_signing_key_from_jwt(self, token):
        if jwt.get_unverified_header(token).get("kid") != KID:
            raise jwt.PyJWKClientError("Unable to find a signing key that matches")
        return jwt.PyJWK.from_dict({**jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key(), as_dict=True),
                                    "kid": KID, "alg": "RS256"})

    # --- token endpoint
    def post(self, url, data=None, timeout=None):
        assert url.startswith("http://keycloak.internal:8080/realms/partner/protocol/openid-connect/")
        assert (data["client_id"], data["client_secret"]) == (CLIENT, "login-secret")
        if url.endswith("/revoke"):
            self._end(next((s for s, v in self.sessions.items() if v["refresh"] == data["token"]), None))
            return httpx.Response(200)
        self.grants.append(data["grant_type"])
        if data["grant_type"] == "password":
            uid = self.find_user(data["username"])
            user = self.users.get(uid)
            if user is None or user.get("password") != data["password"]:
                return self._error("invalid_grant", "Invalid user credentials")
            if not user["enabled"]:
                return self._error("invalid_grant", "Account disabled")
            sid = str(uuid.uuid4())
            self.sessions[sid] = {"user": uid}
        else:
            sid = next((s for s, v in self.sessions.items() if v["refresh"] == data["refresh_token"]), None)
            if sid is None:
                return self._error("invalid_grant", "Invalid refresh token")
            uid = self.sessions[sid]["user"]
        refresh = secrets.token_urlsafe(16)  # rotated on every grant
        self.sessions[sid]["refresh"] = refresh
        return httpx.Response(200, json={
            "access_token": self.token(uid, sid), "refresh_token": refresh,
            "expires_in": self.lifespan, "refresh_expires_in": 1800, "token_type": "Bearer"})

    def token(self, uid, sid, override=None):
        now = int(time.time())
        claims = {"iss": ISSUER, "sub": uid, "iat": now, "exp": now + self.lifespan, "jti": str(uuid.uuid4()),
                  "typ": "Bearer", "azp": CLIENT, "sid": sid,
                  "participant_uid": self.users[uid]["attributes"]["participant_uid"], **(override or {})}
        return jwt.encode({k: v for k, v in claims.items() if v is not None}, KEY, algorithm="RS256",
                          headers={"kid": KID})

    @staticmethod
    def _error(error, description):
        return httpx.Response(401 if error == "invalid_client" else 400,
                              json={"error": error, "error_description": description})

    def _end(self, sid):
        self.sessions.pop(sid, None)

    def delete_session(self, sid):
        self._end(sid)

    def logout_user(self, user_id):
        super().logout_user(user_id)
        for sid in [s for s, v in self.sessions.items() if v["user"] == user_id]:
            self._end(sid)


@pytest.fixture
def realm(monkeypatch):
    return FakeRealm().install(monkeypatch)


@pytest.fixture
def approved(db_session, realm, verified_participant) -> Participant:
    """The participant as approval leaves it: a Keycloak user holding its password."""
    from app.services import iam_user_service
    iam_user_service.sync(db_session, verified_participant, password=PARTICIPANT_PASSWORD)
    return verified_participant


def _login(client, password=PARTICIPANT_PASSWORD, email="partner@example.org"):
    return client.post("/oan/participant/auth/login", json={"email_id": email, "password": password})


def _headers(data):
    return {"x-access-token": data["access_token"], "x-auth-key": data["auth_key"]}


def test_sign_in_returns_keycloak_tokens_that_open_the_portal(client, db_session, realm, approved):
    response = _login(client)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    claims = jwt.decode(data["access_token"], options={"verify_signature": False})
    assert (claims["iss"], claims["azp"], claims["typ"]) == (ISSUER, CLIENT, "Bearer")
    assert data["token_expiry"] == 300 and data["refresh_token"]
    session = db_session.query(ParticipantToken).filter_by(unique_id=data["auth_key"]).one()
    assert session.keycloak_sid == claims["sid"]
    assert realm.grants == ["password"]

    profile = client.get(PROFILE, headers=_headers(data))
    assert profile.status_code == 200, profile.text


def test_wrong_password_is_refused_like_before(client, realm, approved):
    response = _login(client, password="Wrong#Pass1")
    assert response.status_code == 401
    assert response.json()["message"] == "No such email address or password."


def test_unknown_email_never_reaches_keycloak(client, realm, approved):
    assert _login(client, email="nobody@example.org").status_code == 401
    assert realm.grants == []


def test_pending_participant_gets_the_old_message(client, db_session, realm, verified_participant):
    verified_participant.is_approved = 0
    db_session.commit()
    response = _login(client)
    assert response.status_code == 401 and "waiting for UAT approval" in response.text
    assert realm.grants == []


def test_password_changed_in_keycloak_is_the_one_that_counts(client, realm, approved):
    [uid] = realm.users
    realm.set_password(uid, "Changed#InKeycloak1")
    assert _login(client).status_code == 401  # the sandbox's old hash no longer opens anything
    assert _login(client, password="Changed#InKeycloak1").status_code == 200


def test_first_sign_in_of_a_participant_approved_before_keycloak(client, db_session, realm, verified_participant):
    # Approved, but Keycloak has no user / password yet: the sandbox's own check
    # lets them in once and hands Keycloak the password.
    response = _login(client)
    assert response.status_code == 200, response.text
    assert realm.grants == ["password", "password"]
    assert realm.only["password"] == PARTICIPANT_PASSWORD
    realm.grants.clear()
    assert _login(client).status_code == 200 and realm.grants == ["password"]


@pytest.mark.parametrize("bad", ["alg-none", "hs256-with-public-key", "other-issuer", "other-client",
                                 "id-token", "expired", "unknown-kid", "other-session", "no-sid"])
def test_tampered_or_foreign_tokens_are_refused(client, realm, approved, bad):
    data = _login(client).json()["data"]
    [uid] = realm.users
    sid = jwt.decode(data["access_token"], options={"verify_signature": False})["sid"]
    if bad == "alg-none":
        token = jwt.encode({"sub": uid, "sid": sid}, None, algorithm="none")
    elif bad == "hs256-with-public-key":
        token = jwt.encode(jwt.decode(data["access_token"], options={"verify_signature": False}),
                           "not-the-rsa-key", algorithm="HS256", headers={"kid": KID})
    else:
        override = {"other-issuer": {"iss": "https://evil.example.org/realms/partner"},
                    "other-client": {"azp": "consent-partner-portal"},
                    "id-token": {"typ": "ID"},
                    "expired": {"exp": int(time.time()) - 120, "iat": int(time.time()) - 600},
                    "other-session": {"sid": str(uuid.uuid4())},
                    "no-sid": {"sid": None}}.get(bad, {})
        token = realm.token(uid, sid, override)
        if bad == "unknown-kid":
            token = jwt.encode(jwt.decode(token, options={"verify_signature": False}), KEY,
                               algorithm="RS256", headers={"kid": "rotated-away"})
    response = client.get(PROFILE, headers={"x-access-token": token, "x-auth-key": data["auth_key"]})
    assert response.status_code == 401, (bad, response.text)


def test_refresh_rotates_and_stays_on_the_session(client, realm, approved):
    data = _login(client).json()["data"]
    refreshed = client.post("/oan/participant/auth/refresh", json={"refresh_token": data["refresh_token"]},
                            headers={"x-auth-key": data["auth_key"]})
    assert refreshed.status_code == 200, refreshed.text
    new = refreshed.json()["data"]
    assert new["refresh_token"] != data["refresh_token"] and new["token_expiry"] == 300
    assert client.get(PROFILE, headers={"x-access-token": new["access_token"],
                                        "x-auth-key": data["auth_key"]}).status_code == 200
    # The rotated-away refresh token is dead.
    again = client.post("/oan/participant/auth/refresh", json={"refresh_token": data["refresh_token"]},
                        headers={"x-auth-key": data["auth_key"]})
    assert again.status_code == 401


def test_refresh_token_of_another_session_is_refused(client, realm, approved):
    first = _login(client).json()["data"]
    second = _login(client).json()["data"]
    crossed = client.post("/oan/participant/auth/refresh", json={"refresh_token": second["refresh_token"]},
                          headers={"x-auth-key": first["auth_key"]})
    assert crossed.status_code == 401


def test_sign_out_ends_the_keycloak_session(client, realm, approved):
    data = _login(client).json()["data"]
    sid = jwt.decode(data["access_token"], options={"verify_signature": False})["sid"]
    assert client.post("/oan/participant/auth/logout", headers=_headers(data)).status_code == 200
    assert sid not in realm.sessions
    assert client.get(PROFILE, headers=_headers(data)).status_code == 401
    refresh = client.post("/oan/participant/auth/refresh", json={"refresh_token": data["refresh_token"]},
                          headers={"x-auth-key": data["auth_key"]})
    assert refresh.status_code == 401


def test_reject_ends_keycloak_sessions_and_tokens(client, db_session, realm, approved, admin_headers):
    data = _login(client).json()["data"]
    rejected = client.post("/oan/admin/participants/reject", headers=admin_headers, json={
        "participant_id": approved.participant_id, "environment": "UAT",
        "rejection_reason": "Organisation could not be verified."})
    assert rejected.status_code == 200, rejected.text
    assert realm.sessions == {} and realm.only["logouts"] == 1
    assert client.get(PROFILE, headers=_headers(data)).status_code in (401, 403)
    assert _login(client).status_code == 401


def test_change_password_is_checked_by_keycloak(client, realm, approved):
    data = _login(client).json()["data"]
    wrong = client.post("/oan/participant/auth/change-password", headers=_headers(data),
                        json={"old_password": "Wrong#Pass1", "new_password": "Brand#New2026"})
    assert wrong.status_code == 400 and "Current password is incorrect" in wrong.text
    ok = client.post("/oan/participant/auth/change-password", headers=_headers(data),
                     json={"old_password": PARTICIPANT_PASSWORD, "new_password": "Brand#New2026"})
    assert ok.status_code == 200, ok.text
    assert realm.only["password"] == "Brand#New2026"
    # The check's own Keycloak session was revoked; only the portal's session is left.
    assert len(realm.sessions) == 1
    assert _login(client, password="Brand#New2026").status_code == 200


def test_keycloak_down_is_not_a_wrong_password(client, realm, approved, monkeypatch):
    def unreachable(*args, **kwargs):
        raise httpx.ConnectError("refused")
    monkeypatch.setattr(keycloak_oidc.httpx, "post", unreachable)
    response = _login(client)
    assert response.status_code == 502 and "unavailable" in response.text


def test_keycloak_mode_needs_its_settings():
    with pytest.raises(ValueError, match="PARTICIPANT_AUTH_PROVIDER=keycloak"):
        type(settings)(PARTICIPANT_AUTH_PROVIDER="keycloak", KEYCLOAK_PROVISIONING_ENABLED=True,
                       KEYCLOAK_URL="http://kc", KEYCLOAK_LOGIN_CLIENT_SECRET="")
