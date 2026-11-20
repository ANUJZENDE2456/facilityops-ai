"""
SQLAlchemy engine, session factory, and session lifecycle dependencies.
"""

import logging
from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from app.config import settings

logger = logging.getLogger(__name__)


def resolve_database_url(url: str) -> str:
    """
    Resolves the database URL and driver compatibility.
    Falls back gracefully to psycopg2 if psycopg (v3) is requested but not yet installed.
    """
    if url.startswith("postgresql+psycopg://"):
        try:
            import psycopg  # noqa: F401
        except ImportError:
            try:
                import psycopg2  # noqa: F401
                logger.warning(
                    "psycopg (v3) not detected; falling back to psycopg2 driver."
                )
                return url.replace("postgresql+psycopg://", "postgresql+psycopg2://", 1)
            except ImportError:
                pass
    return url


# Resolve effective database URL
effective_db_url = resolve_database_url(settings.DATABASE_URL)

# Create SQLAlchemy engine with connection pooling, timeout, and pre-ping
engine = create_engine(
    effective_db_url,
    pool_pre_ping=settings.DB_POOL_PRE_PING,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    connect_args={"connect_timeout": 5},
)

# Session factory for transactional database sessions
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency yielding an isolated SQLAlchemy database session per request.
    Automatically closes the session after request completion.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection() -> dict:
    """
    Executes a test query (SELECT 1) to verify database connectivity.
    """
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1")).scalar()
        return {
            "status": "connected",
            "database": "PostgreSQL",
            "query": "SELECT 1",
            "result": result,
        }
