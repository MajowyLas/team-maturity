"""Score aggregation and executive summary generation."""

from __future__ import annotations

from dataclasses import dataclass
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    AssessmentRound,
    Question,
    Response,
    ResponseAnswer,
    Team,
)


@dataclass(frozen=True)
class StatementScore:
    question_id: int
    category: str
    subcategory: str
    statement: str
    avg: float
    count: int


@dataclass(frozen=True)
class SubcategoryScore:
    category: str
    subcategory: str
    avg: float
    min_score: int
    max_score: int
    count: int


@dataclass(frozen=True)
class CategoryScore:
    category: str
    avg: float
    count: int


@dataclass(frozen=True)
class TeamRoundStats:
    team_id: int
    team_name: str
    round_id: int
    round_name: str
    overall_avg: float
    response_count: int
    category_scores: list[CategoryScore]
    subcategory_scores: list[SubcategoryScore]


@dataclass(frozen=True)
class ExecSummary:
    overall_score: float
    response_count: int
    strengths: list[SubcategoryScore]
    improvements: list[SubcategoryScore]
    previous_overall: float | None
    category_deltas: dict[str, float]  # category -> delta from previous round


def get_team_maturity_overview(
    db: Session, round_id: int
) -> dict | None:
    """Aggregate team maturity scores across ALL teams for a round.

    Returns a dict mirroring the engineering stats structure:
    overall_avg, response_count, category_scores, subcategory_scores,
    strengths (top 3), improvements (bottom 3).
    """
    response_count = (
        db.query(func.count(Response.id))
        .filter(
            Response.round_id == round_id,
            Response.assessment_type == "team",
        )
        .scalar()
    ) or 0

    if response_count == 0:
        return None

    # Category averages
    category_rows = (
        db.query(
            Question.category,
            func.avg(ResponseAnswer.score).label("avg_score"),
        )
        .join(ResponseAnswer, ResponseAnswer.question_id == Question.id)
        .join(Response, Response.id == ResponseAnswer.response_id)
        .filter(
            Response.round_id == round_id,
            Response.assessment_type == "team",
            Question.assessment_type == "team",
        )
        .group_by(Question.category)
        .order_by(Question.category)
        .all()
    )

    category_scores = [
        {"category": row.category, "avg": round(row.avg_score, 2)}
        for row in category_rows
    ]

    overall_avg = (
        round(sum(c["avg"] for c in category_scores) / len(category_scores), 2)
        if category_scores
        else 0.0
    )

    # Subcategory scores for strengths/improvements
    sub_rows = (
        db.query(
            Question.category,
            Question.subcategory,
            func.avg(ResponseAnswer.score).label("avg_score"),
        )
        .join(ResponseAnswer, ResponseAnswer.question_id == Question.id)
        .join(Response, Response.id == ResponseAnswer.response_id)
        .filter(
            Response.round_id == round_id,
            Response.assessment_type == "team",
            Question.assessment_type == "team",
        )
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

    # ── Previous round comparison ──
    previous_round = (
        db.query(AssessmentRound)
        .filter(AssessmentRound.id < round_id)
        .order_by(AssessmentRound.id.desc())
        .first()
    )

    previous_overall: float | None = None
    category_deltas: dict[str, float] = {}

    if previous_round:
        prev = get_team_maturity_overview(db, previous_round.id)
        if prev:
            previous_overall = prev["overall_avg"]
            prev_cat_map = {c["category"]: c["avg"] for c in prev["category_scores"]}
            for cat in category_scores:
                if cat["category"] in prev_cat_map:
                    category_deltas[cat["category"]] = round(
                        cat["avg"] - prev_cat_map[cat["category"]], 2
                    )

    return {
        "response_count": response_count,
        "overall_avg": overall_avg,
        "category_scores": category_scores,
        "subcategory_scores": subcategory_scores,
        "strengths": strengths,
        "improvements": improvements,
        "previous_overall": previous_overall,
        "category_deltas": category_deltas,
    }


def get_team_round_stats(
    db: Session, team_id: int, round_id: int
) -> TeamRoundStats | None:
    """Compute aggregated scores for a team in a specific round."""
    team = db.get(Team, team_id)
    rnd = db.get(AssessmentRound, round_id)
    if not team or not rnd:
        return None

    # Count responses (team survey only — exclude engineering)
    response_count = (
        db.query(func.count(Response.id))
        .filter(
            Response.team_id == team_id,
            Response.round_id == round_id,
            Response.assessment_type == "team",
        )
        .scalar()
    ) or 0

    if response_count == 0:
        return TeamRoundStats(
            team_id=team_id,
            team_name=team.name,
            round_id=round_id,
            round_name=rnd.name,
            overall_avg=0.0,
            response_count=0,
            category_scores=[],
            subcategory_scores=[],
        )

    # Subcategory scores (team survey only)
    subcategory_rows = (
        db.query(
            Question.category,
            Question.subcategory,
            func.avg(ResponseAnswer.score).label("avg_score"),
            func.min(ResponseAnswer.score).label("min_score"),
            func.max(ResponseAnswer.score).label("max_score"),
            func.count(ResponseAnswer.score).label("cnt"),
        )
        .join(ResponseAnswer, ResponseAnswer.question_id == Question.id)
        .join(Response, Response.id == ResponseAnswer.response_id)
        .filter(
            Response.team_id == team_id,
            Response.round_id == round_id,
            Response.assessment_type == "team",
            Question.assessment_type == "team",
        )
        .group_by(Question.category, Question.subcategory)
        .order_by(Question.category, Question.subcategory)
        .all()
    )

    subcategory_scores = [
        SubcategoryScore(
            category=row.category,
            subcategory=row.subcategory,
            avg=round(row.avg_score, 2),
            min_score=row.min_score,
            max_score=row.max_score,
            count=row.cnt,
        )
        for row in subcategory_rows
    ]

    # Category scores (team survey only)
    category_rows = (
        db.query(
            Question.category,
            func.avg(ResponseAnswer.score).label("avg_score"),
            func.count(ResponseAnswer.score).label("cnt"),
        )
        .join(ResponseAnswer, ResponseAnswer.question_id == Question.id)
        .join(Response, Response.id == ResponseAnswer.response_id)
        .filter(
            Response.team_id == team_id,
            Response.round_id == round_id,
            Response.assessment_type == "team",
            Question.assessment_type == "team",
        )
        .group_by(Question.category)
        .order_by(Question.category)
        .all()
    )

    category_scores = [
        CategoryScore(
            category=row.category,
            avg=round(row.avg_score, 2),
            count=row.cnt,
        )
        for row in category_rows
    ]

    overall_avg = (
        round(sum(c.avg for c in category_scores) / len(category_scores), 2)
        if category_scores
        else 0.0
    )

    return TeamRoundStats(
        team_id=team_id,
        team_name=team.name,
        round_id=round_id,
        round_name=rnd.name,
        overall_avg=overall_avg,
        response_count=response_count,
        category_scores=category_scores,
        subcategory_scores=subcategory_scores,
    )


def get_exec_summary(
    db: Session, team_id: int, round_id: int
) -> ExecSummary | None:
    """Generate an executive summary for a team in a round.

    Includes top 3 strengths, top 3 improvement areas, and
    comparison with the previous round (if any).
    """
    stats = get_team_round_stats(db, team_id, round_id)
    if not stats or stats.response_count == 0:
        return None

    sorted_by_score = sorted(stats.subcategory_scores, key=lambda s: s.avg)
    strengths = sorted_by_score[-3:][::-1]  # top 3, descending
    improvements = sorted_by_score[:3]  # bottom 3, ascending

    # Find previous round for comparison
    previous_round = (
        db.query(AssessmentRound)
        .filter(AssessmentRound.id < round_id)
        .order_by(AssessmentRound.id.desc())
        .first()
    )

    previous_overall: float | None = None
    category_deltas: dict[str, float] = {}

    if previous_round:
        prev_stats = get_team_round_stats(db, team_id, previous_round.id)
        if prev_stats and prev_stats.response_count > 0:
            previous_overall = prev_stats.overall_avg
            prev_cat_map = {c.category: c.avg for c in prev_stats.category_scores}
            for cat in stats.category_scores:
                if cat.category in prev_cat_map:
                    category_deltas[cat.category] = round(
                        cat.avg - prev_cat_map[cat.category], 2
                    )

    return ExecSummary(
        overall_score=stats.overall_avg,
        response_count=stats.response_count,
        strengths=strengths,
        improvements=improvements,
        previous_overall=previous_overall,
        category_deltas=category_deltas,
    )


def get_overview_cards(
    db: Session, round_id: int
) -> list[dict]:
    """Return card data for each team: summary stats for the overview page."""
    teams = db.query(Team).order_by(Team.name).all()

    cards = []
    for team in teams:
        stats = get_team_round_stats(db, team.id, round_id)
        summary = get_exec_summary(db, team.id, round_id)

        card: dict = {
            "team_id": team.id,
            "team_name": team.name,
            "overall": 0.0,
            "response_count": 0,
            "top_strength": None,
            "top_improvement": None,
            "category_scores": [],
        }

        if stats and stats.response_count > 0:
            card["overall"] = stats.overall_avg
            card["response_count"] = stats.response_count
            card["category_scores"] = [
                {"category": c.category, "avg": c.avg}
                for c in stats.category_scores
            ]

        if summary:
            if summary.strengths:
                s = summary.strengths[0]
                card["top_strength"] = {"name": s.subcategory, "avg": s.avg}
            if summary.improvements:
                i = summary.improvements[0]
                card["top_improvement"] = {"name": i.subcategory, "avg": i.avg}

        cards.append(card)

    return cards


def get_statement_scores(
    db: Session, team_id: int | None, round_id: int
) -> list[StatementScore]:
    """Return average score per individual statement for a round.

    When *team_id* is provided, results are scoped to that team.
    When *team_id* is ``None``, results are department-wide (all teams).

    Ordered by question display_order so they group naturally by
    category -> subcategory.
    """
    q = (
        db.query(
            Question.id,
            Question.category,
            Question.subcategory,
            Question.statement,
            Question.display_order,
            func.avg(ResponseAnswer.score).label("avg_score"),
            func.count(ResponseAnswer.score).label("cnt"),
        )
        .join(ResponseAnswer, ResponseAnswer.question_id == Question.id)
        .join(Response, Response.id == ResponseAnswer.response_id)
        .filter(
            Response.round_id == round_id,
            Response.assessment_type == "team",
            Question.assessment_type == "team",
        )
    )
    if team_id is not None:
        q = q.filter(Response.team_id == team_id)
    rows = q.group_by(Question.id).order_by(Question.display_order).all()

    return [
        StatementScore(
            question_id=row.id,
            category=row.category,
            subcategory=row.subcategory,
            statement=row.statement,
            avg=round(row.avg_score, 2),
            count=row.cnt,
        )
        for row in rows
    ]


def get_overview_trends(
    db: Session,
) -> dict:
    """Return overall-score trends for every team across all rounds.

    Returns {
        "round_names": ["Round 1", "Round 2", ...],
        "teams": [
            {"name": "Team A", "scores": [3.2, 3.5, ...]},
            ...
        ]
    }
    Only includes rounds where at least one team has data.
    """
    rounds = db.query(AssessmentRound).order_by(AssessmentRound.id).all()
    teams = db.query(Team).order_by(Team.name).all()

    if not rounds or not teams:
        return {"round_names": [], "teams": []}

    # Build a matrix: team -> round -> overall_avg
    team_round_scores: dict[int, dict[int, float]] = {}
    active_round_ids: set[int] = set()

    for team in teams:
        team_round_scores[team.id] = {}
        for rnd in rounds:
            stats = get_team_round_stats(db, team.id, rnd.id)
            if stats and stats.response_count > 0:
                team_round_scores[team.id][rnd.id] = stats.overall_avg
                active_round_ids.add(rnd.id)

    # Only keep rounds that have at least one team with data
    active_rounds = [r for r in rounds if r.id in active_round_ids]

    if len(active_rounds) < 2:
        return {"round_names": [], "teams": []}

    round_names = [r.name for r in active_rounds]
    team_series = []
    for team in teams:
        scores = []
        has_any = False
        for rnd in active_rounds:
            val = team_round_scores[team.id].get(rnd.id)
            scores.append(val)
            if val is not None:
                has_any = True
        if has_any:
            team_series.append({"name": team.name, "scores": scores})

    return {"round_names": round_names, "teams": team_series}


def get_team_trends(
    db: Session, team_id: int
) -> dict[str, list[dict]]:
    """Return trend data across all rounds for a team.

    Returns {category: [{round_name, avg}, ...]} for line charts.
    """
    rounds = db.query(AssessmentRound).order_by(AssessmentRound.id).all()
    categories = (
        db.query(Question.category)
        .distinct()
        .order_by(Question.category)
        .all()
    )
    cat_names = [c[0] for c in categories]

    trends: dict[str, list[dict]] = {cat: [] for cat in cat_names}

    for rnd in rounds:
        stats = get_team_round_stats(db, team_id, rnd.id)
        if not stats or stats.response_count == 0:
            continue
        cat_map = {c.category: c.avg for c in stats.category_scores}
        for cat in cat_names:
            if cat in cat_map:
                trends[cat].append(
                    {"round_name": rnd.name, "round_id": rnd.id, "avg": cat_map[cat]}
                )

    return trends
