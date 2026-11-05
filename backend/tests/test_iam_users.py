"""Participants' Keycloak users: created at UAT approval (never at sign-up), roles per approved environment."""

from __future__ import annotations

import itertools

import pytest

from app.config.settings import settings
from app.core.exceptions import UpstreamError
from app.integrations import keycloak
from app.models.app import ParticipantIamUser
from app.models.participant import Participant

SIGNUP = {
    "first_name": "Kebede",
    "last_name": "Alemu",
    "country_code": "ET",
    "mobile_number": "0911000555",
    "email_id": "Partner@agri.example.org",
    "category_id": 1,
    "company_name": "Agri Partner PLC",
    "password": "AgriPartner#2026",
    "declaration": True,
}
USERNAME = "partner@agri.example.org"


class FakeKeycloak:
    def __init__(self):
        self.users: dict[str, dict] = {}
        self.fail = False
        self._ids = itertools.count(1)

    def install(self, monkeypatch):
        monkeypatch.setattr(settings, "KEYCLOAK_PROVISIONING_ENABLED", True)
        monkeypatch.setattr(settings, "KEYCLOAK_REALM", "oan-partners")  # not the local .env
        monkeypatch.setattr(settings, "KEYCLOAK_URL", "http://keycloak.internal:8080")
        monkeypatch.setattr(settings, "KEYCLOAK_PUBLIC_URL", "https://auth.example.org")
        monkeypatch.setattr(settings, "KEYCLOAK_ADMIN_CLIENT_SECRET", "provisioner-secret")
        for name in ("find_user", "create_user", "update_user", "set_password", "set_environment_roles",
                     "logout_user"):
            monkeypatch.setattr(keycloak, name, getattr(self, name))
        return self

    def _check(self):
        if self.fail:
            raise UpstreamError("Keycloak could not be reached at KEYCLOAK_URL.")

    def find_user(self, username):
        self._check()
        return next((uid for uid, u in self.users.items() if u["username"] == username), None)

    def create_user(self, username, password=None, **profile):
        self._check()
        uid = f"kc-{next(self._ids)}"
        self.users[uid] = {"username": username, "password": password, "roles": set(), **profile}
        return uid

    def update_user(self, user_id, **profile):
        self._check()
        self.users[user_id].update(profile)

    def set_password(self, user_id, password):
        self._check()
        self.users[user_id]["password"] = password

    def logout_user(self, user_id):
        self._check()
        self.users[user_id]["logouts"] = self.users[user_id].get("logouts", 0) + 1

    def set_environment_roles(self, user_id, roles):
        self._check()
        self.users[user_id]["roles"] = set(roles)

    @property
    def only(self) -> dict:
        [user] = self.users.values()
        return user


def _signup(client, db_session) -> Participant:
    signup = client.post("/oan/participant/auth/signup", json=SIGNUP)
    assert signup.status_code == 200, signup.text
    return db_session.query(Participant).filter_by(unique_id=signup.json()["data"]["unique_id"]).one()


def _decide(client, admin_headers, user, action="approve", environment="UAT"):
    body = {"participant_id": user.participant_id, "environment": environment}
    if action == "reject":
        body["rejection_reason"] = "Organisation could not be verified."
    response = client.post(f"/oan/admin/participants/{action}", headers=admin_headers, json=body)
    assert response.status_code == 200, response.text


def _login(client, password=SIGNUP["password"]) -> dict:
    response = client.post("/oan/participant/auth/login", json={"email_id": USERNAME, "password": password})
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    return {"x-access-token": data["access_token"], "x-auth-key": data["auth_key"]}


def test_nothing_is_created_while_provisioning_is_off(client, db_session, admin_headers):
    user = _signup(client, db_session)
    _decide(client, admin_headers, user)

    assert db_session.query(ParticipantIamUser).count() == 0
    listed = client.get(
        f"/oan/admin/participants/{user.participant_id}/iam-account", headers=admin_headers
    ).json()["data"]
    assert listed == {"enabled": False, "account": None}


