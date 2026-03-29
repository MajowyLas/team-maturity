"""Regression tests for HTTP routes.

Verifies that all pages return expected status codes, with and without data.
Uses the FastAPI TestClient with the in-memory DB.
"""

from __future__ import annotations

import pytest

from app.models import AssessmentRound, Question, Team
from tests.conftest import (
    make_eng_questions,
    make_round,
    make_team,
    make_team_questions,
    submit_eng_response,
    submit_team_response,
)


# ── Landing page ────────────────────────────────────────────────────────────


class TestLandingPage:
    def test_landing_empty_db(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_landing_with_data(self, client, db):
        make_team(db)
        make_round(db)
        db.commit()
        resp = client.get("/")
        assert resp.status_code == 200


# ── Team Maturity Overview (dashboard) ──────────────────────────────────────


class TestDashboardOverview:
    def test_dashboard_empty(self, client):
        resp = client.get("/dashboard")
        assert resp.status_code == 200

    def test_dashboard_with_data(self, client, db):
        team = make_team(db)
        rnd = make_round(db)
        qs = make_team_questions(db, count=2)
        submit_team_response(db, team, rnd, qs, [4, 3])
        db.commit()

        resp = client.get("/dashboard")
        assert resp.status_code == 200

    def test_dashboard_with_round_filter(self, client, db):
        team = make_team(db)
        rnd = make_round(db)
        qs = make_team_questions(db, count=2)
        submit_team_response(db, team, rnd, qs, [4, 3])
        db.commit()

        resp = client.get(f"/dashboard?round_id={rnd.id}")
        assert resp.status_code == 200


# ── Team View (per-team detail) ─────────────────────────────────────────────


class TestTeamView:
    def test_nonexistent_team_redirects(self, client):
        resp = client.get("/dashboard/team/999", follow_redirects=False)
        assert resp.status_code == 303

    def test_team_view_empty(self, client, db):
        team = make_team(db)
        make_round(db)
        db.commit()
        resp = client.get(f"/dashboard/team/{team.id}")
        assert resp.status_code == 200

    def test_team_view_with_data(self, client, db):
        team = make_team(db)
        rnd = make_round(db)
        qs = make_team_questions(db, count=4)
        eng_qs = make_eng_questions(db, count=2)
        submit_team_response(db, team, rnd, qs, [4, 3, 5, 2])
        submit_eng_response(db, rnd, eng_qs, [3, 4], team=team)
        db.commit()

        resp = client.get(f"/dashboard/team/{team.id}")
        assert resp.status_code == 200


# ── Team View API (JSON) ───────────────────────────────────────────────────


class TestTeamViewAPI:
    def test_api_returns_json(self, client, db):
        team = make_team(db)
        rnd = make_round(db)
        qs = make_team_questions(db, count=2)
        submit_team_response(db, team, rnd, qs, [4, 3])
        db.commit()

        resp = client.get(f"/dashboard/api/team/{team.id}?round_id={rnd.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "category_scores" in data
        assert "trends" in data
        assert "summary" in data

    def test_api_empty_round_returns_200_with_empty_scores(self, client, db):
        """When a team exists but has no responses, the API returns 200
        with empty lists (get_team_round_stats returns a zero-count object,
        not None). This is current behavior — stats is truthy.
        """
        team = make_team(db)
        rnd = make_round(db)
        db.commit()

        resp = client.get(f"/dashboard/api/team/{team.id}?round_id={rnd.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["category_scores"] == []
        assert data["summary"]["responses"] == 0


# ── Survey routes ───────────────────────────────────────────────────────────


class TestSurveyRoutes:
    def test_survey_form_valid_token(self, client, db):
        team = make_team(db)
        make_round(db)
        db.commit()
        resp = client.get(f"/survey/{team.token}")
        assert resp.status_code == 200

    def test_survey_form_invalid_token(self, client):
        resp = client.get("/survey/invalid-token")
        assert resp.status_code == 404

    def test_survey_thanks(self, client, db):
        team = make_team(db)
        db.commit()
        resp = client.get(f"/survey/{team.token}/thanks")
        assert resp.status_code == 200


# ── Engineering survey routes ───────────────────────────────────────────────


class TestEngineeringSurveyRoutes:
    def test_eng_survey_valid_token(self, client, db):
        rnd = make_round(db)
        make_eng_questions(db, count=2)
        make_team(db)  # needed for team dropdown
        db.commit()
        resp = client.get(f"/engineering/{rnd.engineering_token}")
        assert resp.status_code == 200

    def test_eng_survey_invalid_token(self, client):
        resp = client.get("/engineering/bad-token")
        assert resp.status_code == 404

    def test_eng_survey_inactive_round(self, client, db):
        rnd = make_round(db, active=False)
        db.commit()
        resp = client.get(f"/engineering/{rnd.engineering_token}")
        assert resp.status_code == 410


# ── Engineering dashboard ───────────────────────────────────────────────────


class TestEngineeringDashboard:
    def test_dashboard_empty(self, client):
        resp = client.get("/engineering/dashboard/view")
        assert resp.status_code == 200

    def test_dashboard_with_data(self, client, db):
        rnd = make_round(db)
        qs = make_eng_questions(db, count=4)
        submit_eng_response(db, rnd, qs, [3, 4, 2, 5])
        db.commit()

        resp = client.get("/engineering/dashboard/view")
        assert resp.status_code == 200

    def test_dashboard_team_filter(self, client, db):
        team = make_team(db)
        rnd = make_round(db)
        qs = make_eng_questions(db, count=2)
        submit_eng_response(db, rnd, qs, [4, 4], team=team)
        db.commit()

        resp = client.get(f"/engineering/dashboard/view?team_id={team.id}")
        assert resp.status_code == 200


# ── Admin panel ─────────────────────────────────────────────────────────────


class TestAdminPanel:
    def test_admin_empty(self, client):
        resp = client.get("/admin")
        assert resp.status_code == 200

    def test_admin_with_data(self, client, db):
        team = make_team(db)
        rnd = make_round(db)
        qs = make_team_questions(db, count=2)
        submit_team_response(db, team, rnd, qs, [3, 3])
        db.commit()

        resp = client.get("/admin")
        assert resp.status_code == 200


# ── Admin API endpoints ─────────────────────────────────────────────────────


class TestAdminAPI:
    def test_create_team_api(self, client):
        resp = client.post("/admin/api/teams", json={"name": "NewTeam"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "NewTeam"
        assert "token" in data

    def test_create_duplicate_team_api(self, client, db):
        make_team(db, name="Existing")
        db.commit()
        resp = client.post("/admin/api/teams", json={"name": "Existing"})
        assert resp.status_code == 409

    def test_create_round_api(self, client):
        resp = client.post("/admin/api/rounds", json={"name": "Q2 2026"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Q2 2026"
        assert "engineering_token" in data

    def test_toggle_round(self, client, db):
        rnd = make_round(db)
        db.commit()
        resp = client.post(f"/admin/rounds/{rnd.id}/toggle", follow_redirects=False)
        assert resp.status_code == 303

    def test_edit_team(self, client, db):
        team = make_team(db, name="Old")
        db.commit()
        resp = client.post(
            f"/admin/teams/{team.id}/edit",
            data={"team_name": "New", "member_count": "10"},
            follow_redirects=False,
        )
        assert resp.status_code == 303

    def test_delete_team(self, client, db):
        team = make_team(db, name="ToDelete")
        db.commit()
        resp = client.post(
            f"/admin/teams/{team.id}/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 303


# ── CSV export ──────────────────────────────────────────────────────────────


class TestCSVExport:
    def test_download_team_questions_csv(self, client, db):
        make_team_questions(db, count=2)
        db.commit()
        resp = client.get("/admin/data/download-questions/team")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")

    def test_download_engineering_questions_csv(self, client, db):
        make_eng_questions(db, count=2)
        db.commit()
        resp = client.get("/admin/data/download-questions/engineering")
        assert resp.status_code == 200

    def test_export_round_csv(self, client, db):
        team = make_team(db)
        rnd = make_round(db)
        qs = make_team_questions(db, count=2)
        submit_team_response(db, team, rnd, qs, [3, 4])
        db.commit()
        resp = client.get(f"/admin/export/{rnd.id}")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
