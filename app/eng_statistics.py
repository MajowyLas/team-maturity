"""Engineering statistics helpers.

Extracted from app.routes.engineering so they can be shared
across engineering and dashboard routes.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import AssessmentRound, Question, Response, ResponseAnswer

MATURITY_LABELS = {1: "Base", 2: "Beginner", 3: "Intermediate", 4: "Advanced", 5: "Expert"}

MATURITY_DESCRIPTIONS = {
    1: {
        "name": "Base",
        "short": "Foundational practices, mostly manual",
        "description": "Version control and scripted builds exist but processes are largely manual or ad-hoc. "
        "Deployments are semi-manual with rudimentary documentation. Teams work in silos — "
        "Dev, QA, and Ops are separate. Testing is mostly manual and happens late. "
        "The team reacts to problems rather than preventing them.",
    },
    2: {
        "name": "Beginner",
        "short": "Standardizing and removing silos",
        "description": "Teams begin removing organizational boundaries — testing is integrated with development. "
        "Build frequency improves with faster feedback loops. Deployment processes are gradually standardized "
        "with documentation and scripts. Teams stabilize around products instead of projects. "
        "Basic automation exists but is inconsistent across the organization.",
    },
    3: {
        "name": "Intermediate",
        "short": "Cohesive pipeline, cross-functional teams",
        "description": "DBA, CM, and Operations are part of the team or consulted regularly. "
        "Builds trigger on every commit with a cohesive delivery pipeline. "
        "All changes — features, bugs, hotfixes — follow the same path to production. "
        "Practices are mature and consolidated, delivering faster feedback, fewer incidents, "
        "and more predictable delivery.",
    },
    4: {
        "name": "Advanced",
        "short": "Autonomous teams, releases decoupled from deploys",
        "description": "Teams have the competence and confidence to own changes all the way to production. "
        "Releases of functionality are decoupled from deployment — feature flags, dark launches. "
        "A dedicated tools/platform team supports engineering productivity. "
        "Cycle times are short, data-driven decisions are the norm, and automation covers most of the pipeline.",
    },
    5: {
        "name": "Expert",
        "short": "Zero-touch continuous deployment",
        "description": "Every commit can potentially reach production automatically — zero-touch continuous deployment. "
        "The organization adopts roll-forward strategies for production issues with confidence. "
        "Self-healing systems, proactive optimization, and continuous experimentation. "
        "The org sets industry standards rather than following them.",
    },
}


def base_response_filter(query, round_id: int, team_id: int | None = None):
    """Apply common filters for engineering responses (round + optional team)."""
    query = query.filter(
        Response.round_id == round_id,
        Response.assessment_type == "engineering",
    )
    if team_id is not None:
        query = query.filter(Response.team_id == team_id)
    return query


def get_engineering_stats(
    db: Session, round_id: int, team_id: int | None = None
) -> dict | None:
    """Aggregate engineering assessment scores for a round (optionally per team)."""
    count_query = db.query(func.count(Response.id))
    count_query = base_response_filter(count_query, round_id, team_id)
    response_count = count_query.scalar() or 0

    if response_count == 0:
        return None

    # Category averages
    cat_query = (
        db.query(
            Question.category,
            func.avg(ResponseAnswer.score).label("avg_score"),
        )
        .join(ResponseAnswer, ResponseAnswer.question_id == Question.id)
        .join(Response, Response.id == ResponseAnswer.response_id)
        .filter(Question.assessment_type == "engineering")
    )
    cat_query = base_response_filter(cat_query, round_id, team_id)
    category_rows = cat_query.group_by(Question.category).order_by(Question.category).all()

    category_scores = [
        {"category": row.category, "avg": round(row.avg_score, 2)}
        for row in category_rows
    ]

    overall_avg = (
        round(sum(c["avg"] for c in category_scores) / len(category_scores), 2)
        if category_scores
        else 0.0
    )

    # Strengths and weaknesses (by subcategory)
    sub_query = (
        db.query(
            Question.category,
            Question.subcategory,
            func.avg(ResponseAnswer.score).label("avg_score"),
        )
        .join(ResponseAnswer, ResponseAnswer.question_id == Question.id)
        .join(Response, Response.id == ResponseAnswer.response_id)
        .filter(Question.assessment_type == "engineering")
    )
    sub_query = base_response_filter(sub_query, round_id, team_id)
    sub_rows = (
        sub_query
        .group_by(Question.category, Question.subcategory)
        .order_by(func.avg(ResponseAnswer.score))
        .all()
    )

    subcategory_scores = [
        {
            "category": row.category,
            "subcategory": row.subcategory,
            "avg": round(row.avg_score, 2),
        }
        for row in sub_rows
    ]

    strengths = subcategory_scores[-3:][::-1] if len(subcategory_scores) >= 3 else subcategory_scores[::-1]
    improvements = subcategory_scores[:3]

    return {
        "response_count": response_count,
        "overall_avg": overall_avg,
        "overall_label": MATURITY_LABELS.get(round(overall_avg), ""),
        "category_scores": category_scores,
        "subcategory_scores": subcategory_scores,
        "strengths": strengths,
        "improvements": improvements,
    }


def get_area_details(
    db: Session, round_id: int, team_id: int | None = None
) -> list[dict]:
    """Per-question average scores with maturity level labels."""
    detail_query = (
        db.query(
            Question.id,
            Question.category,
            Question.subcategory,
            Question.statement,
            Question.level_1,
            Question.level_2,
            Question.level_3,
            Question.level_4,
            Question.level_5,
            Question.display_order,
            func.avg(ResponseAnswer.score).label("avg_score"),
            func.count(ResponseAnswer.score).label("cnt"),
        )
        .join(ResponseAnswer, ResponseAnswer.question_id == Question.id)
        .join(Response, Response.id == ResponseAnswer.response_id)
        .filter(Question.assessment_type == "engineering")
    )
    detail_query = base_response_filter(detail_query, round_id, team_id)
    rows = (
        detail_query
        .group_by(Question.id)
        .order_by(Question.display_order)
        .all()
    )

    return [
        {
            "question_id": row.id,
            "category": row.category,
            "subcategory": row.subcategory,
            "area": row.statement,
            "avg": round(row.avg_score, 2),
            "count": row.cnt,
            "level_label": MATURITY_LABELS.get(round(row.avg_score), ""),
            "current_description": getattr(row, f"level_{round(row.avg_score)}", ""),
        }
        for row in rows
    ]


def get_engineering_trends(
    db: Session, team_id: int | None = None
) -> dict:
    """Return trend data across rounds for engineering assessment."""
    rounds = db.query(AssessmentRound).order_by(AssessmentRound.id).all()

    if not rounds:
        return {"round_names": [], "categories": {}}

    active_rounds = []
    cat_data: dict[str, list] = {}

    for rnd in rounds:
        stats = get_engineering_stats(db, rnd.id, team_id=team_id)
        if not stats:
            continue
        active_rounds.append(rnd.name)
        cat_map = {c["category"]: c["avg"] for c in stats["category_scores"]}
        for cat, avg in cat_map.items():
            cat_data.setdefault(cat, []).append(avg)

    if len(active_rounds) < 2:
        return {"round_names": [], "categories": {}}

    return {"round_names": active_rounds, "categories": cat_data}
