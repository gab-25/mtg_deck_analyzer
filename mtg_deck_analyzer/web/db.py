"""Database engine, session factory and declarative base.

The connection string comes from the ``DATABASE_URL`` environment variable.
It defaults to a local Postgres instance (matching ``docker-compose.yml``); set
``DATABASE_URL`` to e.g. ``sqlite+pysqlite:///./mtg.db`` for a dependency-free
local run or for tests.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DEFAULT_DATABASE_URL = "postgresql+psycopg://mtg:mtg@localhost:5432/mtg"


def get_database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal = None


def get_engine():
    """Lazily builds the SQLAlchemy engine so importing the app needs no DB."""
    global _engine, _SessionLocal
    if _engine is None:
        url = get_database_url()
        connect_args = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        _engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
        _SessionLocal = sessionmaker(
            bind=_engine, autoflush=False, expire_on_commit=False
        )
    return _engine


def init_db() -> None:
    """Creates all tables (idempotent)."""
    # Import models so they register on the metadata before create_all.
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())


def get_session():
    """FastAPI dependency that yields a session and always closes it."""
    if _SessionLocal is None:
        get_engine()
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()
