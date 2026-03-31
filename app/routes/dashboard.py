"""Dashboard routes -- overview cards and per-team detail views."""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AssessmentRound, Question, Team
from app.eng_statistics import (
    MATURITY_DESCRIPTIONS,
    MATURITY_LABELS,
    get_area_details,
    get_engineering_stats,
)
from app.statistics import (
    get_exec_summary,
    get_overview_cards,
    get_overview_trends,
    get_statement_scores,
    get_team_maturity_overview,
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
    overview_stats = None
    statement_scores = []
    if selected_round:
        cards = get_overview_cards(db, selected_round.id)
        overview_stats = get_team_maturity_overview(db, selected_round.id)
        statement_scores = get_statement_scores(db, None, selected_round.id)

    grouped_statements: dict[str, dict[str, list]] = {}
    for s in statement_scores:
        grouped_statements.setdefault(s.category, {}).setdefault(
            s.subcategory, []
        ).append(s)

    overview_trends = get_overview_trends(db)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "rounds": rounds,
            "selected_round": selected_round,
            "cards": cards,
            "overview_stats": overview_stats,
            "overview_trends": overview_trends,
            "grouped_statements": grouped_statements,
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

    # ── Team Maturity Survey data ──
    stats = None
    summary = None
    trends = {}
    statement_scores = []
    if selected_round:
        stats = get_team_round_stats(db, team_id, selected_round.id)
        summary = get_exec_summary(db, team_id, selected_round.id)
        trends = get_team_trends(db, team_id)
        statement_scores = get_statement_scores(db, team_id, selected_round.id)

    grouped_statements: dict[str, dict[str, list]] = {}
    for s in statement_scores:
        grouped_statements.setdefault(s.category, {}).setdefault(
            s.subcategory, []
        ).append(s)

    # ── Engineering Maturity data (filtered by this team) ──
    eng_stats = None
    eng_area_details = []
    if selected_round:
        eng_stats = get_engineering_stats(db, selected_round.id, team_id=team_id)
        eng_area_details = get_area_details(db, selected_round.id, team_id=team_id)

    grouped_eng_areas: dict[str, dict[str, list]] = {}
    for a in eng_area_details:
        grouped_eng_areas.setdefault(a["category"], {}).setdefault(
            a["subcategory"], []
        ).append(a)

    return templates.TemplateResponse(
        "team_view.html",
        {
            "request": request,
            "team": team,
            "rounds": rounds,
            "selected_round": selected_round,
            # Team Maturity
            "stats": stats,
            "summary": summary,
            "trends": trends,
            "grouped_statements": grouped_statements,
            # Engineering Maturity
            "eng_stats": eng_stats,
            "grouped_eng_areas": grouped_eng_areas,
            "maturity_labels": MATURITY_LABELS,
            "maturity_descriptions": MATURITY_DESCRIPTIONS,
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
