"""Database engine and session management for SQLite."""

import os
import secrets
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
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


def _run_migrations() -> None:
    """Lightweight schema migrations for SQLite (no Alembic).

    Checks for missing columns and adds them. Safe to run on every startup.
    """
    inspector = inspect(engine)

    # Migration: add engineering_token to assessment_rounds
    if "assessment_rounds" in inspector.get_table_names():
        columns = {col["name"] for col in inspector.get_columns("assessment_rounds")}
        if "engineering_token" not in columns:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE assessment_rounds "
                        "ADD COLUMN engineering_token VARCHAR(50)"
                    )
                )
                # Backfill existing rows with unique tokens
                rows = conn.execute(
                    text("SELECT id FROM assessment_rounds WHERE engineering_token IS NULL")
                ).fetchall()
                for row in rows:
                    token = secrets.token_urlsafe(8)
                    conn.execute(
                        text(
                            "UPDATE assessment_rounds SET engineering_token = :token WHERE id = :id"
                        ),
                        {"token": token, "id": row[0]},
                    )
            print("[MIGRATION] Added engineering_token column to assessment_rounds")


def init_db() -> None:
    """Create all tables if they don't exist yet, then run migrations."""
    Base.metadata.create_all(bind=engine)
    _run_migrations()


def get_db():
    """FastAPI dependency that yields a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
