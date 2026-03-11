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
    strengths: list[CategoryScore]
    improvements: list[CategoryScore]
    previous_overall: float | None
    category_deltas: dict[str, float]  # category -> delta from previous round


# ---------------------------------------------------------------------------
# Bulk aggregation helpers — reduce dashboard load from O(teams×rounds) to O(1)
# ---------------------------------------------------------------------------


def _bulk_response_counts(db: Session) -> dict[tuple[int, int], int]:
    """Return {(team_id, round_id): response_count} for all team/round pairs."""
    rows = (
        db.query(
            Response.team_id,
            Response.round_id,
            func.count(Response.id).label("cnt"),
        )
        .group_by(Response.team_id, Response.round_id)
        .all()
    )
    return {(r.team_id, r.round_id): r.cnt for r in rows}


def _bulk_category_scores(
    db: Session,
) -> dict[tuple[int, int], list[CategoryScore]]:
    """Return {(team_id, round_id): [CategoryScore]} for all team/round pairs."""
    rows = (
        db.query(
            Response.team_id,
            Response.round_id,
            Question.category,
            func.avg(ResponseAnswer.score).label("avg_score"),
            func.count(ResponseAnswer.score).label("cnt"),
        )
        .join(ResponseAnswer, ResponseAnswer.response_id == Response.id)
        .join(Question, Question.id == ResponseAnswer.question_id)
        .group_by(Response.team_id, Response.round_id, Question.category)
        .order_by(Response.team_id, Response.round_id, Question.category)
        .all()
    )
    result: dict[tuple[int, int], list[CategoryScore]] = {}
    for row in rows:
        key = (row.team_id, row.round_id)
        result.setdefault(key, []).append(
            CategoryScore(
                category=row.category,
                avg=round(row.avg_score, 2),
                count=row.cnt,
            )
        )
    return result


def _weighted_overall(cat_scores: list[CategoryScore]) -> float:
    """Compute true weighted average across all answers (T2 fix for overview fns)."""
    total_count = sum(c.count for c in cat_scores)
    if not total_count:
        return 0.0
    return round(sum(c.avg * c.count for c in cat_scores) / total_count, 2)


# ---------------------------------------------------------------------------
# Single-team detail — used by per-team dashboard views
# ---------------------------------------------------------------------------


