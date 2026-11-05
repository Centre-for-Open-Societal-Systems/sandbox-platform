"""Regression tests for the 27 Oct 2026 security audit.

Each test pins one finding: if it fails, the hole is open again.
"""

from __future__ import annotations

import pytest

from app.config.settings import Settings, settings
from app.core.exceptions import ValidationError
from app.core.pagination import apply_sort
from app.core.permissions import Permission
from app.core.security import hash_password
from app.models.admin import AdmRole, AdmUser
from app.models.participant import Participant
from app.repositories.admin_repository import PermissionRepository
from app.services import sandbox_service
from app.utils import exporters
from app.utils.common import render_template
from app.utils.files import _assert_content_matches
from tests.conftest import ADMIN_PASSWORD, PARTICIPANT_PASSWORD
from tests.test_apps import (  # noqa: F401
    FakeGateway,
    _api_product,
    _create_app,
    _routes,
    farmer_endpoints,
)

LIMITED_PASSWORD = "Limit3d#Admin"


def _limited_admin(db, client, permissions, email="limited@example.org", country="ET"):
    """An enabled, non-master administrator whose role holds only ``permissions``."""
    PermissionRepository(db).sync_catalogue()
    role = AdmRole(role_name=f"Role {email}", is_editable=True)
    db.add(role)
    db.commit()
    PermissionRepository(db).replace_role_permissions(role.role_id, [int(p) for p in permissions])
    user = AdmUser(
        first_name="Limited", email_id=email, login_name=email.split("@")[0],
        login_pass=hash_password(LIMITED_PASSWORD), is_master=False, is_enabled=True,
        is_activated=True, role_id=role.role_id, country_code=country,
    )
    db.add(user)
    db.commit()
    login = client.post("/oan/admin/auth/login", json={"username": email, "password": LIMITED_PASSWORD})
    assert login.status_code == 200, login.text
    data = login.json()["data"]
    return user, {"x-access-token": data["access_token"], "x-auth-key": data["auth_key"]}


# ------------------------------------------------------- C1: fixed reset code
@pytest.mark.parametrize("env", ["sandbox", "uat", "production"])
def test_fixed_code_is_off_on_every_shared_environment(env):
    assert Settings(ENV=env, MAIL_ENABLED=False, DEV_FIXED_OTP="000000").fixed_otp is None


def test_weak_signing_keys_refuse_to_start_a_shared_server():
    shared = {"ENV": "sandbox", "DATABASE_URL_OVERRIDE": "postgresql+psycopg://u:p@db/x"}
    with pytest.raises(ValueError):
        Settings(**shared, JWT_ACCESS_TOKEN_KEY="", JWT_REFRESH_TOKEN_KEY="x" * 40)
    with pytest.raises(ValueError):
        Settings(**shared, JWT_ACCESS_TOKEN_KEY="change-me-access-secret", JWT_REFRESH_TOKEN_KEY="x" * 40)
    with pytest.raises(ValueError):
        Settings(**shared, JWT_ACCESS_TOKEN_KEY="y" * 40, JWT_REFRESH_TOKEN_KEY="y" * 40)
    Settings(**shared, JWT_ACCESS_TOKEN_KEY="a" * 40, JWT_REFRESH_TOKEN_KEY="b" * 40)


# --------------------------------------------- H1/H2: admin privilege escalation
def test_view_only_admin_cannot_change_any_account(client, db_session, master_admin):
    _, headers = _limited_admin(db_session, client, [Permission.AUM_VIEW_USER_LIST])
    assert client.post("/oan/admin/users/list", headers=headers, json={}).status_code == 200

    takeover = client.put("/oan/admin/users", headers=headers,
                          json={"admin_id": master_admin.admin_id, "password": "Taken#Over1"})
    assert takeover.status_code == 403
    created = client.post("/oan/admin/users", headers=headers, json={
        "first_name": "X", "email_id": "x@example.org", "login_name": "xadmin", "role_id": master_admin.role_id})
    assert created.status_code == 403
    login = client.post("/oan/admin/auth/login", json={"username": master_admin.email_id, "password": "Taken#Over1"})
    assert login.status_code == 401


