"""Downloadable OpenAPI document of a published product."""

from __future__ import annotations

from app.config.settings import settings
from tests.test_catalog import _create_product
from tests.test_sandbox_tryit import _import_and_publish


def _product_id(client, admin_headers) -> int:
    _import_and_publish(client, admin_headers)
    rows = client.post("/oan/admin/products/list", headers=admin_headers, json={"page": 1, "limit": 10}).json()
    return rows["data"]["products"][0]["product_id"]


def test_participant_gets_an_openapi_document(client, admin_headers, participant_headers):
    pid = _product_id(client, admin_headers)

    response = client.get(f"/oan/participant/catalog/products/{pid}/openapi", headers=participant_headers)

    assert response.status_code == 200, response.text
    doc = response.json()["data"]
    assert doc["openapi"].startswith("3.0")
    assert doc["info"]["title"] == "Farmer Registry"
    assert set(doc["paths"]) == {"/farmers/{farmerId}", "/farmers/search"}
    get_op = doc["paths"]["/farmers/{farmerId}"]["get"]
    path_param = get_op["parameters"][0]
    assert (path_param["name"], path_param["in"], path_param["required"]) == ("farmerId", "path", True)
    assert "200" in get_op["responses"]
    assert "requestBody" in doc["paths"]["/farmers/search"]["post"]
    scheme = doc["components"]["securitySchemes"]["PartnerAuth"]
    assert scheme["name"] == settings.GATEWAY_APP_KEY_HEADER
    assert doc["security"] == [{"PartnerAuth": []}]


def test_production_export_needs_production_access(client, admin_headers, participant_headers):
    pid = _product_id(client, admin_headers)

    response = client.get(
        f"/oan/participant/catalog/products/{pid}/openapi",
        headers=participant_headers,
        params={"environment": "PRODUCTION"},
    )

    assert response.status_code == 403


def test_participant_export_requires_sign_in(client, admin_headers):
    pid = _product_id(client, admin_headers)

    assert client.get(f"/oan/participant/catalog/products/{pid}/openapi").status_code == 401


def test_public_export_of_a_published_product(client, admin_headers):
    pid = _product_id(client, admin_headers)

    openapi = client.get(f"/oan/catalog/products/{pid}/openapi")

    assert openapi.status_code == 200
    assert openapi.json()["data"]["info"]["title"] == "Farmer Registry"


def test_unpublished_product_cannot_be_exported(client, admin_headers, participant_headers):
    product = _create_product(client, admin_headers, "Draft Product")
    pid = product["product_id"]

    assert client.get(f"/oan/catalog/products/{pid}/openapi").status_code == 404
    assert (
        client.get(f"/oan/participant/catalog/products/{pid}/openapi", headers=participant_headers).status_code
        == 404
    )
