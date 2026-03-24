"""
database.py — SQLAlchemy engine & session factory.

Supports both SQLite (development) and PostgreSQL (production).
Switch via the DATABASE_URL environment variable in config.py.
"""

import logging
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, declarative_base

from config import DATABASE_URL

logger = logging.getLogger(__name__)

# ── Engine ────────────────────────────────────────────────────────────────────

_is_sqlite = DATABASE_URL.startswith("sqlite")

connect_args = {"check_same_thread": False} if _is_sqlite else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    # Pool settings for PostgreSQL concurrency
    pool_pre_ping=True,        # verify connections before use
    echo=False,
)

# SQLite-specific pragmas (WAL mode + foreign keys)
if _is_sqlite:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

logger.info("Database: %s", DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL)

# ── Session factory ───────────────────────────────────────────────────────────

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency: yields a DB session with automatic cleanup."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
