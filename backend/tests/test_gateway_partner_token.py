"""Gateway partner tokens (GATEWAY_PARTNER_AUTH=keycloak): the API gateway identifies the
caller by its Keycloak access token in X-Partner-Token; try-it sends the signed-in
participant's own Keycloak token there, never a value typed into the form."""

from __future__ import annotations

import pytest

from app.config.settings import settings
from tests import test_keycloak_login
from tests.test_keycloak_login import _headers, _login
from tests.test_sandbox_tryit import (
    _flag_product,
    _gateway,
    _import_and_publish,
    _product_of,
)

HEADER = "X-Partner-Token"
# The fake Keycloak realm and a participant signed up in it.
realm = test_keycloak_login.realm
approved = test_keycloak_login.approved


@pytest.fixture
def farmer_endpoint(client, admin_headers) -> int:
    ids = _import_and_publish(client, admin_headers)
    endpoint_id = ids["/farmers/{farmerId}"]
    _flag_product(client, admin_headers, _product_of(client, admin_headers, endpoint_id)["product_id"])
    return endpoint_id


def _try_it(client, auth, endpoint_id, **payload):
    response = client.post("/oan/participant/try-it", headers=auth,
                           json={"endpoint_id": endpoint_id, "path_params": {"farmerId": "F-1"}, **payload})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_try_it_sends_the_participants_keycloak_token(client, realm, approved, farmer_endpoint, monkeypatch):
    monkeypatch.setattr(settings, "GATEWAY_PARTNER_AUTH", "keycloak")
    calls = _gateway(monkeypatch)
    data = _login(client).json()["data"]

    _try_it(client, _headers(data), farmer_endpoint,
            headers={"Authorization": "Bearer upstream", "x-partner-token": "typed-in"})

    sent = calls[0][2]
    assert sent[HEADER] == data["access_token"]
    assert [k for k in sent if k.lower() == HEADER.lower()] == [HEADER]  # the typed one is gone
    assert sent["Authorization"] == "Bearer upstream"  # the upstream's own credential stays
    history = client.post("/oan/participant/api-history", headers=_headers(data), json={}).json()["data"]["logs"]
    assert data["access_token"] not in str(history)


def test_api_key_mode_sends_no_partner_token(client, realm, approved, farmer_endpoint, monkeypatch):
    calls = _gateway(monkeypatch)
    data = _login(client).json()["data"]

    _try_it(client, _headers(data), farmer_endpoint)

    assert HEADER not in calls[0][2]


def test_code_sample_names_the_partner_token_header(client, realm, approved, farmer_endpoint, monkeypatch):
    monkeypatch.setattr(settings, "GATEWAY_PARTNER_AUTH", "keycloak")
    _gateway(monkeypatch)
    data = _login(client).json()["data"]

    sample = client.post("/oan/participant/code-sample", headers=_headers(data),
                         json={"endpoint_id": farmer_endpoint, "language": "curl", "environment": "UAT"})

    code = sample.json()["data"]["code"]
    assert f"{HEADER}: <partner access token>" in code
    assert data["access_token"] not in code


def test_partner_tokens_need_keycloak_sign_in():
    with pytest.raises(ValueError, match="GATEWAY_PARTNER_AUTH=keycloak needs PARTICIPANT_AUTH_PROVIDER"):
        type(settings)(GATEWAY_PARTNER_AUTH="keycloak", PARTICIPANT_AUTH_PROVIDER="local")
