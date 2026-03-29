"""Admin routes -- manage teams, assessment rounds, and view participation."""

import csv
import io
import shutil
import tempfile

from fastapi import APIRouter, Depends, Form, Request, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db, DB_PATH
from app.models import AssessmentRound, Question, Response, ResponseAnswer, Team
from app.seed import (
    parse_team_csv,
    parse_engineering_csv,
    seed_questions,
    seed_engineering_questions,
    TEAM_CSV,
    ENGINEERING_CSV,
    DATA_DIR,
)

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")


@router.get("")
def admin_panel(request: Request, db: Session = Depends(get_db)):
    """Render admin panel with teams, rounds, and participation stats."""
    teams = db.query(Team).order_by(Team.name).all()
    rounds = (
        db.query(AssessmentRound)
        .order_by(AssessmentRound.created_at.desc())
        .all()
    )

    # Participation: {(round_id, team_id): count}
    participation_rows = (
        db.query(
            Response.round_id,
            Response.team_id,
            func.count(Response.id).label("cnt"),
        )
        .group_by(Response.round_id, Response.team_id)
        .all()
    )
    participation = {
        (row.round_id, row.team_id): row.cnt for row in participation_rows
    }

    # Per-team total response count (for delete confirmation)
    team_response_counts_rows = (
        db.query(Response.team_id, func.count(Response.id).label("cnt"))
        .group_by(Response.team_id)
        .all()
    )
    team_response_counts = {row.team_id: row.cnt for row in team_response_counts_rows}

    # Question counts for data management
    team_q_count = db.query(Question).filter(Question.assessment_type == "team").count()
    eng_q_count = db.query(Question).filter(Question.assessment_type == "engineering").count()

    # Build the base URL for survey links
    base_url = str(request.base_url).rstrip("/")

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "teams": teams,
            "rounds": rounds,
            "participation": participation,
            "team_response_counts": team_response_counts,
            "team_q_count": team_q_count,
            "eng_q_count": eng_q_count,
            "base_url": base_url,
        },
    )


@router.post("/teams")
def create_team(
    request: Request,
    team_name: str = Form(...),
    member_count: int | None = Form(None),
    db: Session = Depends(get_db),
):
    """Create a new team (form-based, used by admin page)."""
    name = team_name.strip()
    if name:
        existing = db.query(Team).filter(Team.name == name).first()
        if not existing:
            db.add(Team(name=name, member_count=member_count))
            db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/rounds")
def create_round(
    request: Request,
    round_name: str = Form(...),
    db: Session = Depends(get_db),
):
    """Create a new assessment round."""
    name = round_name.strip()
    if name:
        db.add(AssessmentRound(name=name, is_active=True))
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/rounds/{round_id}/toggle")
def toggle_round(round_id: int, db: Session = Depends(get_db)):
    """Toggle a round's active status."""
    rnd = db.get(AssessmentRound, round_id)
    if rnd:
        rnd.is_active = not rnd.is_active
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/teams/{team_id}/edit")
def edit_team(
    team_id: int,
    team_name: str = Form(...),
    member_count: int | None = Form(None),
    db: Session = Depends(get_db),
):
    """Rename a team or update its member count."""
    team = db.get(Team, team_id)
    if team:
        name = team_name.strip()
        if name:
            team.name = name
        team.member_count = member_count
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/teams/{team_id}/delete")
def delete_team(team_id: int, db: Session = Depends(get_db)):
    """Delete a team and all its responses."""
    team = db.get(Team, team_id)
    if team:
        # Cascade: delete all responses (and their answers) for this team
        responses = db.query(Response).filter(Response.team_id == team_id).all()
        for resp in responses:
            db.delete(resp)
        db.delete(team)
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)


# ─── Data Management ────────────────────────────────────────────────────────


@router.get("/data/download-db")
def download_database():
    """Download the SQLite database file."""
    if not DB_PATH.exists():
        return RedirectResponse(url="/admin", status_code=303)
    return FileResponse(
        path=str(DB_PATH),
        media_type="application/x-sqlite3",
        filename="maturity.db",
    )


