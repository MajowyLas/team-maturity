"""Seed realistic mock data into the team-maturity-assessment SQLite database.

Usage:
    python seed_mock_data.py

Creates assessment rounds, teams, and survey responses with realistic
score distributions and cross-round improvement trends.
"""

import random
import sys
from datetime import datetime, timedelta, timezone

# Ensure app package is importable
sys.path.insert(0, ".")

from app.database import SessionLocal, init_db
from app.models import (
    AssessmentRound,
    Question,
    Response,
    ResponseAnswer,
    Team,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TEAMS = {
    "API": {"members": 8, "profile": "strong_technical"},
    "Checkout": {"members": 7, "profile": "strong_responsiveness"},
    "Search": {"members": 6, "profile": "strong_improvement"},
    "Platform": {"members": 10, "profile": "balanced_weak"},
}

POLISH_NAMES = [
    "Jan Kowalski",
    "Anna Nowak",
    "Piotr Wisniewski",
    "Katarzyna Wojcik",
    "Tomasz Kaminski",
    "Magdalena Lewandowska",
    "Marcin Zielinski",
    "Agnieszka Szymanska",
    "Krzysztof Wozniak",
    "Joanna Dabrowski",
    "Michal Kozlowski",
    "Monika Jankowska",
    "Lukasz Mazur",
    "Ewa Krawczyk",
    "Adam Piotrowicz",
    "Marta Grabowska",
    "Jakub Pawlak",
    "Natalia Michalska",
    "Rafal Krol",
    "Karolina Wieczorek",
    "Dawid Jablonski",
    "Aleksandra Majewska",
    "Sebastian Olszewski",
    "Dorota Stępień",
    "Grzegorz Malinowski",
    "Izabela Dudek",
    "Kamil Gorski",
    "Patrycja Rutkowska",
    "Robert Sikora",
    "Weronika Baran",
    "Damian Szczepanski",
    "Sylwia Olejniczak",
]

ENGINEERING_NAMES = [
    "Marek Witkowski",
    "Beata Zawadzka",
    "Artur Kaczmarek",
    "Paulina Sadowska",
    "Bartosz Bak",
    "Renata Chmielewska",
    "Szymon Borkowski",
    "Justyna Urbanska",
    "Filip Przybylski",
    "Iwona Walczak",
]

# ---------------------------------------------------------------------------
# Team-survey score profiles per category (base averages for Q4 2025)
# Each profile maps category -> (mean, stddev)
# Scores are Likert 1-5.
# ---------------------------------------------------------------------------

TEAM_CATEGORY_PROFILES = {
    "strong_technical": {
        # Strong on Release Automation, Refinement; weaker on Autonomy, Stakeholders
        "Responsiveness": (4.0, 0.6),
        "Continuous Improvement": (3.5, 0.7),
        "Stakeholders": (2.8, 0.8),
        "Team Autonomy": (2.6, 0.9),
        "Team Effectiveness": (3.2, 0.7),
        "Management Support": (3.4, 0.6),
    },
    "strong_responsiveness": {
        # Checkout: great release cadence & stakeholders, weak autonomy
        "Responsiveness": (4.2, 0.5),
        "Continuous Improvement": (3.0, 0.8),
        "Stakeholders": (3.8, 0.6),
        "Team Autonomy": (2.5, 0.9),
        "Team Effectiveness": (3.6, 0.6),
        "Management Support": (3.0, 0.7),
    },
    "strong_improvement": {
        # Search: strong CI culture, weaker on stakeholder engagement
        "Responsiveness": (3.0, 0.7),
        "Continuous Improvement": (4.1, 0.5),
        "Stakeholders": (2.7, 0.8),
        "Team Autonomy": (3.5, 0.7),
        "Team Effectiveness": (3.3, 0.6),
        "Management Support": (3.2, 0.7),
    },
    "balanced_weak": {
        # Platform: large team, consistently below-average
        "Responsiveness": (2.8, 0.8),
        "Continuous Improvement": (2.5, 0.9),
        "Stakeholders": (2.6, 0.8),
        "Team Autonomy": (2.9, 0.8),
        "Team Effectiveness": (2.7, 0.9),
        "Management Support": (2.4, 0.8),
    },
}

# Engineering score profiles per category (base averages for Q4 2025)
ENGINEERING_CATEGORY_PROFILES = {
    "Build & Integration": (3.5, 0.7),
    "Test & Verification": (3.0, 0.8),
    "Deploy & Release": (2.8, 0.9),
    "Architecture & Design": (3.2, 0.7),
    "Infrastructure & Environments": (2.2, 0.9),
    "Process & Flow": (2.6, 0.8),
    "Culture & Organization": (3.3, 0.6),
}

# Q1 2026 improvement delta (added to means)
IMPROVEMENT_DELTA = 0.3


def _clamp_score(value: float) -> int:
    """Clamp a float to integer score in [1, 5]."""
    return max(1, min(5, round(value)))


def _generate_score(mean: float, std: float) -> int:
    """Generate a single Likert/rubric score from a normal distribution."""
    return _clamp_score(random.gauss(mean, std))


# ---------------------------------------------------------------------------
# Main seeding logic
# ---------------------------------------------------------------------------


def seed_mock_data() -> None:
    init_db()
    db = SessionLocal()

    try:
        summary: dict[str, int] = {
            "rounds_created": 0,
            "teams_created": 0,
            "team_responses": 0,
            "team_answers": 0,
            "eng_responses": 0,
            "eng_answers": 0,
        }

        # -- 1. Assessment rounds ------------------------------------------------
        round_q4 = (
            db.query(AssessmentRound)
            .filter(AssessmentRound.name == "Q4 2025")
            .first()
        )
        if not round_q4:
            round_q4 = AssessmentRound(name="Q4 2025", is_active=False)
            db.add(round_q4)
            db.flush()
            summary["rounds_created"] += 1
            print(f"  Created round: Q4 2025 (id={round_q4.id}, closed)")
        else:
            # Ensure it's closed
            round_q4.is_active = False
            print(f"  Reusing round: Q4 2025 (id={round_q4.id})")

        round_q1 = (
            db.query(AssessmentRound)
            .filter(AssessmentRound.name == "Q1 2026")
            .first()
        )
        if not round_q1:
            round_q1 = AssessmentRound(name="Q1 2026", is_active=True)
            db.add(round_q1)
            db.flush()
            summary["rounds_created"] += 1
            print(f"  Created round: Q1 2026 (id={round_q1.id}, active)")
        else:
            round_q1.is_active = True
            print(f"  Reusing round: Q1 2026 (id={round_q1.id})")

        rounds = [
            (round_q4, 0.0),  # no improvement delta for Q4
            (round_q1, IMPROVEMENT_DELTA),
        ]

        # -- 2. Teams ------------------------------------------------------------
        team_objects: dict[str, Team] = {}
        for team_name, cfg in TEAMS.items():
            team = db.query(Team).filter(Team.name == team_name).first()
            if not team:
                team = Team(name=team_name, member_count=cfg["members"])
                db.add(team)
                db.flush()
                summary["teams_created"] += 1
                print(f"  Created team: {team_name} (id={team.id}, {cfg['members']} members)")
            else:
                print(f"  Reusing team: {team_name} (id={team.id})")
            team_objects[team_name] = team

        # -- 3. Load questions ---------------------------------------------------
        team_questions = (
            db.query(Question)
            .filter(Question.assessment_type == "team")
            .order_by(Question.display_order)
            .all()
        )
        eng_questions = (
            db.query(Question)
            .filter(Question.assessment_type == "engineering")
            .order_by(Question.display_order)
            .all()
        )

        if not team_questions:
            print("ERROR: No team questions found. Run the app first to seed questions.")
            return
        if not eng_questions:
            print("WARNING: No engineering questions found. Skipping engineering responses.")

        # Group questions by category for profile-based scoring
        team_q_by_cat: dict[str, list[Question]] = {}
        for q in team_questions:
            team_q_by_cat.setdefault(q.category, []).append(q)

        eng_q_by_cat: dict[str, list[Question]] = {}
        for q in eng_questions:
            eng_q_by_cat.setdefault(q.category, []).append(q)

        # -- 4. Team survey responses --------------------------------------------
        name_pool = list(POLISH_NAMES)

        for round_obj, delta in rounds:
            # Check if this round already has team responses
            existing_team_resp = (
                db.query(Response)
                .filter(
                    Response.round_id == round_obj.id,
                    Response.assessment_type == "team",
                )
                .count()
            )
            if existing_team_resp > 0:
                print(
                    f"  Skipping team responses for {round_obj.name} "
                    f"({existing_team_resp} already exist)"
                )
                continue

            # Timestamp range for this round
            if "Q4" in round_obj.name:
                base_date = datetime(2025, 12, 10, tzinfo=timezone.utc)
            else:
                base_date = datetime(2026, 3, 15, tzinfo=timezone.utc)

            for team_name, team_obj in team_objects.items():
                profile_key = TEAMS[team_name]["profile"]
                profile = TEAM_CATEGORY_PROFILES[profile_key]
                num_respondents = random.randint(3, 6)

                # Pick unique names for this team+round
                chosen_names = random.sample(name_pool, num_respondents)

                for i, respondent in enumerate(chosen_names):
                    submitted = base_date + timedelta(
                        days=random.randint(0, 5),
                        hours=random.randint(8, 17),
                        minutes=random.randint(0, 59),
                    )
                    resp = Response(
                        round_id=round_obj.id,
                        team_id=team_obj.id,
                        respondent_name=respondent,
                        assessment_type="team",
                        submitted_at=submitted,
                    )
                    db.add(resp)
                    db.flush()

                    # Generate answers for every team question
                    for cat, questions in team_q_by_cat.items():
                        mean, std = profile.get(cat, (3.0, 0.8))
                        adjusted_mean = mean + delta
                        for q in questions:
                            score = _generate_score(adjusted_mean, std)
                            db.add(
                                ResponseAnswer(
                                    response_id=resp.id,
                                    question_id=q.id,
                                    score=score,
                                )
                            )
                            summary["team_answers"] += 1

                    summary["team_responses"] += 1

                print(
                    f"  {round_obj.name} / {team_name}: "
                    f"{num_respondents} respondents, {len(team_questions)} answers each"
                )

        # -- 5. Engineering assessment responses ----------------------------------
        if eng_questions:
            for round_obj, delta in rounds:
                existing_eng_resp = (
                    db.query(Response)
                    .filter(
                        Response.round_id == round_obj.id,
                        Response.assessment_type == "engineering",
                    )
                    .count()
                )
                if existing_eng_resp > 0:
                    print(
                        f"  Skipping engineering responses for {round_obj.name} "
                        f"({existing_eng_resp} already exist)"
                    )
                    continue

                if "Q4" in round_obj.name:
                    base_date = datetime(2025, 12, 12, tzinfo=timezone.utc)
                else:
                    base_date = datetime(2026, 3, 18, tzinfo=timezone.utc)

                num_eng = random.randint(5, 8)
                chosen_eng = random.sample(ENGINEERING_NAMES, num_eng)

                # Distribute engineering respondents across teams
                team_list = list(team_objects.values())

                for idx, respondent in enumerate(chosen_eng):
                    submitted = base_date + timedelta(
                        days=random.randint(0, 4),
                        hours=random.randint(9, 16),
                        minutes=random.randint(0, 59),
                    )
                    assigned_team = team_list[idx % len(team_list)]
                    resp = Response(
                        round_id=round_obj.id,
                        team_id=assigned_team.id,
                        respondent_name=respondent,
                        assessment_type="engineering",
                        submitted_at=submitted,
                    )
                    db.add(resp)
                    db.flush()

                    for cat, questions in eng_q_by_cat.items():
                        mean, std = ENGINEERING_CATEGORY_PROFILES.get(
                            cat, (3.0, 0.8)
                        )
                        adjusted_mean = mean + delta
                        for q in questions:
                            score = _generate_score(adjusted_mean, std)
                            db.add(
                                ResponseAnswer(
                                    response_id=resp.id,
                                    question_id=q.id,
                                    score=score,
                                )
                            )
                            summary["eng_answers"] += 1

                    summary["eng_responses"] += 1

                print(
                    f"  {round_obj.name} / Engineering: "
                    f"{num_eng} respondents, {len(eng_questions)} answers each"
                )

        db.commit()

        # -- Summary -------------------------------------------------------------
        print("\n--- Seed Summary ---")
        print(f"  Rounds created:            {summary['rounds_created']}")
        print(f"  Teams created:             {summary['teams_created']}")
        print(f"  Team responses created:    {summary['team_responses']}")
        print(f"  Team answers created:      {summary['team_answers']}")
        print(f"  Engineering responses:     {summary['eng_responses']}")
        print(f"  Engineering answers:       {summary['eng_answers']}")
        print(
            f"  Total DB responses now:    "
            f"{db.query(Response).count()}"
        )
        print("Done.")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    random.seed(42)  # reproducible but realistic
    print("Seeding mock data...\n")
    seed_mock_data()
