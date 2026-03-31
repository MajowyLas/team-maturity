"""Regression tests for engineering statistics (app.eng_statistics)."""

from __future__ import annotations

import pytest

from app.eng_statistics import (
    MATURITY_LABELS,
    get_area_details,
    get_engineering_stats,
    get_engineering_trends,
)
from tests.conftest import (
    make_eng_questions,
    make_round,
    make_team,
    submit_eng_response,
)


# ── get_engineering_stats ───────────────────────────────────────────────────


class TestGetEngineeringStats:
    """Aggregate engineering assessment scores per round."""

    def test_returns_none_with_no_responses(self, db):
        rnd = make_round(db)
        assert get_engineering_stats(db, rnd.id) is None

    def test_overall_average(self, db):
        rnd = make_round(db)
        qs = make_eng_questions(db, count=4)
        # Build & Deploy (q0=3, q2=5) avg=4 ; Test & Verification (q1=1, q3=3) avg=2
        submit_eng_response(db, rnd, qs, scores=[3, 1, 5, 3])
        db.commit()

        stats = get_engineering_stats(db, rnd.id)
        assert stats is not None
        assert stats["response_count"] == 1
        cat_map = {c["category"]: c["avg"] for c in stats["category_scores"]}
        assert cat_map["Build & Deploy"] == 4.0
        assert cat_map["Test & Verification"] == 2.0
        assert stats["overall_avg"] == 3.0

    def test_multiple_respondents(self, db):
        rnd = make_round(db)
        qs = make_eng_questions(db, count=2)
        submit_eng_response(db, rnd, qs, [2, 4], respondent="A")
        submit_eng_response(db, rnd, qs, [4, 2], respondent="B")
        db.commit()

        stats = get_engineering_stats(db, rnd.id)
        assert stats["response_count"] == 2
        cat_map = {c["category"]: c["avg"] for c in stats["category_scores"]}
        assert cat_map["Build & Deploy"] == 3.0
        assert cat_map["Test & Verification"] == 3.0

    def test_strengths_and_improvements(self, db):
        rnd = make_round(db)
        qs = make_eng_questions(db, count=4)
        submit_eng_response(db, rnd, qs, [5, 1, 5, 1])
        db.commit()

        stats = get_engineering_stats(db, rnd.id)
        # Build & Deploy should be strongest, Test & Verification weakest
        assert stats["strengths"][0]["category"] == "Build & Deploy"
        assert stats["improvements"][0]["category"] == "Test & Verification"

    def test_team_filter(self, db):
        rnd = make_round(db)
        team_a = make_team(db, name="Alpha")
        team_b = make_team(db, name="Beta")
        qs = make_eng_questions(db, count=2)

        submit_eng_response(db, rnd, qs, [5, 5], team=team_a, respondent="A")
        submit_eng_response(db, rnd, qs, [1, 1], team=team_b, respondent="B")
        db.commit()

        stats_a = get_engineering_stats(db, rnd.id, team_id=team_a.id)
        stats_b = get_engineering_stats(db, rnd.id, team_id=team_b.id)

        assert stats_a["overall_avg"] == 5.0
        assert stats_b["overall_avg"] == 1.0

    def test_overall_label(self, db):
        rnd = make_round(db)
        qs = make_eng_questions(db, count=2)
        submit_eng_response(db, rnd, qs, [3, 3])
        db.commit()

        stats = get_engineering_stats(db, rnd.id)
        assert stats["overall_label"] == MATURITY_LABELS[3]


# ── get_area_details ────────────────────────────────────────────────────────


class TestGetAreaDetails:
    """Per-question scores with maturity labels."""

    def test_returns_details_per_question(self, db):
        rnd = make_round(db)
        qs = make_eng_questions(db, count=4)
        submit_eng_response(db, rnd, qs, [2, 4, 3, 5])
        db.commit()

        details = get_area_details(db, rnd.id)
        assert len(details) == 4
        detail_map = {d["area"]: d for d in details}
        assert detail_map["Engineering area 1"]["avg"] == 2.0
        assert detail_map["Engineering area 1"]["level_label"] == "Beginner"
        assert detail_map["Engineering area 4"]["avg"] == 5.0
        assert detail_map["Engineering area 4"]["level_label"] == "Expert"

    def test_team_filter(self, db):
        rnd = make_round(db)
        team = make_team(db)
        qs = make_eng_questions(db, count=2)

        # One response WITH team, one WITHOUT
        submit_eng_response(db, rnd, qs, [5, 5], team=team, respondent="A")
        submit_eng_response(db, rnd, qs, [1, 1], respondent="B")
        db.commit()

        details_team = get_area_details(db, rnd.id, team_id=team.id)
        details_all = get_area_details(db, rnd.id)

        assert details_team[0]["avg"] == 5.0
        assert details_all[0]["avg"] == 3.0  # (5+1)/2


# ── get_engineering_trends ──────────────────────────────────────────────────


class TestGetEngineeringTrends:
    def test_needs_at_least_two_rounds(self, db):
        rnd = make_round(db)
        qs = make_eng_questions(db, count=2)
        submit_eng_response(db, rnd, qs, [3, 3])
        db.commit()

        trends = get_engineering_trends(db)
        assert trends["round_names"] == []

    def test_returns_category_trends(self, db):
        r1 = make_round(db, name="R1")
        r2 = make_round(db, name="R2")
        qs = make_eng_questions(db, count=2)
        submit_eng_response(db, r1, qs, [2, 2], respondent="A")
        submit_eng_response(db, r2, qs, [4, 4], respondent="B")
        db.commit()

        trends = get_engineering_trends(db)
        assert len(trends["round_names"]) == 2
        assert "Build & Deploy" in trends["categories"]
