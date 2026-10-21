"""SQLAlchemy engine, session factory and declarative base."""

from collections.abc import Iterator

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config.settings import settings

IN_MEMORY_SQLITE_URLS = {"sqlite://", "sqlite:///:memory:"}

# check_same_thread is a SQLite-only argument; Postgres rejects it.
_connect_args = {"check_same_thread": False} if settings.is_sqlite else {}

_engine_kwargs: dict = {
    "echo": settings.DB_ECHO,
    "pool_pre_ping": True,
    "connect_args": _connect_args,
}
if settings.is_sqlite:
    if settings.DATABASE_URL in IN_MEMORY_SQLITE_URLS:
        # Every new connection to an in-memory database gets its own empty
        # store, so a single shared connection is the only way the schema
        # survives between sessions.
        _engine_kwargs["poolclass"] = StaticPool
else:
    _engine_kwargs["pool_size"] = settings.DB_POOL_SIZE
    _engine_kwargs["max_overflow"] = settings.DB_MAX_OVERFLOW

engine = create_engine(settings.DATABASE_URL, **_engine_kwargs)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

# Explicit naming convention keeps Alembic autogenerate diffs stable.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


# Tables are left unqualified so the same models run on Postgres (resolved via
# the connection's search_path, `public` by default) and on SQLite in tests,
# which has no concept of schemas.
class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