def test_sign_up_creates_nothing_in_keycloak_until_uat_is_approved(
    client, db_session, admin_headers, monkeypatch
):
    fake = FakeKeycloak().install(monkeypatch)
    user = _signup(client, db_session)

    assert fake.users == {} and db_session.query(ParticipantIamUser).count() == 0
    listed = client.get(
        f"/oan/admin/participants/{user.participant_id}/iam-account", headers=admin_headers
    ).json()["data"]
    assert listed == {"enabled": True, "account": None}
    # Nothing to retry either: the user is made by the approval.
    retried = client.post(
        f"/oan/admin/participants/{user.participant_id}/iam-account/retry", headers=admin_headers
    )
    assert retried.status_code == 400 and "approved" in retried.text
    assert fake.users == {}

    _decide(client, admin_headers, user)
    kc = fake.only
    assert (kc["username"], kc["email"]) == (USERNAME, USERNAME)
    assert kc["enabled"] is True and kc["roles"] == {"uat"}
    assert kc["attributes"] == {"participant_uid": str(user.unique_id)}
    assert kc["password"] is None  # the sandbox only has a hash
    row = db_session.query(ParticipantIamUser).one()
    assert (row.status, row.roles, row.realm) == ("ACTIVE", "uat", "oan-partners")
    assert row.password_synced_at is None

    _login(client)  # the first portal sign-in hands Keycloak the password
    assert fake.only["password"] == SIGNUP["password"]
    db_session.expire_all()
    assert db_session.query(ParticipantIamUser).one().password_synced_at is not None


def test_a_rejected_sign_up_never_reaches_keycloak(client, db_session, admin_headers, monkeypatch):
    fake = FakeKeycloak().install(monkeypatch)
    user = _signup(client, db_session)

    _decide(client, admin_headers, user, action="reject")
    assert fake.users == {} and db_session.query(ParticipantIamUser).count() == 0

    # Approved later after all: created then, like any approval.
    _decide(client, admin_headers, user)
    assert fake.only["enabled"] is True and fake.only["roles"] == {"uat"}


def test_approval_gives_the_environment_role_and_reject_takes_it_away(
    client, db_session, admin_headers, monkeypatch
):
    fake = FakeKeycloak().install(monkeypatch)
    user = _signup(client, db_session)

    _decide(client, admin_headers, user)
    assert fake.only["enabled"] is True and fake.only["roles"] == {"uat"}
    assert fake.only["email_verified"] is True

    user.is_prod_requested = True
    db_session.commit()
    _decide(client, admin_headers, user, environment="PRODUCTION")
    assert fake.only["roles"] == {"uat", "production"}

    account = client.get(
        f"/oan/admin/participants/{user.participant_id}/iam-account", headers=admin_headers
    ).json()["data"]["account"]
    assert account["username"] == USERNAME and account["roles"] == ["production", "uat"]
    assert account["client_id"] == "oan-partner-api" and account["grant_type"] == "password"
    assert account["token_url"] == "https://auth.example.org/realms/oan-partners/protocol/openid-connect/token"
    assert SIGNUP["password"] not in str(account)

    _decide(client, admin_headers, user, action="reject", environment="PRODUCTION")
    assert fake.only["roles"] == {"uat"}
    _decide(client, admin_headers, user, action="reject")
    assert fake.only["roles"] == set() and fake.only["enabled"] is False
    assert len(fake.users) == 1  # one user per participant, never one per environment


def test_disable_enable_and_delete_follow_the_participant(client, db_session, admin_headers, monkeypatch):
    fake = FakeKeycloak().install(monkeypatch)
    user = _signup(client, db_session)
    _decide(client, admin_headers, user)

    client.post("/oan/admin/participants/toggle", headers=admin_headers,
                json={"id": user.participant_id, "is_enabled": False})
    assert fake.only["enabled"] is False and fake.only["roles"] == set()
    client.post("/oan/admin/participants/toggle", headers=admin_headers,
                json={"id": user.participant_id, "is_enabled": True})
    assert fake.only["enabled"] is True and fake.only["roles"] == {"uat"}

    client.delete(f"/oan/admin/participants/{user.participant_id}", headers=admin_headers)
    assert fake.only["enabled"] is False and fake.only["roles"] == set()


