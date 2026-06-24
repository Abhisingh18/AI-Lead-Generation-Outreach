"""SQLAlchemy engine, session factory, and base class."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

def _normalize_db_url(url: str) -> str:
    """Render/Heroku give 'postgres://...'; SQLAlchemy needs the psycopg2 dialect."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


DATABASE_URL = _normalize_db_url(settings.database_url)
_is_sqlite = DATABASE_URL.startswith("sqlite")

# SQLite needs check_same_thread=False so FastAPI's threadpool can share the conn.
_connect_args = {"check_same_thread": False} if _is_sqlite else {}

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,   # recycle dead connections automatically
    connect_args=_connect_args,
    future=True,
)

if _is_sqlite:
    # WAL mode lets the dashboard READ leads while the pipeline is WRITING them,
    # so progress shows live instead of the DB locking during a long scrape.
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=15000")  # wait on locks instead of erroring
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a DB session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. Fine for MVP; switch to Alembic migrations later."""
    from app import models  # noqa: F401  (ensure models are imported/registered)

    Base.metadata.create_all(bind=engine)
