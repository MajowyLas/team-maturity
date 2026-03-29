"""Shared fixtures for regression tests.

Uses an in-memory SQLite database so that tests never touch the real maturity.db.
Each test function gets a fresh, empty database via the ``db`` fixture.
The ``client`` fixture wires FastAPI's ``get_db`` dependency to the same session.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.main import app
from app.models import (
    AssessmentRound,
    Base,
    Question,
    Response,
    ResponseAnswer,
    Team,
)

# ---------------------------------------------------------------------------
# In-memory engine & session factory
# StaticPool ensures all connections share the SAME in-memory database.
# Without it, each SQLAlchemy connection gets its own empty `:memory:` DB.
# ---------------------------------------------------------------------------

_ENGINE = create_engine(
    "sqlite:///:memory:",
    echo=False,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = sessionmaker(bind=_ENGINE, class_=Session)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db():
    """Yield a fresh database session with all tables created.

    Rolls back after the test so each test is fully isolated.
    """
    Base.metadata.create_all(bind=_ENGINE)
    session = _TestSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_ENGINE)


@pytest.fixture()
def client(db):
    """FastAPI TestClient with ``get_db`` overridden to use the test session."""
    from httpx import ASGITransport, AsyncClient
    from starlette.testclient import TestClient

    def _override():
        try:
            yield db
        finally:
            pass  # session closed by the ``db`` fixture

    app.dependency_overrides[get_db] = _override

    # Patch Jinja2 globals: _get_nav_teams() normally uses SessionLocal
    # which hits the real DB. Replace it with a version using the test session.
    from app.main import _all_templates
    from app.models import Team

    def _test_get_nav_teams():
        return db.query(Team).order_by(Team.name).all()

    for tpl in _all_templates:
        tpl.env.globals["auth_enabled"] = False
        tpl.env.globals["get_nav_teams"] = _test_get_nav_teams

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def make_team(db: Session, name: str = "Alpha", member_count: int = 5) -> Team:
    """Insert and return a Team."""
    team = Team(name=name, member_count=member_count)
    db.add(team)
    db.flush()
    return team


def make_round(db: Session, name: str = "Q1 2026", active: bool = True) -> AssessmentRound:
    """Insert and return an AssessmentRound."""
    rnd = AssessmentRound(name=name, is_active=active)
    db.add(rnd)
    db.flush()
    return rnd


def make_team_questions(db: Session, count: int = 4) -> list[Question]:
    """Insert *count* team-type questions across 2 categories / 2 subcategories."""
    questions = []
    cats = ["Culture", "Process"]
    subs = ["Collaboration", "Planning"]
    for i in range(count):
        q = Question(
            category=cats[i % 2],
            subcategory=subs[i % 2],
            statement=f"Team statement {i + 1}",
            display_order=i + 1,
            assessment_type="team",
        )
        db.add(q)
        questions.append(q)
    db.flush()
    return questions


def make_eng_questions(db: Session, count: int = 4) -> list[Question]:
    """Insert *count* engineering-type questions across 2 categories."""
    questions = []
    cats = ["Build & Deploy", "Test & Verification"]
    subs = ["CI/CD", "Automation"]
    for i in range(count):
        q = Question(
            category=cats[i % 2],
            subcategory=subs[i % 2],
            statement=f"Engineering area {i + 1}",
            display_order=i + 1,
            assessment_type="engineering",
            level_1=f"Base description {i + 1}",
            level_2=f"Beginner description {i + 1}",
            level_3=f"Intermediate description {i + 1}",
            level_4=f"Advanced description {i + 1}",
            level_5=f"Expert description {i + 1}",
        )
        db.add(q)
        questions.append(q)
    db.flush()
    return questions


def submit_team_response(
    db: Session,
    team: Team,
    rnd: AssessmentRound,
    questions: list[Question],
    scores: list[int],
    respondent: str = "Tester",
) -> Response:
    """Create a team survey response with the given scores."""
    resp = Response(
        round_id=rnd.id,
        team_id=team.id,
        respondent_name=respondent,
        assessment_type="team",
    )
    db.add(resp)
    db.flush()
    for q, score in zip(questions, scores):
        db.add(ResponseAnswer(response_id=resp.id, question_id=q.id, score=score))
    db.flush()
    return resp


def submit_eng_response(
    db: Session,
    rnd: AssessmentRound,
    questions: list[Question],
    scores: list[int],
    respondent: str = "Engineer",
    team: Team | None = None,
) -> Response:
    """Create an engineering assessment response with the given scores."""
    resp = Response(
        round_id=rnd.id,
        team_id=team.id if team else None,
        respondent_name=respondent,
        assessment_type="engineering",
    )
    db.add(resp)
    db.flush()
    for q, score in zip(questions, scores):
        db.add(ResponseAnswer(response_id=resp.id, question_id=q.id, score=score))
    db.flush()
    return resp
