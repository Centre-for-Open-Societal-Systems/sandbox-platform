"""FastAPI application entrypoint."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import settings
from app.controllers import api_router
from app.core.database import SessionLocal
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import register_middleware
from app.core.responses import ok
from app.repositories.admin_repository import PermissionRepository

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    logger.info("Starting %s (%s)", settings.APP_NAME, settings.ENV)
    _sync_permission_catalogue()
    maintenance = (
        asyncio.create_task(_key_maintenance_loop()) if settings.APP_KEY_MAINTENANCE_MINUTES > 0 else None
    )
    yield
    if maintenance is not None:
        maintenance.cancel()
    logger.info("Shutting down %s", settings.APP_NAME)


def _run_key_maintenance() -> None:
    from app.services import app_service

    db = SessionLocal()
    try:
        result = app_service.run_key_maintenance(db)
        if result["expired"] or result["warned"]:
            logger.info("Key maintenance: %(expired)d expired, %(warned)d warned.", result)
        from app.services import log_service, support_service

        closed = support_service.close_stale_tickets(db)
        if closed:
            logger.info("Support: %d answered tickets closed after no reply.", closed)
        purged = log_service.purge_old_audit_logs(db)
        if purged:
            logger.info("Audit retention: %d old entries deleted.", purged)
    except Exception as exc:
        logger.error("Key maintenance failed: %s", exc)
        db.rollback()
    finally:
        db.close()


async def _key_maintenance_loop() -> None:
    """Expire old app keys and warn their owners, every APP_KEY_MAINTENANCE_MINUTES."""
    while True:
        await asyncio.to_thread(_run_key_maintenance)
        await asyncio.sleep(settings.APP_KEY_MAINTENANCE_MINUTES * 60)


def _sync_permission_catalogue() -> None:
    """Keep ``adm_permission`` aligned with the code-side permission tree.

    Adding a console screen then means adding one enum member, not writing a
    data migration. Failures are logged rather than fatal so the API still
    starts when the database is briefly unavailable.
    """
    db = SessionLocal()
    try:
        changed = PermissionRepository(db).sync_catalogue()
        if changed:
            logger.info("Synchronised %d permission entries.", changed)
    except Exception as exc:
        logger.error("Could not synchronise the permission catalogue: %s", exc)
        db.rollback()
    finally:
        db.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        description=settings.APP_DESCRIPTION,
        version=settings.APP_VERSION,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        openapi_url="/openapi.json" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "x-access-token",
            "x-auth-key",
            "x-country-code",
        ],
        expose_headers=["x-auth-key", "x-correlation-id", "Content-Disposition"],
    )
    register_middleware(app)
    register_exception_handlers(app)
    app.include_router(api_router)

    @app.get("/", tags=["Health"])
    def root():
        return ok(
            f"Welcome to {settings.APP_NAME}.",
            {
                "version": settings.APP_VERSION,
                "docs": "/docs",
                "api": settings.API_PREFIX,
            },
        )

    return app


app = create_app()