@router.get("/data/download-questions/{assessment_type}")
def download_questions_csv(assessment_type: str, db: Session = Depends(get_db)):
    """Download questions as CSV (team or engineering)."""
    if assessment_type not in ("team", "engineering"):
        return RedirectResponse(url="/admin", status_code=303)

    questions = (
        db.query(Question)
        .filter(Question.assessment_type == assessment_type)
        .order_by(Question.display_order)
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)

    if assessment_type == "team":
        writer.writerow(["Category", "Subcategory", "Statement"])
        for q in questions:
            writer.writerow([q.category, q.subcategory, q.statement])
    else:
        writer.writerow([
            "Category", "Subcategory", "Area",
            "Base", "Beginner", "Intermediate", "Advanced", "Expert",
        ])
        for q in questions:
            writer.writerow([
                q.category, q.subcategory, q.statement,
                q.level_1 or "", q.level_2 or "", q.level_3 or "",
                q.level_4 or "", q.level_5 or "",
            ])

    output.seek(0)
    filename = f"{assessment_type}_questions.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/data/upload-questions/{assessment_type}")
async def upload_questions_csv(
    assessment_type: str,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload a CSV to replace questions for an assessment type.

    Saves the file to data/ and re-seeds questions from it (force=True).
    """
    if assessment_type not in ("team", "engineering"):
        return RedirectResponse(url="/admin", status_code=303)

    # Save uploaded CSV to data directory
    target = TEAM_CSV if assessment_type == "team" else ENGINEERING_CSV
    content = await file.read()

    # Write to a temp file first, then move (atomic-ish)
    with tempfile.NamedTemporaryFile(
        mode="wb", dir=str(DATA_DIR), delete=False, suffix=".csv"
    ) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    shutil.move(tmp_path, str(target))

    # Re-seed questions from the new CSV
    if assessment_type == "team":
        count = seed_questions(db, force=True)
    else:
        count = seed_engineering_questions(db, force=True)

    return RedirectResponse(url="/admin?upload_success=1&count=" + str(count), status_code=303)


@router.get("/export/{round_id}")
def export_round_csv(round_id: int, db: Session = Depends(get_db)):
    """Export all responses for a round as CSV download."""
    rnd = db.get(AssessmentRound, round_id)
    if not rnd:
        return RedirectResponse(url="/admin", status_code=303)

    questions = db.query(Question).order_by(Question.display_order).all()
    responses = (
        db.query(Response)
        .filter(Response.round_id == round_id)
        .order_by(Response.team_id, Response.submitted_at)
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    header = ["Team", "Respondent", "Submitted At"]
    for q in questions:
        header.append(f"{q.category} | {q.subcategory} | {q.statement[:60]}")
    writer.writerow(header)

    # Data rows
    for resp in responses:
        answer_map = {a.question_id: a.score for a in resp.answers}
        row = [
            resp.team.name,
            resp.respondent_name,
            resp.submitted_at.strftime("%Y-%m-%d %H:%M"),
        ]
        for q in questions:
            row.append(answer_map.get(q.id, ""))
        writer.writerow(row)

    output.seek(0)
    filename = f"maturity_assessment_{rnd.name.replace(' ', '_')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ---------------------------------------------------------------------------
# JSON API endpoints (used by the guided setup flow on the landing page)
# ---------------------------------------------------------------------------


class TeamCreate(BaseModel):
    name: str
    member_count: int | None = None


class RoundCreate(BaseModel):
    name: str


@router.post("/api/teams")
def api_create_team(
    payload: TeamCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    """Create a team and return JSON with the token and survey link."""
    name = payload.name.strip()
    if not name:
        return JSONResponse({"error": "Team name is required"}, status_code=400)

    existing = db.query(Team).filter(Team.name == name).first()
    if existing:
        return JSONResponse({"error": "A team with this name already exists"}, status_code=409)

    team = Team(name=name, member_count=payload.member_count)
    db.add(team)
    db.commit()
    db.refresh(team)

    base_url = str(request.base_url).rstrip("/")
    return {
        "id": team.id,
        "name": team.name,
        "member_count": team.member_count,
        "token": team.token,
        "survey_link": f"{base_url}/survey/{team.token}",
    }


@router.post("/api/rounds")
def api_create_round(
    payload: RoundCreate,
    db: Session = Depends(get_db),
):
    """Create an assessment round and return JSON."""
    name = payload.name.strip()
    if not name:
        return JSONResponse({"error": "Session name is required"}, status_code=400)

    rnd = AssessmentRound(name=name, is_active=True)
    db.add(rnd)
    db.commit()
    db.refresh(rnd)

    return {
        "id": rnd.id,
        "name": rnd.name,
        "is_active": rnd.is_active,
        "engineering_token": rnd.engineering_token,
    }