def test_user_manager_cannot_touch_the_master_or_hand_out_a_stronger_role(client, db_session, master_admin):
    me, headers = _limited_admin(
        db_session, client, [Permission.AUM_VIEW_USER_LIST, Permission.AUM_ADD_NEW_USER])

    master = client.put("/oan/admin/users", headers=headers,
                        json={"admin_id": master_admin.admin_id, "password": "Taken#Over1"})
    assert master.status_code == 403
    # The Super Administrator role, or making themselves stronger.
    stronger = client.post("/oan/admin/users", headers=headers, json={
        "first_name": "X", "email_id": "x@example.org", "login_name": "xadmin", "role_id": master_admin.role_id})
    assert stronger.status_code == 403
    own_role = client.put("/oan/admin/users", headers=headers,
                          json={"admin_id": me.admin_id, "role_id": master_admin.role_id})
    assert own_role.status_code == 403
    # A role within their own permissions is fine.
    same = client.post("/oan/admin/users", headers=headers, json={
        "first_name": "Y", "email_id": "y@example.org", "login_name": "yadmin", "role_id": me.role_id})
    assert same.status_code == 200, same.text


def test_role_manager_cannot_grant_permissions_they_do_not_hold(client, db_session, master_admin):
    me, headers = _limited_admin(
        db_session, client, [Permission.ADMIN_USER_MANAGEMENT, Permission.AUM_MANAGE_ROLES])
    everything = [{"id": int(p), "status": True} for p in Permission]

    own = client.put("/oan/admin/permissions", headers=headers,
                     json={"role_id": me.role_id, "permissions": everything})
    assert own.status_code == 403
    new_role = client.post("/oan/admin/roles", headers=headers, json={
        "role_name": "Escalated", "permission_ids": [int(Permission.ALL_PARTICIPANTS)]})
    assert new_role.status_code == 403
    allowed = client.post("/oan/admin/roles", headers=headers, json={
        "role_name": "Helper", "permission_ids": [int(Permission.AUM_MANAGE_ROLES)]})
    assert allowed.status_code in (200, 201), allowed.text


# ------------------------------------------------------ M2: token / session binding
def test_tokens_only_work_with_their_own_session_and_audience(
    client, admin_headers, participant_headers
):
    # A participant's JWT with an administrator's session key.
    mixed = {"x-access-token": participant_headers["x-access-token"], "x-auth-key": admin_headers["x-auth-key"]}
    assert client.post("/oan/admin/users/list", headers=mixed, json={}).status_code == 401
    # An administrator's JWT on a participant route.
    mixed = {"x-access-token": admin_headers["x-access-token"], "x-auth-key": participant_headers["x-auth-key"]}
    assert client.get("/oan/participant/apps", headers=mixed).status_code == 401


def test_idle_sessions_expire(client, participant_headers, monkeypatch):
    assert client.get("/oan/participant/apps", headers=participant_headers).status_code == 200
    monkeypatch.setattr(settings, "SESSION_IDLE_TIMEOUT_SECONDS", -1)
    assert client.get("/oan/participant/apps", headers=participant_headers).status_code == 401
    monkeypatch.setattr(settings, "SESSION_IDLE_TIMEOUT_SECONDS", 3600)
    # Ended for good, not just while the limit is low.
    assert client.get("/oan/participant/apps", headers=participant_headers).status_code == 401


# ---------------------------------------------------------- M4: brute force
def test_repeated_wrong_passwords_lock_the_account(client, master_admin):
    for _ in range(settings.LOGIN_MAX_FAILURES):
        wrong = client.post("/oan/admin/auth/login", json={"username": master_admin.email_id, "password": "nope"})
        assert wrong.status_code == 401
    right = client.post("/oan/admin/auth/login",
                        json={"username": master_admin.email_id, "password": ADMIN_PASSWORD})
    assert right.status_code == 429


