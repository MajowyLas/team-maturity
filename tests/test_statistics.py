"""Regression tests for team survey statistics (app.statistics)."""

from __future__ import annotations

import pytest

from app.statistics import (
    get_exec_summary,
    get_overview_cards,
    get_overview_trends,
    get_statement_scores,
    get_team_maturity_overview,
    get_team_round_stats,
    get_team_trends,
)
from tests.conftest import (
    make_round,
    make_team,
    make_team_questions,
    submit_team_response,
)


# ── get_team_round_stats ────────────────────────────────────────────────────


class TestGetTeamRoundStats:
    """Core aggregation: category / subcategory averages for a team in a round."""

    def test_returns_none_for_nonexistent_team(self, db):
        rnd = make_round(db)
        assert get_team_round_stats(db, team_id=999, round_id=rnd.id) is None

    def test_returns_none_for_nonexistent_round(self, db):
        team = make_team(db)
        assert get_team_round_stats(db, team_id=team.id, round_id=999) is None

    def test_empty_round_returns_zero_stats(self, db):
        team = make_team(db)
        rnd = make_round(db)
        stats = get_team_round_stats(db, team.id, rnd.id)
        assert stats is not None
        assert stats.response_count == 0
        assert stats.overall_avg == 0.0
        assert stats.category_scores == []

    def test_single_response_correct_averages(self, db):
        team = make_team(db)
        rnd = make_round(db)
        qs = make_team_questions(db, count=4)
        submit_team_response(db, team, rnd, qs, scores=[4, 2, 5, 3])
        db.commit()

        stats = get_team_round_stats(db, team.id, rnd.id)
        assert stats.response_count == 1
        # 2 categories: Culture (q0=4, q2=5) avg=4.5 ; Process (q1=2, q3=3) avg=2.5
        cat_map = {c.category: c.avg for c in stats.category_scores}
        assert cat_map["Culture"] == 4.5
        assert cat_map["Process"] == 2.5
        assert stats.overall_avg == 3.5  # (4.5 + 2.5) / 2

    def test_multiple_respondents_averaged(self, db):
        team = make_team(db)
        rnd = make_round(db)
        qs = make_team_questions(db, count=2)  # q0=Culture, q1=Process
        submit_team_response(db, team, rnd, qs, scores=[4, 2], respondent="A")
        submit_team_response(db, team, rnd, qs, scores=[2, 4], respondent="B")
        db.commit()

        stats = get_team_round_stats(db, team.id, rnd.id)
        assert stats.response_count == 2
        cat_map = {c.category: c.avg for c in stats.category_scores}
        assert cat_map["Culture"] == 3.0  # (4+2)/2
        assert cat_map["Process"] == 3.0  # (2+4)/2

    def test_subcategory_min_max(self, db):
        team = make_team(db)
        rnd = make_round(db)
        qs = make_team_questions(db, count=2)
        submit_team_response(db, team, rnd, qs, [1, 5], respondent="A")
        submit_team_response(db, team, rnd, qs, [5, 1], respondent="B")
        db.commit()

        stats = get_team_round_stats(db, team.id, rnd.id)
        for sub in stats.subcategory_scores:
            assert sub.min_score == 1
            assert sub.max_score == 5


# ── get_exec_summary ────────────────────────────────────────────────────────


class TestGetExecSummary:
    """Executive summary: strengths, improvements, round-over-round deltas."""

    def test_returns_none_when_no_data(self, db):
        team = make_team(db)
        rnd = make_round(db)
        assert get_exec_summary(db, team.id, rnd.id) is None

    def test_strengths_and_improvements(self, db):
        team = make_team(db)
        rnd = make_round(db)
        qs = make_team_questions(db, count=4)
        # Culture/Collaboration: 5,5 → avg 5  ; Process/Planning: 1,1 → avg 1
        submit_team_response(db, team, rnd, qs, [5, 1, 5, 1])
        db.commit()

        summary = get_exec_summary(db, team.id, rnd.id)
        assert summary is not None
        assert summary.strengths[0].subcategory == "Collaboration"
        assert summary.improvements[0].subcategory == "Planning"

    def test_round_deltas(self, db):
        team = make_team(db)
        r1 = make_round(db, name="R1")
        r2 = make_round(db, name="R2")
        qs = make_team_questions(db, count=2)

        submit_team_response(db, team, r1, qs, [2, 2])
        submit_team_response(db, team, r2, qs, [4, 4])
        db.commit()

        summary = get_exec_summary(db, team.id, r2.id)
        assert summary.previous_overall is not None
        assert summary.previous_overall == 2.0
        assert summary.overall_score == 4.0
        # Each category should show +2.0 delta
        for delta in summary.category_deltas.values():
            assert delta == 2.0


