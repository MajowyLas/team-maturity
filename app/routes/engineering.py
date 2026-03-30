"""Engineering Delivery Assessment routes.

Department-wide rubric-based maturity assessment.
Shareable survey link: /engineering/<round_token>
Dashboard: /engineering/dashboard
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.eng_statistics import (
    MATURITY_DESCRIPTIONS,
    MATURITY_LABELS,
    get_area_details,
    get_engineering_stats,
    get_engineering_trends,
)
from app.models import AssessmentRound, Question, Response, ResponseAnswer, Team

router = APIRouter(prefix="/engineering", tags=["engineering"])
templates = Jinja2Templates(directory="app/templates")

# ─── Dashboard ───────────────────────────────────────────────────────────────
# NOTE: Dashboard routes MUST be defined before /{token} wildcard routes,
# otherwise FastAPI matches "dashboard" as a token value.


@router.get("/dashboard/view")
def engineering_dashboard(
    request: Request,
    round_id: int | None = Query(None),
    team_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    """Engineering maturity dashboard — department-wide or filtered by team."""
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

    teams = db.query(Team).order_by(Team.name).all()
    selected_team = db.get(Team, team_id) if team_id else None

    stats = None
    trends = {}
    area_details = []

    if selected_round:
        stats = get_engineering_stats(db, selected_round.id, team_id=team_id)
        trends = get_engineering_trends(db, team_id=team_id)
        area_details = get_area_details(db, selected_round.id, team_id=team_id)

    # Group area details: {category: {subcategory: [area, ...]}}
    grouped_areas: dict[str, dict[str, list]] = {}
    for a in area_details:
        grouped_areas.setdefault(a["category"], {}).setdefault(
            a["subcategory"], []
        ).append(a)

    base_url = str(request.base_url).rstrip("/")

    return templates.TemplateResponse(
        "engineering_dashboard.html",
        {
            "request": request,
            "rounds": rounds,
            "selected_round": selected_round,
            "teams": teams,
            "selected_team": selected_team,
            "stats": stats,
            "trends": trends,
            "grouped_areas": grouped_areas,
            "maturity_labels": MATURITY_LABELS,
            "maturity_descriptions": MATURITY_DESCRIPTIONS,
            "base_url": base_url,
        },
    )


# ─── Survey (token-based) ────────────────────────────────────────────────────


@router.get("/{token}")
def engineering_survey_form(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Render the engineering delivery assessment survey for a specific round."""
    rnd = (
        db.query(AssessmentRound)
        .filter(AssessmentRound.engineering_token == token)
        .first()
    )
    if not rnd:
        raise HTTPException(status_code=404, detail="Invalid assessment link")

    if not rnd.is_active:
        raise HTTPException(status_code=410, detail="This assessment round is closed")

    questions = (
        db.query(Question)
        .filter(Question.assessment_type == "engineering")
        .order_by(Question.display_order)
        .all()
    )

    teams = db.query(Team).order_by(Team.name).all()

    # Group: {category: {subcategory: [question, ...]}}
    grouped: dict[str, dict[str, list]] = {}
    for q in questions:
        grouped.setdefault(q.category, {}).setdefault(q.subcategory, []).append(q)

    return templates.TemplateResponse(
        "engineering_survey.html",
        {
            "request": request,
            "round": rnd,
            "token": token,
            "teams": teams,
            "grouped_questions": grouped,
            "total_questions": len(questions),
            "maturity_labels": MATURITY_LABELS,
            "maturity_descriptions": MATURITY_DESCRIPTIONS,
        },
    )


@router.post("/{token}")
async def submit_engineering_survey(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Process engineering assessment submission."""
    rnd = (
        db.query(AssessmentRound)
        .filter(AssessmentRound.engineering_token == token)
        .first()
    )
    if not rnd:
        raise HTTPException(status_code=404, detail="Invalid assessment link")

    form = await request.form()
    respondent_name = str(form.get("respondent_name", "")).strip()
    team_id_str = form.get("team_id", "")
    team_id = int(team_id_str) if team_id_str and team_id_str != "" else None

    if not respondent_name:
        return RedirectResponse(
            url=f"/engineering/{token}?error=missing_fields", status_code=303
        )

    response = Response(
        round_id=rnd.id,
        team_id=team_id,
        respondent_name=respondent_name,
        assessment_type="engineering",
    )
    db.add(response)
    db.flush()

    questions = (
        db.query(Question).filter(Question.assessment_type == "engineering").all()
    )
    for q in questions:
        score_str = form.get(f"q_{q.id}")
        if score_str:
            db.add(
                ResponseAnswer(
                    response_id=response.id,
                    question_id=q.id,
                    score=int(score_str),
                )
            )

    db.commit()
    return RedirectResponse(url=f"/engineering/{token}/thanks", status_code=303)


@router.get("/{token}/thanks")
def engineering_thanks(token: str, request: Request, db: Session = Depends(get_db)):
    rnd = (
        db.query(AssessmentRound)
        .filter(AssessmentRound.engineering_token == token)
        .first()
    )
    return templates.TemplateResponse(
        "engineering_thanks.html",
        {"request": request, "token": token, "round": rnd},
    )

