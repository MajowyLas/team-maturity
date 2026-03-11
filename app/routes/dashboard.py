"""Dashboard routes -- overview cards and per-team detail views."""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AssessmentRound, Question, Team
from app.statistics import (
    get_all_teams_trend_summary,
    get_exec_summary,
    get_overview_cards,
    get_overview_trends,
    get_statement_scores,
    get_team_round_stats,
    get_team_trends,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")


@router.get("")
def dashboard_overview(
    request: Request,
    round_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    """Overview dashboard with clickable team summary cards."""
    rounds = (
        db.query(AssessmentRound)
        .order_by(AssessmentRound.created_at.desc())
        .all()
    )

    selected_round = None
    if round_id:
        selected_round = db.get(AssessmentRound, round_id)
    if not selected_round and rounds:
        selected_round = rounds[0]

    cards = []
    if selected_round:
        cards = get_overview_cards(db, selected_round.id)

    overview_trends = get_overview_trends(db)
    trend_summary = get_all_teams_trend_summary(db)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "rounds": rounds,
            "selected_round": selected_round,
            "cards": cards,
            "overview_trends": overview_trends,
            "trend_summary": trend_summary,
        },
    )


@router.get("/team/{team_id}")
def team_dashboard(
    request: Request,
    team_id: int,
    round_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    """Per-team dashboard with charts, statement-level scores, and exec summary."""
    team = db.get(Team, team_id)
    if not team:
        return RedirectResponse(url="/dashboard", status_code=303)

    rounds = (
        db.query(AssessmentRound)
        .order_by(AssessmentRound.created_at.desc())
        .all()
    )

    selected_round = None
    if round_id:
        selected_round = db.get(AssessmentRound, round_id)
    if not selected_round and rounds:
        selected_round = rounds[0]

    stats = None
    summary = None
    trends = {}
    statement_scores = []
    if selected_round:
        stats = get_team_round_stats(db, team_id, selected_round.id)
        summary = get_exec_summary(db, team_id, selected_round.id)
        trends = get_team_trends(db, team_id)
        statement_scores = get_statement_scores(db, team_id, selected_round.id)

    # Group statement scores: {category: {subcategory: [StatementScore, ...]}}
    grouped_statements: dict[str, dict[str, list]] = {}
    for s in statement_scores:
        grouped_statements.setdefault(s.category, {}).setdefault(
            s.subcategory, []
        ).append(s)

    return templates.TemplateResponse(
        "team_dashboard.html",
        {
            "request": request,
            "team": team,
            "rounds": rounds,
            "selected_round": selected_round,
            "stats": stats,
            "summary": summary,
            "trends": trends,
            "grouped_statements": grouped_statements,
        },
    )


@router.get("/api/team/{team_id}")
def api_team_data(
    team_id: int,
    round_id: int = Query(...),
    db: Session = Depends(get_db),
):
    """JSON API for team chart data."""
    stats = get_team_round_stats(db, team_id, round_id)
    trends = get_team_trends(db, team_id)
    summary = get_exec_summary(db, team_id, round_id)

    if not stats:
        return JSONResponse({"error": "No data"}, status_code=404)

    return {
        "category_scores": [
            {"category": c.category, "avg": c.avg} for c in stats.category_scores
        ],
        "subcategory_scores": [
            {
                "category": s.category,
                "subcategory": s.subcategory,
                "avg": s.avg,
                "min": s.min_score,
                "max": s.max_score,
            }
            for s in stats.subcategory_scores
        ],
        "trends": {
            cat: [{"round": d["round_name"], "avg": d["avg"]} for d in points]
            for cat, points in trends.items()
        },
        "summary": {
            "overall": summary.overall_score if summary else 0,
            "responses": summary.response_count if summary else 0,
            "strengths": [
                {"subcategory": s.subcategory, "avg": s.avg}
                for s in (summary.strengths if summary else [])
            ],
            "improvements": [
                {"subcategory": s.subcategory, "avg": s.avg}
                for s in (summary.improvements if summary else [])
            ],
            "previous_overall": summary.previous_overall if summary else None,
            "category_deltas": summary.category_deltas if summary else {},
        },
    }