def test_password_changes_reach_keycloak(
    client, db_session, admin_headers, monkeypatch, mailbox
):
    fake = FakeKeycloak().install(monkeypatch)
    user = _signup(client, db_session)
    _decide(client, admin_headers, user)

    changed = client.post("/oan/participant/auth/change-password", headers=_login(client), json={
        "old_password": SIGNUP["password"], "new_password": "Changed#2026", "confirm_password": "Changed#2026"})
    assert changed.status_code == 200, changed.text
    assert fake.only["password"] == "Changed#2026"

    client.post("/oan/participant/auth/forgot-password", json={"email_id": USERNAME})
    reset = client.post("/oan/participant/auth/reset-password",
                        json={"token": mailbox[-1]["values"]["token"], "new_password": "ResetTo#2026"})
    assert reset.status_code == 200, reset.text
    assert fake.only["password"] == "ResetTo#2026"


def test_keycloak_failure_does_not_block_sign_up_and_sign_in_or_retry_heals_it(
    client, db_session, admin_headers, monkeypatch
):
    fake = FakeKeycloak().install(monkeypatch)
    fake.fail = True
    user = _signup(client, db_session)
    assert db_session.query(ParticipantIamUser).count() == 0  # nothing attempted at sign-up
    _decide(client, admin_headers, user)

    row = db_session.query(ParticipantIamUser).one()
    assert row.status == "FAILED" and "Keycloak" in row.error
    _login(client)  # still FAILED: Keycloak is down, sign-in works anyway

    fake.fail = False
    retried = client.post(f"/oan/admin/participants/{user.participant_id}/iam-account/retry", headers=admin_headers)
    assert retried.status_code == 200, retried.text
    account = retried.json()["data"]["account"]
    assert account["status"] == "ACTIVE" and account["roles"] == ["uat"] and account["error"] is None
    assert account["password_synced"] is False  # an admin retry has no password
    assert account["console_url"].endswith(f"/admin/master/console/#/oan-partners/users/{account['keycloak_id']}/settings")
    assert fake.only["password"] is None

    _login(client)  # the next portal sign-in hands Keycloak the password
    assert fake.only["password"] == SIGNUP["password"]
    db_session.expire_all()
    assert db_session.query(ParticipantIamUser).one().password_synced_at is not None


def test_email_verification_gives_no_role_until_uat_is_approved(
    client, db_session, admin_headers, monkeypatch
):
    fake = FakeKeycloak().install(monkeypatch)
    monkeypatch.setattr(settings, "MAIL_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr("app.services.notification_service.send_email", lambda *a, **k: True)
    user = _signup(client, db_session)
    assert fake.users == {}

    verified = client.post("/oan/participant/auth/verify-email",
                           json={"unique_id": str(user.unique_id), "otp": user.otp})
    assert verified.status_code == 200, verified.text
    assert fake.users == {}  # verified, but still waiting for the administrator

    _decide(client, admin_headers, user)
    assert fake.only["roles"] == {"uat"} and fake.only["enabled"] is True
    assert fake.only["email_verified"] is True


@pytest.mark.parametrize("missing", ["KEYCLOAK_PARTNER_CLIENT_ID", "KEYCLOAK_ADMIN_CLIENT_SECRET"])
def test_provisioning_needs_the_shared_client_and_the_service_account(monkeypatch, missing):
    FakeKeycloak().install(monkeypatch)
    assert keycloak.is_configured()
    monkeypatch.setattr(settings, missing, "")
    assert not keycloak.is_configured()


def test_a_template_missing_from_the_database_falls_back_to_the_built_in_text(db_session, monkeypatch):
    from app.models.content import EmailTemplate
    from app.services import notification_service

    sent = []
    monkeypatch.setattr(notification_service, "send_email", lambda to, subject, body: sent.append((subject, body)) or True)
    db_session.query(EmailTemplate).filter_by(template_code="PROMOTION_APPROVED").delete()
    db_session.commit()
    assert notification_service.send_templated(
        db_session, "PROMOTION_APPROVED", "p@example.org", {"name": "P", "environment": "UAT"}
    )
    [(subject, body)] = sent
    assert subject == "UAT access approved"
    assert "Dear P" in body



def test_participants_have_no_api_login_endpoint(client, participant_headers):
    """Removed 27 Oct 2026: the gateway does not accept Keycloak tokens yet."""
    assert client.get("/oan/participant/iam-account", headers=participant_headers).status_code == 404
