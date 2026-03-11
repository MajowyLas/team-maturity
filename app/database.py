"""Database engine and session management for SQLite."""

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base

# Allow override via DATABASE_PATH env var (for Render persistent disk).
# Default: maturity.db in project root (local development).
_default_db = Path(__file__).resolve().parent.parent / "maturity.db"
DB_PATH = Path(os.environ.get("DATABASE_PATH", str(_default_db)))

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    echo=False,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(bind=engine, class_=Session)


def init_db() -> None:
    """Create all tables if they don't exist yet."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency that yields a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
