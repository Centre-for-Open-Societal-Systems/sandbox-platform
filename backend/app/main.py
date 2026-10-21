"""FastAPI application entrypoint."""

from __future__ import annotations

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
    yield
    logger.info("Shutting down %s", settings.APP_NAME)


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