# ── get_team_maturity_overview ───────────────────────────────────────────────


class TestGetTeamMaturityOverview:
    """Department-wide aggregation across all teams."""

    def test_returns_none_with_no_data(self, db):
        rnd = make_round(db)
        assert get_team_maturity_overview(db, rnd.id) is None

    def test_aggregates_across_teams(self, db):
        t1 = make_team(db, name="Alpha")
        t2 = make_team(db, name="Beta")
        rnd = make_round(db)
        qs = make_team_questions(db, count=2)
        submit_team_response(db, t1, rnd, qs, [4, 2])
        submit_team_response(db, t2, rnd, qs, [2, 4])
        db.commit()

        overview = get_team_maturity_overview(db, rnd.id)
        assert overview is not None
        assert overview["response_count"] == 2
        # Culture: (4+2)/2=3.0 ; Process: (2+4)/2=3.0
        assert overview["overall_avg"] == 3.0

    def test_strengths_and_improvements(self, db):
        team = make_team(db)
        rnd = make_round(db)
        qs = make_team_questions(db, count=4)
        submit_team_response(db, team, rnd, qs, [5, 1, 5, 1])
        db.commit()

        overview = get_team_maturity_overview(db, rnd.id)
        assert overview["strengths"][0]["subcategory"] == "Collaboration"
        assert overview["improvements"][0]["subcategory"] == "Planning"


# ── get_statement_scores ────────────────────────────────────────────────────


class TestGetStatementScores:
    def test_returns_per_question_averages(self, db):
        team = make_team(db)
        rnd = make_round(db)
        qs = make_team_questions(db, count=2)
        submit_team_response(db, team, rnd, qs, [3, 5], respondent="A")
        submit_team_response(db, team, rnd, qs, [5, 3], respondent="B")
        db.commit()

        scores = get_statement_scores(db, team.id, rnd.id)
        assert len(scores) == 2
        score_map = {s.statement: s.avg for s in scores}
        assert score_map["Team statement 1"] == 4.0  # (3+5)/2
        assert score_map["Team statement 2"] == 4.0  # (5+3)/2


# ── get_overview_cards ──────────────────────────────────────────────────────


class TestGetOverviewCards:
    def test_cards_for_all_teams(self, db):
        t1 = make_team(db, name="Alpha")
        t2 = make_team(db, name="Beta")
        rnd = make_round(db)
        qs = make_team_questions(db, count=2)
        submit_team_response(db, t1, rnd, qs, [4, 4])
        db.commit()

        cards = get_overview_cards(db, rnd.id)
        assert len(cards) == 2  # both teams appear
        alpha_card = next(c for c in cards if c["team_name"] == "Alpha")
        beta_card = next(c for c in cards if c["team_name"] == "Beta")
        assert alpha_card["response_count"] == 1
        assert beta_card["response_count"] == 0

    def test_card_includes_strength_and_improvement(self, db):
        team = make_team(db)
        rnd = make_round(db)
        qs = make_team_questions(db, count=4)
        submit_team_response(db, team, rnd, qs, [5, 1, 5, 1])
        db.commit()

        cards = get_overview_cards(db, rnd.id)
        card = cards[0]
        assert card["top_strength"] is not None
        assert card["top_improvement"] is not None


# ── get_overview_trends ─────────────────────────────────────────────────────


class TestGetOverviewTrends:
    def test_needs_at_least_two_rounds(self, db):
        team = make_team(db)
        rnd = make_round(db)
        qs = make_team_questions(db, count=2)
        submit_team_response(db, team, rnd, qs, [3, 3])
        db.commit()

        trends = get_overview_trends(db)
        assert trends["round_names"] == []

    def test_returns_trends_with_two_rounds(self, db):
        team = make_team(db)
        r1 = make_round(db, name="R1")
        r2 = make_round(db, name="R2")
        qs = make_team_questions(db, count=2)
        submit_team_response(db, team, r1, qs, [2, 2])
        submit_team_response(db, team, r2, qs, [4, 4])
        db.commit()

        trends = get_overview_trends(db)
        assert len(trends["round_names"]) == 2
        assert len(trends["teams"]) == 1
        assert trends["teams"][0]["name"] == "Alpha"


# ── get_team_trends ─────────────────────────────────────────────────────────


class TestGetTeamTrends:
    def test_returns_per_category_trends(self, db):
        team = make_team(db)
        r1 = make_round(db, name="R1")
        r2 = make_round(db, name="R2")
        qs = make_team_questions(db, count=2)
        submit_team_response(db, team, r1, qs, [2, 3])
        submit_team_response(db, team, r2, qs, [4, 5])
        db.commit()

        trends = get_team_trends(db, team.id)
        assert "Culture" in trends
        assert "Process" in trends
        assert len(trends["Culture"]) == 2
