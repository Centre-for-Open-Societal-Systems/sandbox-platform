"""API catalogue and the sandbox "try it" console for signed-in participants."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response

from app.core.deps import CountryCode, CurrentParticipant, DbSession
from app.core.exceptions import NotFoundError
from app.core.responses import ok
from app.models.enums import Environment
from app.schemas.catalog import (
    CodeSampleRequest,
    CurlConvertRequest,
    TryItRequest,
)
from app.schemas.content import ApiLogQuery
from app.services import catalog_service, log_service, sandbox_service

router = APIRouter(tags=["User / Sandbox"])



@router.get("/catalog/products")
def list_products(current: CurrentParticipant, db: DbSession, country: CountryCode):
    products = catalog_service.list_published_products(db, country)
    return ok("Catalogue loaded.", [product.model_dump() for product in products])


@router.get("/catalog/menu")
def catalog_menu(
    request: Request, current: CurrentParticipant, db: DbSession, country: CountryCode
):
    """All published products with their end-points, in one call.

    Sends an ETag; a client that already has this version gets ``304 Not
    Modified`` with no body.
    """
    menu, etag = catalog_service.catalog_menu(db, country)
    headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return ok("Catalogue menu loaded.", menu, headers=headers)


@router.get("/catalog/products/{product_id}")
def get_product(product_id: int, current: CurrentParticipant, db: DbSession):
    product = catalog_service.get_product(db, product_id, published_only=True)
    return ok("Product loaded.", product.model_dump())


@router.get("/catalog/endpoints/{endpoint_id}")
def get_endpoint(endpoint_id: int, current: CurrentParticipant, db: DbSession):
    """End-point documentation plus the try-it pre-fill (the 200 sample), so the
    documentation and test pages need one call instead of two."""
    endpoint = catalog_service.get_endpoint(db, endpoint_id, published_only=True)
    return ok(
        "Endpoint loaded.",
        {**endpoint.model_dump(), "sample": sandbox_service.sample_request(db, endpoint_id)},
    )


@router.get("/catalog/endpoints/{endpoint_id}/sample")
def endpoint_sample(
    endpoint_id: int,
    current: CurrentParticipant,
    db: DbSession,
    status_code: str = Query("200"),
):
    """Pre-filled request and expected response for the try-it console."""
    return ok(
        "Sample loaded.", sandbox_service.sample_request(db, endpoint_id, status_code)
    )


@router.post("/try-it")
def try_it(payload: TryItRequest, current: CurrentParticipant, db: DbSession):
    result = sandbox_service.execute(db, current.participant, payload)
    return ok("Request executed.", result.model_dump())


@router.post("/code-sample")
def code_sample(payload: CodeSampleRequest, current: CurrentParticipant, db: DbSession):
    sample = sandbox_service.code_sample(
        db, payload.endpoint_id, payload.language, payload.environment
    )
    return ok("Code sample generated.", sample)


@router.post("/curl-convert")
def curl_convert(payload: CurlConvertRequest, current: CurrentParticipant):
    return ok("Command converted.", sandbox_service.convert_curl(payload.curl_command))


@router.post("/api-history")
def api_history(
    payload: ApiLogQuery,
    current: CurrentParticipant,
    db: DbSession,
    environment: Environment | None = Query(None),
):
    """The participant's own call history - scoped to their records only.

    Accepts the same filters as the console's API history (method, status,
    product, end-point, date range); ``participant_id`` is always forced to
    the signed-in participant so one account can never read another's calls.
    """
    query = payload.model_copy(
        update={
            "participant_id": current.id,
            "environment": str(environment) if environment else payload.environment,
            "country_code": None,
        }
    )
    return ok(
        "API history loaded.", log_service.list_api_logs(db, query).as_dict("logs")
    )


@router.get("/api-history/{log_id}")
def api_history_detail(log_id: int, current: CurrentParticipant, db: DbSession):
    """Full request/response of one of the participant's own calls."""
    log = log_service.get_api_log(db, log_id)
    if log is None or log.participant_id != current.id:
        raise NotFoundError("Log entry not found.")
    return ok("Log entry loaded.", log.model_dump())