def get_team_round_stats(
    db: Session, team_id: int, round_id: int
) -> TeamRoundStats | None:
    """Compute aggregated scores for a team in a specific round."""
    team = db.get(Team, team_id)
    rnd = db.get(AssessmentRound, round_id)
    if not team or not rnd:
        return None

    # Count responses
    response_count = (
        db.query(func.count(Response.id))
        .filter(Response.team_id == team_id, Response.round_id == round_id)
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

    # Subcategory scores
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
        .filter(Response.team_id == team_id, Response.round_id == round_id)
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

    # Category scores
    category_rows = (
        db.query(
            Question.category,
            func.avg(ResponseAnswer.score).label("avg_score"),
            func.count(ResponseAnswer.score).label("cnt"),
        )
        .join(ResponseAnswer, ResponseAnswer.question_id == Question.id)
        .join(Response, Response.id == ResponseAnswer.response_id)
        .filter(Response.team_id == team_id, Response.round_id == round_id)
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

    # T2 fix: true weighted average across all answers (not average of category averages)
    _overall_raw = (
        db.query(func.avg(ResponseAnswer.score))
        .join(Response, Response.id == ResponseAnswer.response_id)
        .filter(Response.team_id == team_id, Response.round_id == round_id)
        .scalar()
    )
    overall_avg = round(_overall_raw, 2) if _overall_raw is not None else 0.0

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

    sorted_by_score = sorted(stats.category_scores, key=lambda s: s.avg)
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


# ---------------------------------------------------------------------------
# Overview functions — refactored to use bulk helpers (T1 fix)
# ---------------------------------------------------------------------------


def get_overview_cards(
    db: Session, round_id: int
) -> list[dict]:
    """Return card data for each team: summary stats for the overview page.

    Uses two bulk queries instead of per-team calls (T1 fix).
    """
    teams = db.query(Team).order_by(Team.name).all()

    # Bulk response counts for this round only
    count_rows = (
        db.query(
            Response.team_id,
            func.count(Response.id).label("cnt"),
        )
        .filter(Response.round_id == round_id)
        .group_by(Response.team_id)
        .all()
    )
    response_counts: dict[int, int] = {r.team_id: r.cnt for r in count_rows}

    # Bulk category scores for this round only
    cat_rows = (
        db.query(
            Response.team_id,
            Question.category,
            func.avg(ResponseAnswer.score).label("avg_score"),
            func.count(ResponseAnswer.score).label("cnt"),
        )
        .join(ResponseAnswer, ResponseAnswer.response_id == Response.id)
        .join(Question, Question.id == ResponseAnswer.question_id)
        .filter(Response.round_id == round_id)
        .group_by(Response.team_id, Question.category)
        .all()
    )

    cat_map: dict[int, list[CategoryScore]] = {}
    for row in cat_rows:
        cat_map.setdefault(row.team_id, []).append(
            CategoryScore(
                category=row.category,
                avg=round(row.avg_score, 2),
                count=row.cnt,
            )
        )

    cards = []
    for team in teams:
        resp_count = response_counts.get(team.id, 0)
        cat_scores = sorted(cat_map.get(team.id, []), key=lambda c: c.category)

        card: dict = {
            "team_id": team.id,
            "team_name": team.name,
            "overall": 0.0,
            "response_count": resp_count,
            "top_strength": None,
            "top_improvement": None,
            "category_scores": [],
        }

        if resp_count > 0 and cat_scores:
            card["overall"] = _weighted_overall(cat_scores)
            card["category_scores"] = [
                {"category": c.category, "avg": c.avg} for c in cat_scores
            ]
            sorted_cats = sorted(cat_scores, key=lambda c: c.avg)
            s = sorted_cats[-1]
            card["top_strength"] = {"name": s.category, "avg": s.avg}
            i = sorted_cats[0]
            card["top_improvement"] = {"name": i.category, "avg": i.avg}

        cards.append(card)

    return cards


def get_statement_scores(
    db: Session, team_id: int, round_id: int
) -> list[StatementScore]:
    """Return average score per individual statement for a team in a round.

    Ordered by question display_order so they group naturally by
    category -> subcategory.
    """
    rows = (
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
        .filter(Response.team_id == team_id, Response.round_id == round_id)
        .group_by(Question.id)
        .order_by(Question.display_order)
        .all()
    )

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
    Uses bulk queries instead of per-team/round calls (T1 fix).
    """
    rounds = db.query(AssessmentRound).order_by(AssessmentRound.id).all()
    teams = db.query(Team).order_by(Team.name).all()

    if not rounds or not teams:
        return {"round_names": [], "teams": []}

    response_counts = _bulk_response_counts(db)
    cat_scores_map = _bulk_category_scores(db)

    # Compute overall score per (team, round) as weighted average
    overall: dict[tuple[int, int], float] = {}
    for key, cats in cat_scores_map.items():
        if response_counts.get(key, 0) > 0:
            overall[key] = _weighted_overall(cats)

    # Only keep rounds that have at least one team with data
    active_round_ids: set[int] = {round_id for (_, round_id) in overall}
    active_rounds = [r for r in rounds if r.id in active_round_ids]

    if len(active_rounds) < 2:
        return {"round_names": [], "teams": []}

    round_names = [r.name for r in active_rounds]
    team_series = []
    for team in teams:
        scores = []
        has_any = False
        for rnd in active_rounds:
            val = overall.get((team.id, rnd.id))
            scores.append(val)
            if val is not None:
                has_any = True
        if has_any:
            team_series.append({"name": team.name, "scores": scores})

    return {"round_names": round_names, "teams": team_series}


def get_all_teams_trend_summary(db: Session) -> list[dict]:
    """Return latest score and delta vs previous round for every team that has data.

    Each entry:
        team_id, team_name, latest_score, latest_round,
        previous_score, previous_round, delta (None if only one round exists)
    Uses bulk queries instead of per-team/round calls (T1 fix).
    """
    teams = db.query(Team).order_by(Team.name).all()
    rounds = db.query(AssessmentRound).order_by(AssessmentRound.id).all()

    response_counts = _bulk_response_counts(db)
    cat_scores_map = _bulk_category_scores(db)

    # Compute overall score per (team, round)
    overall: dict[tuple[int, int], float] = {}
    for key, cats in cat_scores_map.items():
        if response_counts.get(key, 0) > 0:
            overall[key] = _weighted_overall(cats)

    result = []
    for team in teams:
        scored_rounds = []
        for rnd in rounds:
            key = (team.id, rnd.id)
            if key in overall:
                cat_scores = cat_scores_map.get(key, [])
                scored_rounds.append(
                    {
                        "round_name": rnd.name,
                        "score": overall[key],
                        "category_scores": [
                            {"category": c.category, "avg": c.avg}
                            for c in cat_scores
                        ],
                    }
                )

        if not scored_rounds:
            continue

        latest = scored_rounds[-1]
        previous = scored_rounds[-2] if len(scored_rounds) >= 2 else None
        delta = (
            round(latest["score"] - previous["score"], 2) if previous else None
        )

        # Per-category deltas vs previous round
        category_deltas: dict[str, float] = {}
        if previous:
            prev_cat_map = {c["category"]: c["avg"] for c in previous["category_scores"]}
            for cat in latest["category_scores"]:
                if cat["category"] in prev_cat_map:
                    category_deltas[cat["category"]] = round(
                        cat["avg"] - prev_cat_map[cat["category"]], 2
                    )

        result.append(
            {
                "team_id": team.id,
                "team_name": team.name,
                "latest_score": latest["score"],
                "latest_round": latest["round_name"],
                "previous_score": previous["score"] if previous else None,
                "previous_round": previous["round_name"] if previous else None,
                "delta": delta,
                "category_scores": latest["category_scores"],
                "category_deltas": category_deltas,
            }
        )

    return result


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