def test_verification_code_dies_after_too_many_guesses(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "MAIL_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr("app.services.participant_auth_service.send_otp", lambda *a, **k: True)
    data = client.post("/oan/participant/auth/signup", json={
        "first_name": "Otp", "last_name": "Guess", "email_id": "otp.guess@example.org",
        "mobile_number": "+251911000999", "company_name": "Guess Ltd", "category_id": 1,
        "password": "Guess#Pass2026", "country_code": "ET", "declaration": True}).json()["data"]
    user = db_session.query(Participant).filter_by(email_id="otp.guess@example.org").one()
    real_code = user.otp
    wrong = "000001" if real_code != "000001" else "000002"
    for _ in range(settings.OTP_MAX_ATTEMPTS):
        client.post("/oan/participant/auth/verify-email", json={"unique_id": data["unique_id"], "otp": wrong})
    late = client.post("/oan/participant/auth/verify-email", json={"unique_id": data["unique_id"], "otp": real_code})
    assert late.status_code in (400, 429)
    db_session.refresh(user)
    assert user.is_email_verified is False


def test_password_reset_signs_out_other_sessions(client, participant_headers, verified_participant, mailbox):
    client.post("/oan/participant/auth/forgot-password", json={"email_id": verified_participant.email_id})
    reset = client.post("/oan/participant/auth/reset-password",
                        json={"token": mailbox[-1]["values"]["token"], "new_password": "Brand#New2026"})
    assert reset.status_code == 200, reset.text
    assert client.get("/oan/participant/apps", headers=participant_headers).status_code == 401


# --------------------------------- H3/M3: account state reaches sessions and keys
def test_disabled_participant_loses_gateway_keys_and_gets_them_back(
    client, admin_headers, participant_headers, verified_participant, farmer_endpoints, monkeypatch  # noqa: F811
):
    fake = FakeGateway(_routes()).install(monkeypatch)
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    _create_app(client, participant_headers, "Keys", [read], admin_headers)
    assert len(fake.consumers) == 1

    pid = verified_participant.participant_id
    off = client.post("/oan/admin/participants/toggle", headers=admin_headers, json={"id": pid, "is_enabled": False})
    assert off.status_code == 200, off.text
    assert fake.consumers == {}
    client.post("/oan/admin/participants/toggle", headers=admin_headers, json={"id": pid, "is_enabled": True})
    assert len(fake.consumers) == 1

    client.delete(f"/oan/admin/participants/{pid}", headers=admin_headers)
    assert fake.consumers == {}


def test_rejected_participant_is_signed_out_and_keys_removed(
    client, admin_headers, participant_headers, verified_participant, farmer_endpoints, monkeypatch  # noqa: F811
):
    fake = FakeGateway(_routes()).install(monkeypatch)
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    _create_app(client, participant_headers, "Keys", [read], admin_headers)
    rejected = client.post("/oan/admin/participants/reject", headers=admin_headers, json={
        "participant_id": verified_participant.participant_id, "environment": "UAT",
        "rejection_reason": "Audit test"})
    assert rejected.status_code == 200, rejected.text
    assert fake.consumers == {}
    assert client.get("/oan/participant/apps", headers=participant_headers).status_code == 401


# ------------------------------------------------------- M6: country scope
def test_country_admin_cannot_reach_another_countrys_participant(
    client, db_session, master_admin, verified_participant
):
    _, headers = _limited_admin(db_session, client, [Permission.PARTICIPANT_MANAGEMENT, Permission.ALL_PARTICIPANTS],
                                email="kenya@example.org", country="KE")
    pid = verified_participant.participant_id  # an ET participant
    assert client.get(f"/oan/admin/participants/{pid}", headers=headers).status_code == 404
    assert client.post("/oan/admin/participants/toggle", headers=headers,
                       json={"id": pid, "is_enabled": False}).status_code == 404
    listed = client.post("/oan/admin/participants/list", headers=headers, json={}).json()["data"]
    assert all(p["participant_id"] != pid for p in listed["participants"])


# ------------------------------------------------- M1: private file prefix bypass
@pytest.mark.parametrize("path", [
    "./participants/id-proof/abc_proof.pdf",
    "Participants/id-proof/abc_proof.pdf",
    "x/../participants/id-proof/abc_proof.pdf",
    "products/../participants/id-proof/abc_proof.pdf",
    "participants\\id-proof\\abc_proof.pdf",
])
def test_private_documents_cannot_be_reached_by_another_spelling(client, tmp_path, monkeypatch, path):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    target = tmp_path / "participants" / "id-proof" / "abc_proof.pdf"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"%PDF-1.4 secret")
    response = client.get(f"/oan/files/{path}")
    assert response.status_code in (400, 401, 404)
    assert b"secret" not in response.content


def test_owner_still_downloads_their_document(client, db_session, tmp_path, monkeypatch,
                                              verified_participant, participant_headers):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    target = tmp_path / "participants" / "id-proof" / "abc_proof.pdf"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"%PDF-1.4 mine")
    verified_participant.id_proof = "participants/id-proof/abc_proof.pdf"
    db_session.commit()
    assert client.get("/oan/files/participants/id-proof/abc_proof.pdf").status_code == 401
    mine = client.get("/oan/files/participants/id-proof/abc_proof.pdf", headers=participant_headers)
    assert mine.status_code == 200 and mine.content == b"%PDF-1.4 mine"


