"""Survey routes -- token-based per-team links, no email required."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AssessmentRound, Question, Response, ResponseAnswer, Team

router = APIRouter(prefix="/survey", tags=["survey"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/{token}")
def survey_form(token: str, request: Request, db: Session = Depends(get_db)):
    """Render the survey form for a specific team (identified by token)."""
    team = db.query(Team).filter(Team.token == token).first()
    if not team:
        raise HTTPException(status_code=404, detail="Invalid survey link")

    active_rounds = (
        db.query(AssessmentRound)
        .filter(AssessmentRound.is_active == True)
        .order_by(AssessmentRound.created_at.desc())
        .all()
    )
    questions = db.query(Question).order_by(Question.display_order).all()

    # Group questions: {category: {subcategory: [question, ...]}}
    grouped: dict[str, dict[str, list]] = {}
    for q in questions:
        grouped.setdefault(q.category, {}).setdefault(q.subcategory, []).append(q)

    return templates.TemplateResponse(
        "survey.html",
        {
            "request": request,
            "team": team,
            "rounds": active_rounds,
            "grouped_questions": grouped,
            "total_questions": len(questions),
        },
    )


@router.post("/{token}")
async def submit_survey(token: str, request: Request, db: Session = Depends(get_db)):
    """Process survey submission and store all answers."""
    team = db.query(Team).filter(Team.token == token).first()
    if not team:
        raise HTTPException(status_code=404, detail="Invalid survey link")

    form = await request.form()

    round_id = int(form.get("round_id", 0))
    respondent_name = str(form.get("respondent_name", "")).strip()

    if not all([round_id, respondent_name]):
        return RedirectResponse(
            url=f"/survey/{token}?error=missing_fields", status_code=303
        )

    # Create the response record
    response = Response(
        round_id=round_id,
        team_id=team.id,
        respondent_name=respondent_name,
    )
    db.add(response)
    db.flush()

    # Collect all question answers from the form (fields named "q_{question_id}")
    questions = db.query(Question).all()
    for q in questions:
        score_str = form.get(f"q_{q.id}")
        if score_str:
            answer = ResponseAnswer(
                response_id=response.id,
                question_id=q.id,
                score=int(score_str),
            )
            db.add(answer)

    db.commit()
    return RedirectResponse(url=f"/survey/{token}/thanks", status_code=303)


@router.get("/{token}/thanks")
def survey_thanks(token: str, request: Request, db: Session = Depends(get_db)):
    team = db.query(Team).filter(Team.token == token).first()
    return templates.TemplateResponse(
        "thanks.html", {"request": request, "team": team, "token": token}
    )
