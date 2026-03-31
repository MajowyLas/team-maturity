"""Regression tests for data isolation between team and engineering surveys.

The two assessment types share the same Response/ResponseAnswer tables,
differentiated by ``assessment_type``. These tests verify that statistics
functions NEVER bleed data between types.
"""

from __future__ import annotations

import pytest

from app.eng_statistics import get_engineering_stats
from app.statistics import get_team_round_stats
from tests.conftest import (
    make_eng_questions,
    make_round,
    make_team,
    make_team_questions,
    submit_eng_response,
    submit_team_response,
)


class TestDataIsolation:
    """Ensure team stats ignore engineering data and vice versa."""

    def test_team_stats_exclude_engineering_responses(self, db):
        """Team stats should NOT include engineering survey answers."""
        team = make_team(db)
        rnd = make_round(db)
        team_qs = make_team_questions(db, count=2)
        eng_qs = make_eng_questions(db, count=2)

        submit_team_response(db, team, rnd, team_qs, [4, 4])
        submit_eng_response(db, rnd, eng_qs, [1, 1], team=team)
        db.commit()

        stats = get_team_round_stats(db, team.id, rnd.id)
        assert stats.response_count == 1  # only team response
        assert stats.overall_avg == 4.0  # not contaminated by eng scores

    def test_engineering_stats_exclude_team_responses(self, db):
        """Engineering stats should NOT include team survey answers."""
        team = make_team(db)
        rnd = make_round(db)
        team_qs = make_team_questions(db, count=2)
        eng_qs = make_eng_questions(db, count=2)

        submit_team_response(db, team, rnd, team_qs, [5, 5])
        submit_eng_response(db, rnd, eng_qs, [2, 2], team=team)
        db.commit()

        eng_stats = get_engineering_stats(db, rnd.id, team_id=team.id)
        assert eng_stats["response_count"] == 1
        assert eng_stats["overall_avg"] == 2.0  # not contaminated by team scores

    def test_team_stats_with_only_engineering_data(self, db):
        """If only engineering data exists, team stats should be empty."""
        team = make_team(db)
        rnd = make_round(db)
        eng_qs = make_eng_questions(db, count=2)
        submit_eng_response(db, rnd, eng_qs, [3, 3], team=team)
        db.commit()

        stats = get_team_round_stats(db, team.id, rnd.id)
        assert stats.response_count == 0
        assert stats.overall_avg == 0.0

    def test_engineering_stats_with_only_team_data(self, db):
        """If only team data exists, engineering stats should be None."""
        team = make_team(db)
        rnd = make_round(db)
        team_qs = make_team_questions(db, count=2)
        submit_team_response(db, team, rnd, team_qs, [4, 4])
        db.commit()

        eng_stats = get_engineering_stats(db, rnd.id)
        assert eng_stats is None

    def test_mixed_data_different_teams(self, db):
        """Each team's stats should reflect only their own responses."""
        team_a = make_team(db, name="Alpha")
        team_b = make_team(db, name="Beta")
        rnd = make_round(db)
        team_qs = make_team_questions(db, count=2)
        eng_qs = make_eng_questions(db, count=2)

        # Alpha: high team scores, low eng scores
        submit_team_response(db, team_a, rnd, team_qs, [5, 5])
        submit_eng_response(db, rnd, eng_qs, [1, 1], team=team_a)

        # Beta: low team scores, high eng scores
        submit_team_response(db, team_b, rnd, team_qs, [1, 1])
        submit_eng_response(db, rnd, eng_qs, [5, 5], team=team_b)
        db.commit()

        # Team stats
        stats_a = get_team_round_stats(db, team_a.id, rnd.id)
        stats_b = get_team_round_stats(db, team_b.id, rnd.id)
        assert stats_a.overall_avg == 5.0
        assert stats_b.overall_avg == 1.0

        # Engineering stats
        eng_a = get_engineering_stats(db, rnd.id, team_id=team_a.id)
        eng_b = get_engineering_stats(db, rnd.id, team_id=team_b.id)
        assert eng_a["overall_avg"] == 1.0
        assert eng_b["overall_avg"] == 5.0
