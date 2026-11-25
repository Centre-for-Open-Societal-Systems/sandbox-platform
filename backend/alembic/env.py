"""Alembic environment.

Target metadata comes from the application models, and the connection URL from
application settings, so migrations always match the running configuration.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.types import JSON

from app.config.settings import settings
from app.core.database import Base
from app.models.base import GUID

# Importing the package registers every table on Base.metadata.
import app.models  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def render_item(obj_type, obj, autogen_context):
    """Emit the project's custom column types with a matching import.

    Without this, autogenerate inlines the dialect variants and produces
    migrations that reference names it never imports.
    """
    if obj_type != "type":
        return False
    if isinstance(obj, GUID):
        autogen_context.imports.add("from app.models.base import GUID")
        return "GUID()"
    if isinstance(obj, JSON):
        autogen_context.imports.add("from app.models.base import JSONB")
        return "JSONB"
    return False


def run_migrations_offline() -> None:
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        render_item=render_item,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            render_item=render_item,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
