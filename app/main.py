"""FastAPI application entry point and CLI for Team Maturity Assessment."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import (
    APP_PASSWORD,
    AuthMiddleware,
    clear_auth_cookie,
    set_auth_cookie,
)
from app.database import SessionLocal, get_db, init_db
from app.models import AssessmentRound, Team
from app.routes import admin, dashboard, engineering, survey
from app.seed import seed_engineering_questions, seed_questions

APP_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables and seed questions from CSV."""
    init_db()
    db = SessionLocal()
    try:
        team_count = seed_questions(db)
        eng_count = seed_engineering_questions(db)
        print(f"[OK] Database ready - {team_count} team + {eng_count} engineering questions loaded")
    finally:
        db.close()
    yield


app = FastAPI(
    title="Team Maturity Assessment",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount static files
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

# Auth middleware (only active when APP_PASSWORD is set)
app.add_middleware(AuthMiddleware)

# Include routers
app.include_router(survey.router)
app.include_router(dashboard.router)
app.include_router(admin.router)
app.include_router(engineering.router)

# Templates for the landing page
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

# Make auth_enabled available in ALL template instances (for showing logout link)
_auth_enabled = APP_PASSWORD is not None
_all_templates = (templates, survey.templates, dashboard.templates, admin.templates, engineering.templates)
for _tpl in _all_templates:
    _tpl.env.globals["auth_enabled"] = _auth_enabled
    _tpl.env.auto_reload = True


def _get_nav_teams() -> list:
    """Fetch teams for the nav dropdown (called on each render)."""
    db = SessionLocal()
    try:
        return db.query(Team).order_by(Team.name).all()
    finally:
        db.close()


# Register a Jinja2 global function so nav can call it
for _tpl in _all_templates:
    _tpl.env.globals["get_nav_teams"] = _get_nav_teams


@app.get("/")
def landing_page(request: Request, db: Session = Depends(get_db)):
    """Landing page with guided setup flow.

    Passes teams, rounds, and base_url so the template can render the
    appropriate step: create team → create session → share link.
    """
    teams = db.query(Team).order_by(Team.name).all()
    rounds = (
        db.query(AssessmentRound)
        .order_by(AssessmentRound.created_at.desc())
        .all()
    )
    base_url = str(request.base_url).rstrip("/")

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "teams": teams,
            "rounds": rounds,
            "base_url": base_url,
        },
    )


# ─── Login / Logout ──────────────────────────────────────────────────────────

@app.get("/login")
def login_page(request: Request, next: str = Query("/")):
    """Show the login form."""
    return templates.TemplateResponse(
        "login.html", {"request": request, "next_url": next, "error": False}
    )


@app.post("/login")
def login_submit(
    request: Request,
    password: str = Form(...),
    next: str = Form("/"),
):
    """Validate password and set auth cookie."""
    if APP_PASSWORD is not None and password == APP_PASSWORD:
        response = RedirectResponse(url=next, status_code=302)
        set_auth_cookie(response)
        return response

    # Wrong password → re-render with error
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "next_url": next, "error": True},
        status_code=401,
    )


@app.get("/logout")
def logout():
    """Clear auth cookie and redirect to login."""
    response = RedirectResponse(url="/login", status_code=302)
    clear_auth_cookie(response)
    return response


def cli():
    """CLI entry point: `team-maturity` starts the server."""
    import os

    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    print("=" * 50)
    print("  Team Maturity Assessment Tool")
    print(f"  Starting on http://localhost:{port}")
    print("=" * 50)
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    cli()
