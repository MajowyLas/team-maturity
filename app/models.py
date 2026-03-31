"""SQLAlchemy ORM models for the Team Maturity Assessment tool."""

import secrets
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


def _generate_token() -> str:
    """Generate a short URL-safe token for team survey links."""
    return secrets.token_urlsafe(8)


class Base(DeclarativeBase):
    pass


class Question(Base):
    """A single survey statement seeded from the CSV.

    Grouped by category -> subcategory, displayed in display_order.

    Two assessment types:
    - "team": Likert-scale statements (original Scrum Team Survey).
    - "engineering": Rubric-based maturity questions with level descriptions.
    """

    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String(100), nullable=False, index=True)
    subcategory = Column(String(200), nullable=False)
    statement = Column(Text, nullable=False)
    display_order = Column(Integer, nullable=False, default=0)
    assessment_type = Column(String(20), nullable=False, default="team", index=True)

    # Rubric level descriptions (engineering assessment only)
    level_1 = Column(Text, nullable=True)  # Base
    level_2 = Column(Text, nullable=True)  # Beginner
    level_3 = Column(Text, nullable=True)  # Intermediate
    level_4 = Column(Text, nullable=True)  # Advanced
    level_5 = Column(Text, nullable=True)  # Expert

    answers = relationship("ResponseAnswer", back_populates="question")


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, unique=True)
    member_count = Column(Integer, nullable=True)
    token = Column(String(50), nullable=False, unique=True, default=_generate_token)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    responses = relationship("Response", back_populates="team")


class AssessmentRound(Base):
    __tablename__ = "assessment_rounds"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    engineering_token = Column(
        String(50), nullable=False, unique=True, default=_generate_token
    )
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    responses = relationship("Response", back_populates="round")


class Response(Base):
    """A single survey submission by one person for one team in one round."""

    __tablename__ = "responses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    round_id = Column(Integer, ForeignKey("assessment_rounds.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)  # NULL for engineering
    respondent_name = Column(String(200), nullable=False)
    assessment_type = Column(String(20), nullable=False, default="team")
    submitted_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_response_team_round", "team_id", "round_id"),
        Index("ix_response_round_team", "round_id", "team_id"),
    )

    round = relationship("AssessmentRound", back_populates="responses")
    team = relationship("Team", back_populates="responses")
    answers = relationship(
        "ResponseAnswer", back_populates="response", cascade="all, delete-orphan"
    )


class ResponseAnswer(Base):
    """Individual score (1-5) for a single question within a response."""

    __tablename__ = "response_answers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    response_id = Column(Integer, ForeignKey("responses.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    score = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("response_id", "question_id", name="uq_response_question"),
        Index("ix_ra_question", "question_id"),
    )

    response = relationship("Response", back_populates="answers")
    question = relationship("Question", back_populates="answers")