# --------------------------------------------------- H4/M8/M10: try-it proxy
def test_path_parameters_cannot_leave_the_route():
    path = sandbox_service._substitute_path_params("/v1/items/{id}", {"id": "../../apisix/admin?x=1#f"})
    assert path == "/v1/items/..%2F..%2Fapisix%2Fadmin%3Fx%3D1%23f"


@pytest.mark.parametrize("url", [
    "http://gw.test:9080/other/admin",       # outside the base path
    "http://evil.test/base/x",               # another host
    "http://169.254.169.254/base/latest",    # metadata address (same origin check first)
    "file:///etc/passwd",
])
def test_try_it_target_must_stay_on_its_upstream(url):
    with pytest.raises(ValidationError):
        sandbox_service._assert_safe_target(url, "http://gw.test:9080/base")


def test_try_it_never_calls_admin_apis(monkeypatch):
    monkeypatch.setattr(settings, "GATEWAY_ADMIN_URL", "http://gw.test:9180")
    with pytest.raises(ValidationError):
        sandbox_service._assert_safe_target("http://gw.test:9180/apisix/admin/routes", "http://gw.test:9180")
    with pytest.raises(ValidationError):
        sandbox_service._assert_safe_target("http://169.254.169.254/x", "http://169.254.169.254")
    sandbox_service._assert_safe_target("http://gw.test:9080/base/v1/x", "http://gw.test:9080/base")


def test_identity_and_hop_by_hop_headers_are_not_forwarded(verified_participant):
    sent = sandbox_service._build_headers({
        "X-Entity-Id": "victim", "x-forwarded-for": "1.2.3.4", "X-Real-IP": "1.2.3.4",
        "X-Consumer-Username": "admin", "Transfer-Encoding": "chunked", "Connection": "close",
        "X-Custom": "kept", "X-Bad": "a\r\nInjected: 1",
    }, verified_participant, sandbox_service.Environment.UAT)
    lowered = {k.lower() for k in sent}
    assert "x-custom" in lowered
    for blocked in ("x-entity-id", "x-forwarded-for", "x-real-ip", "x-consumer-username",
                    "transfer-encoding", "connection", "x-bad"):
        assert blocked not in lowered


def test_api_history_never_stores_credentials():
    body = sandbox_service._loggable({
        "username": "u", "password": "p", "client_secret": "s",
        "nested": [{"access_token": "t", "refresh_token": "r", "otp": "123456", "name": "kept"}],
    })
    assert body["password"] == body["client_secret"] == "***"
    assert body["nested"][0]["access_token"] == body["nested"][0]["otp"] == "***"
    assert body["nested"][0]["name"] == "kept" and body["username"] == "u"
    assert sandbox_service._redact_headers({"X-Client-Secret": "s", "X-Signature": "g", "Accept": "a"}) == {
        "X-Client-Secret": "***", "X-Signature": "***", "Accept": "a"}
    assert "abc" not in sandbox_service._redact_url("http://gw/x?apikey=abc&q=1")
    big = sandbox_service._loggable({"data": "x" * 20000})
    assert big["truncated"] is True


# ---------------------------------------------------- M9 / L3 / L5 / L7 helpers
def test_exports_neutralise_formulas():
    content, _, _ = exporters.export(
        [{"name": "=HYPERLINK(\"http://evil\",\"x\")"}], [("name", "Name")], "csv")
    assert b"'=HYPERLINK" in content


def test_lists_cannot_be_sorted_by_secrets():
    from sqlalchemy import select
    stmt = apply_sort(select(Participant), Participant, "user_pass", "asc", "participant_id")
    assert "user_pass" not in str(stmt).split("ORDER BY")[1]


def test_mail_values_are_html_escaped():
    out = render_template("<p>Hi {{name}}</p>", {"name": "<a href='http://evil'>x</a>"}, escape_html=True)
    assert "<a " not in out and "&lt;a" in out


def test_uploads_must_match_their_extension():
    with pytest.raises(ValidationError):
        _assert_content_matches("pdf", b"<html><script>alert(1)</script>")
    _assert_content_matches("pdf", b"%PDF-1.7 ...")


def test_participant_login_password_kept_out_of_test_noise():
    # Guard for the conftest constants used above.
    assert PARTICIPANT_PASSWORD and ADMIN_PASSWORD
