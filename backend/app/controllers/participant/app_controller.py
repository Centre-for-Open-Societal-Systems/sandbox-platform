"""My Apps: a participant's apps, their API products and keys.

==========================================  =====================================
``GET    /participant/api-products``        API products an app can ask for
``GET    /participant/apps``                the participant's apps
``POST   /participant/apps``                create; waits for an administrator (no key yet)
``GET    /participant/apps/{app_id}``       one app
``PUT    /participant/apps/{app_id}``       rename / describe
``DELETE /participant/apps/{app_id}``       delete (its keys stop working)
``POST   /participant/apps/{app_id}/products``                 request products
``DELETE /participant/apps/{app_id}/products/{product_id}``    withdraw one
``POST   /participant/apps/{app_id}/credentials``              new key + secret
``DELETE /participant/apps/{app_id}/credentials/{credential_id}``  revoke a key
``POST   /participant/apps/{app_id}/token``  the app's access token (OAuth client credentials)
``GET    /participant/gateway-auth``        how the gateway identifies callers (try-it page)
==========================================  =====================================

A new app has no credential until an administrator approves it (the whole
app, or one of its product requests); the first key + secret are issued
then and listed on the app for its owner. ``app_id`` and ``credential_id``
are the public unique ids, never the database keys.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.deps import CurrentParticipant, DbSession
from app.core.responses import ok
from app.core.status_codes import StatusCode
from app.schemas.app import AppCreate, AppProductsRequest, AppUpdate
from app.services import app_service

router = APIRouter(tags=["User / Apps"])


@router.get("/api-products")
def api_products(current: CurrentParticipant, db: DbSession):
    return ok("API products loaded.", app_service.available_products(db, current.participant))


@router.get("/gateway-auth")
def gateway_auth(current: CurrentParticipant):
    return ok("Gateway sign-in loaded.", app_service.gateway_auth())


@router.post("/apps/{app_id}/token")
def app_token(app_id: str, current: CurrentParticipant, db: DbSession):
    """Client credentials with the app's API key + secret (the secret never leaves the server)."""
    return ok("App token issued.", app_service.get_app_token(db, current.participant, app_id))


@router.get("/apps")
def list_apps(current: CurrentParticipant, db: DbSession):
    apps = app_service.list_apps(db, current.participant)
    return ok("Apps loaded.", [app.model_dump() for app in apps])


@router.post("/apps")
def create_app(payload: AppCreate, current: CurrentParticipant, db: DbSession):
    created = app_service.create_app(db, current, payload)
    return ok(
        "App submitted for approval. Your API key and secret are issued once an administrator approves it.",
        created.model_dump(),
        code=StatusCode.CREATED,
    )


@router.get("/apps/{app_id}")
def get_app(app_id: str, current: CurrentParticipant, db: DbSession):
    return ok("App loaded.", app_service.get_app(db, current.participant, app_id).model_dump())


@router.put("/apps/{app_id}")
def update_app(app_id: str, payload: AppUpdate, current: CurrentParticipant, db: DbSession):
    return ok("App updated.", app_service.update_app(db, current, app_id, payload).model_dump())


@router.delete("/apps/{app_id}")
def delete_app(app_id: str, current: CurrentParticipant, db: DbSession):
    app_service.delete_app(db, current, app_id)
    return ok("App deleted. Its keys no longer work.")


@router.post("/apps/{app_id}/products")
def add_products(app_id: str, payload: AppProductsRequest, current: CurrentParticipant, db: DbSession):
    app = app_service.add_products(db, current, app_id, payload.api_product_ids)
    return ok("API products requested.", app.model_dump())


@router.delete("/apps/{app_id}/products/{api_product_id}")
def remove_product(app_id: str, api_product_id: int, current: CurrentParticipant, db: DbSession):
    app = app_service.remove_product(db, current, app_id, api_product_id)
    return ok("API product removed from the app.", app.model_dump())


@router.post("/apps/{app_id}/credentials")
def issue_credential(app_id: str, current: CurrentParticipant, db: DbSession):
    credential = app_service.issue_credential(db, current, app_id)
    return ok("New key issued.", credential.model_dump(), code=StatusCode.CREATED)


@router.delete("/apps/{app_id}/credentials/{credential_id}")
def revoke_credential(app_id: str, credential_id: str, current: CurrentParticipant, db: DbSession):
    app = app_service.revoke_credential(db, current, app_id, credential_id)
    return ok("Key revoked.", app.model_dump())

