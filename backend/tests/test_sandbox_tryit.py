"""The try-it console's mock mode and partial updates of endpoints and samples."""

from __future__ import annotations

import json

from tests.test_catalog import OPENAPI_SPEC, _create_product


def _import_and_publish(client, admin_headers) -> dict[str, int]:
    product = _create_product(client, admin_headers)
    response = client.post(
        "/oan/admin/products/import-spec",
        headers=admin_headers,
        json={"product_id": product["product_id"], "spec_text": json.dumps(OPENAPI_SPEC)},
    )
    assert response.status_code == 200, response.text

    detail = client.get(
        f"/oan/admin/products/{product['product_id']}", headers=admin_headers
    ).json()["data"]
    ids = {e["endpoint_url"]: e["endpoint_id"] for e in detail["endpoints"]}
    for endpoint_id in ids.values():
        client.post(
            "/oan/admin/endpoints/publish",
            headers=admin_headers,
            json={"id": endpoint_id, "is_published": True},
        )
    client.post(
        "/oan/admin/products/publish",
        headers=admin_headers,
        json={"id": product["product_id"], "is_published": True},
    )
    return ids


def _try_it(client, participant_headers, endpoint_id, **payload):
    response = client.post(
        "/oan/participant/try-it",
        headers=participant_headers,
        json={"endpoint_id": endpoint_id, **payload},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_without_an_upstream_the_sandbox_answers_from_the_200_sample(
    client, admin_headers, participant_headers
):
    ids = _import_and_publish(client, admin_headers)

    result = _try_it(
        client,
        participant_headers,
        ids["/farmers/{farmerId}"],
        path_params={"farmerId": "F-1"},
    )

    assert result["status_code"] == 200
    assert result["body"] == {"farmerId": "string", "fullName": "string", "region": "string"}
    assert result["headers"]["x-sandbox-mock"] == "true"
    assert result["request_url"].startswith("mock:")


def test_mock_returns_401_when_a_required_path_parameter_is_missing(
    client, admin_headers, participant_headers
):
    ids = _import_and_publish(client, admin_headers)

    result = _try_it(client, participant_headers, ids["/farmers/{farmerId}"])

    assert result["status_code"] == 401
    assert "farmerId" in result["error"]


def test_mock_picks_the_sample_whose_request_matches_the_body(
    client, admin_headers, participant_headers
):
    ids = _import_and_publish(client, admin_headers)
    endpoint_id = ids["/farmers/search"]
    client.post(
        "/oan/admin/schemas",
        headers=admin_headers,
        json={
            "endpoint_id": endpoint_id,
            "status_code": "404",
            "req_json": {"region": "Nowhere"},
            "res_json": {"errors": [{"code": "NOT_FOUND"}]},
        },
    )

    result = _try_it(client, participant_headers, endpoint_id, body={"region": "Nowhere"})

    assert result["status_code"] == 404
    assert result["body"] == {"errors": [{"code": "NOT_FOUND"}]}


def test_partial_schema_update_keeps_the_fields_it_did_not_send(
    client, admin_headers, participant_headers
):
    ids = _import_and_publish(client, admin_headers)
    schemas = client.get(
        f"/oan/admin/endpoints/{ids['/farmers/{farmerId}']}/schemas", headers=admin_headers
    ).json()["data"]
    schema = schemas[0]

    response = client.put(
        "/oan/admin/schemas",
        headers=admin_headers,
        json={"schema_id": schema["schema_id"], "res_json": {"farmerId": "F-1"}},
    )

    assert response.status_code == 200, response.text
    updated = response.json()["data"]
    assert updated["res_json"] == {"farmerId": "F-1"}
    assert updated["res_schema"] == schema["res_schema"]
    assert updated["status_code"] == schema["status_code"]


def test_partial_endpoint_update_keeps_method_and_keywords(client, admin_headers):
    ids = _import_and_publish(client, admin_headers)
    endpoint_id = ids["/farmers/{farmerId}"]

    response = client.put(
        "/oan/admin/endpoints",
        headers=admin_headers,
        json={"endpoint_id": endpoint_id, "display_name": "Fetch farmer"},
    )

    assert response.status_code == 200, response.text
    detail = client.get(f"/oan/admin/endpoints/{endpoint_id}", headers=admin_headers).json()[
        "data"
    ]
    assert detail["display_name"] == "Fetch farmer"
    assert detail["method"] == "GET"


def test_api_history_is_filterable_and_scoped_to_the_caller(
    client, admin_headers, participant_headers, db_session
):
    from app.models.logs import ApiLog

    ids = _import_and_publish(client, admin_headers)
    _try_it(client, participant_headers, ids["/farmers/{farmerId}"], path_params={"farmerId": "F-1"})
    _try_it(client, participant_headers, ids["/farmers/{farmerId}"])  # 401: missing path param

    ok_calls = client.post(
        "/oan/participant/api-history", headers=participant_headers, json={"status_code": 200}
    ).json()["data"]
    assert [row["status_code"] for row in ok_calls["logs"]] == [200]

    # Someone else's call must neither be listed nor readable by id.
    other = ApiLog(transaction_id="TXN-OTHER", participant_id=999_999, status_code=200, method="GET")
    db_session.add(other)
    db_session.commit()

    everything = client.post(
        "/oan/participant/api-history",
        headers=participant_headers,
        json={"participant_id": 999_999},
    ).json()["data"]
    assert "TXN-OTHER" not in {row["transaction_id"] for row in everything["logs"]}
    assert len(everything["logs"]) == 2

    mine = everything["logs"][0]["id"]
    assert client.get(f"/oan/participant/api-history/{mine}", headers=participant_headers).status_code == 200
    assert client.get(f"/oan/participant/api-history/{other.id}", headers=participant_headers).status_code == 404



# ------------------------------------------------------------ api gateway
def _gateway(monkeypatch, sandbox_url="http://kong.test:8100"):
    from app.config.settings import settings
    from app.services import sandbox_service

    monkeypatch.setattr(settings, "GATEWAY_ENABLED", True)
    monkeypatch.setattr(settings, "GATEWAY_SANDBOX_URL", sandbox_url)
    calls = []

    def fake_call(method, url, headers, body):
        calls.append((method, url, headers))
        return 200, {"x-kong-proxy-latency": "1"}, {"ok": True}, None

    monkeypatch.setattr(sandbox_service, "_call_upstream", fake_call)
    return calls


def _flag_product(client, admin_headers, product_id):
    response = client.put(
        "/oan/admin/products",
        headers=admin_headers,
        json={"product_id": product_id, "is_gateway_published": True},
    )
    assert response.status_code == 200, response.text


def _product_of(client, admin_headers, endpoint_id):
    return client.get(f"/oan/admin/endpoints/{endpoint_id}", headers=admin_headers).json()["data"]


def test_gateway_product_endpoints_are_called_on_the_gateway(
    client, admin_headers, participant_headers, monkeypatch
):
    calls = _gateway(monkeypatch)
    ids = _import_and_publish(client, admin_headers)
    endpoint = _product_of(client, admin_headers, ids["/farmers/{farmerId}"])
    _flag_product(client, admin_headers, endpoint["product_id"])

    result = _try_it(
        client,
        participant_headers,
        ids["/farmers/{farmerId}"],
        path_params={"farmerId": "F-1"},
        headers={"Authorization": "Bearer t"},
    )

    assert result["request_url"] == "http://kong.test:8100/farmers/F-1"
    assert result["body"] == {"ok": True}
    assert calls[0][2]["Authorization"] == "Bearer t"
    detail = _product_of(client, admin_headers, ids["/farmers/{farmerId}"])
    assert detail["resolved_upstreams"]["SANDBOX"] == "http://kong.test:8100"


def test_endpoints_not_on_the_gateway_stay_in_mock_mode(
    client, admin_headers, participant_headers, monkeypatch
):
    calls = _gateway(monkeypatch)
    ids = _import_and_publish(client, admin_headers)

    result = _try_it(
        client, participant_headers, ids["/farmers/{farmerId}"], path_params={"farmerId": "F-1"}
    )

    assert calls == []
    assert result["request_url"].startswith("mock:")


def test_an_endpoint_url_overrides_the_gateway(
    client, admin_headers, participant_headers, monkeypatch
):
    calls = _gateway(monkeypatch)
    ids = _import_and_publish(client, admin_headers)
    endpoint_id = ids["/farmers/{farmerId}"]
    _flag_product(client, admin_headers, _product_of(client, admin_headers, endpoint_id)["product_id"])
    client.put(
        "/oan/admin/endpoints",
        headers=admin_headers,
        json={"endpoint_id": endpoint_id, "sandbox_api_url": "http://direct.test"},
    )

    _try_it(client, participant_headers, endpoint_id, path_params={"farmerId": "F-1"})

    assert calls[0][1] == "http://direct.test/farmers/F-1"


def test_gateway_disabled_falls_back_to_mock(
    client, admin_headers, participant_headers, monkeypatch
):
    from app.config.settings import settings

    calls = _gateway(monkeypatch)
    monkeypatch.setattr(settings, "GATEWAY_ENABLED", False)
    ids = _import_and_publish(client, admin_headers)
    endpoint_id = ids["/farmers/{farmerId}"]
    _flag_product(client, admin_headers, _product_of(client, admin_headers, endpoint_id)["product_id"])

    result = _try_it(client, participant_headers, endpoint_id, path_params={"farmerId": "F-1"})

    assert calls == []
    assert result["request_url"].startswith("mock:")


# ---------------------------------------------------------- catalogue menu
def test_catalog_menu_returns_every_product_with_endpoints_in_one_call(
    client, admin_headers, participant_headers
):
    ids = _import_and_publish(client, admin_headers)

    response = client.get("/oan/participant/catalog/menu", headers=participant_headers)

    assert response.status_code == 200
    menu = response.json()["data"]
    [product] = [p for p in menu if p["product_name"] == "Farmer Registry"]
    assert {e["endpoint_id"] for e in product["endpoints"]} == set(ids.values())
    assert set(product["endpoints"][0]) == {
        "endpoint_id", "display_name", "endpoint_url", "method", "api_type",
    }


def test_catalog_menu_revalidates_with_etag_and_sees_changes(
    client, admin_headers, participant_headers
):
    ids = _import_and_publish(client, admin_headers)
    first = client.get("/oan/participant/catalog/menu", headers=participant_headers)
    etag = first.headers["etag"]

    unchanged = client.get(
        "/oan/participant/catalog/menu",
        headers={**participant_headers, "If-None-Match": etag},
    )
    assert unchanged.status_code == 304
    assert unchanged.content == b""

    client.post(
        "/oan/admin/endpoints/publish",
        headers=admin_headers,
        json={"id": ids["/farmers/{farmerId}"], "is_published": False},
    )
    changed = client.get(
        "/oan/participant/catalog/menu",
        headers={**participant_headers, "If-None-Match": etag},
    )
    assert changed.status_code == 200
    endpoint_ids = {e["endpoint_id"] for p in changed.json()["data"] for e in p["endpoints"]}
    assert ids["/farmers/{farmerId}"] not in endpoint_ids


def test_portal_product_detail_omits_the_stored_spec(
    client, admin_headers, participant_headers
):
    ids = _import_and_publish(client, admin_headers)
    product_id = client.get(
        f"/oan/admin/endpoints/{ids['/farmers/{farmerId}']}", headers=admin_headers
    ).json()["data"]["product_id"]

    portal = client.get(f"/oan/participant/catalog/products/{product_id}", headers=participant_headers)
    admin = client.get(f"/oan/admin/products/{product_id}", headers=admin_headers)

    assert portal.json()["data"]["open_spec_json"] is None
    assert admin.json()["data"]["open_spec_json"]


def test_portal_endpoint_detail_includes_the_try_it_sample(
    client, admin_headers, participant_headers
):
    ids = _import_and_publish(client, admin_headers)
    endpoint_id = ids["/farmers/search"]

    detail = client.get(
        f"/oan/participant/catalog/endpoints/{endpoint_id}", headers=participant_headers
    ).json()["data"]
    sample = client.get(
        f"/oan/participant/catalog/endpoints/{endpoint_id}/sample", headers=participant_headers
    ).json()["data"]

    assert detail["sample"] == sample
