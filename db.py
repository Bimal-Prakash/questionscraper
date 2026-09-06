"""SQLAlchemy engine, session factory and schema bootstrap.

Synchronous on purpose. The scraper is a plain background thread using
`httpx.Client`, and the API's own handlers are declared `def`, so FastAPI runs
them in its threadpool - a sync engine is the shape that already fits, and it
avoids running two engines (one per concurrency model) against a free-tier
Postgres that caps connections low.
"""

from __future__ import annotations

import logging

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

from config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


_engine_options: dict = {}
if settings.is_pooled_postgres:
    # PgBouncer already pools server-side; a second pool in front of it just
    # holds connections open against the free tier's cap for no gain.
    _engine_options = {"poolclass": NullPool}
elif settings.is_postgres:
    # Neon suspends an idle compute and drops the TCP connection with it.
    # Pre-ping plus a short recycle means the next request reconnects instead
    # of raising. The pool stays small: the free tier caps total connections,
    # and the API threadpool and the extractor thread both draw from it.
    _engine_options = {"pool_recycle": 280, "pool_size": 5, "max_overflow": 5}

engine = create_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    future=True,
    connect_args=settings.db_connect_args,
    **_engine_options,
)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


if settings.is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record) -> None:
        cursor = dbapi_connection.cursor()
        # WAL lets the API keep reading while the extractor writes.
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


def _sync_added_columns(connection) -> None:
    """Add columns and indexes the models declare but an existing table lacks.

    `create_all` only creates whole tables, so a database written by an earlier
    version keeps its old column set forever and every query naming a new
    column fails. No migration tool here on purpose: every schema change so far
    is additive, and additive changes are plain `ALTER TABLE ADD COLUMN`, which
    SQLite and Postgres spell identically. A destructive change is the point at
    which this stops being enough and Alembic earns its keep.
    """
    from sqlalchemy import inspect
    from sqlalchemy.schema import CreateIndex

    inspector = inspect(connection)
    existing_tables = set(inspector.get_table_names())
    quote = connection.dialect.identifier_preparer.quote

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # create_all just made it, in full

        present = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present:
                continue
            # Added nullable regardless of what the model says: existing rows
            # have no value to put there and every backend rejects a NOT NULL
            # column added to a non-empty table.
            connection.exec_driver_sql(
                f"ALTER TABLE {quote(table.name)} ADD COLUMN "
                f"{quote(column.name)} {column.type.compile(connection.dialect)}"
            )
            logger.info("Added column %s.%s", table.name, column.name)

        present_indexes = {idx["name"] for idx in inspector.get_indexes(table.name)}
        for index in table.indexes:
            if index.name in present_indexes:
                continue
            connection.execute(CreateIndex(index, if_not_exists=True))
            logger.info("Created index %s", index.name)


def init_db() -> None:
    """Create tables if absent, and add any columns they are missing."""
    import db_models  # noqa: F401  - register mappers

    with engine.begin() as conn:
        Base.metadata.create_all(conn)
        _sync_added_columns(conn)
    logger.info("Database ready (%s)", describe_database())


def dispose_db() -> None:
    engine.dispose()


def healthcheck() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.exception("Database healthcheck failed")
        return False


def describe_database() -> str:
    """Backend and host, never the password - this ends up in /health."""
    url = engine.url
    if url.get_backend_name() == "sqlite":
        return f"sqlite:{url.database}"
    return f"{url.get_backend_name()}://{url.host}/{url.database}"
