"""Generate realistic dummy survey data for all teams across multiple rounds."""
import random
from datetime import datetime, timedelta

from app.database import SessionLocal, init_db
from app.models import AssessmentRound, Question, Response, ResponseAnswer, Team

# Team "personality" profiles: baseline score tendencies per category
TEAM_PROFILES = {
    "API": {"base": 3.8, "variance": 0.6},       # strong team
    "Checkout": {"base": 3.2, "variance": 0.8},   # average, inconsistent
    "Platform": {"base": 4.0, "variance": 0.4},   # top performer
    "Core": {"base": 2.8, "variance": 0.7},       # struggling
    "Infra": {"base": 3.5, "variance": 0.5},      # solid middle
}

# Category modifiers (some teams stronger in some areas)
CATEGORY_BIAS = {
    "API": {"Psychological Safety": +0.3, "Release Process": +0.5},
    "Checkout": {"Team Morale": -0.4, "Scrum Events": +0.3},
    "Platform": {"Value Delivery": +0.4, "Self-Management": +0.3},
    "Core": {"Cross-Team Collaboration": -0.5, "Team Quality": +0.2},
    "Infra": {"Release Process": +0.4, "Backlog & PO Collaboration": -0.3},
}

# Round-over-round improvement trend (simulate growth)
ROUND_TREND = {
    "Q12025": 0.0,
    "Q22025": 0.1,
    "Q4 2025": 0.15,
    "Q1 2026": 0.25,
    "Q22026": 0.3,
    "Q3 2026": 0.35,
}

RESPONDENT_NAMES = [
    "Anna", "Bartek", "Celina", "Dawid", "Ewa", "Filip", "Gosia", "Henryk",
    "Iga", "Jakub", "Kasia", "Lech", "Marta", "Norbert", "Ola", "Piotr",
    "Ryszard", "Sylwia", "Tomek", "Urszula", "Wiktor", "Zosia",
]


def clamp_score(val: float) -> int:
    """Clamp to 1-5 integer score."""
    return max(1, min(5, round(val)))


def generate_score(base: float, variance: float, cat_bias: float, trend: float) -> int:
    """Generate a realistic score with some randomness."""
    mean = base + cat_bias + trend
    score = random.gauss(mean, variance)
    return clamp_score(score)


def seed_dummy_data():
    init_db()
    db = SessionLocal()

    try:
        # Clear existing responses
        db.query(ResponseAnswer).delete()
        db.query(Response).delete()
        db.commit()
        print("[OK] Cleared existing responses")

        teams = {t.name: t for t in db.query(Team).all()}
        rounds = {r.name: r for r in db.query(AssessmentRound).all()}
        team_questions = db.query(Question).filter(Question.assessment_type == "team").all()
        eng_questions = db.query(Question).filter(Question.assessment_type == "engineering").all()

        print(f"[OK] Found {len(teams)} teams, {len(rounds)} rounds")
        print(f"[OK] {len(team_questions)} team questions, {len(eng_questions)} engineering questions")

        total_responses = 0

        for round_name, rnd in rounds.items():
            trend = ROUND_TREND.get(round_name, 0.2)

            for team_name, team in teams.items():
                profile = TEAM_PROFILES.get(team_name, {"base": 3.3, "variance": 0.6})
                cat_biases = CATEGORY_BIAS.get(team_name, {})

                # 4-8 team survey respondents per team per round
                num_respondents = random.randint(4, 8)
                names = random.sample(RESPONDENT_NAMES, num_respondents)

                for name in names:
                    resp = Response(
                        round_id=rnd.id,
                        team_id=team.id,
                        respondent_name=name,
                        assessment_type="team",
                        submitted_at=rnd.created_at + timedelta(days=random.randint(1, 14)),
                    )
                    db.add(resp)
                    db.flush()

                    for q in team_questions:
                        bias = cat_biases.get(q.category, 0.0)
                        score = generate_score(profile["base"], profile["variance"], bias, trend)
                        db.add(ResponseAnswer(response_id=resp.id, question_id=q.id, score=score))

                    total_responses += 1

                # 3-6 engineering survey respondents per team per round
                num_eng = random.randint(3, 6)
                eng_names = random.sample(RESPONDENT_NAMES, num_eng)

                for name in eng_names:
                    resp = Response(
                        round_id=rnd.id,
                        team_id=team.id,
                        respondent_name=name,
                        assessment_type="engineering",
                        submitted_at=rnd.created_at + timedelta(days=random.randint(1, 14)),
                    )
                    db.add(resp)
                    db.flush()

                    for q in eng_questions:
                        bias = cat_biases.get(q.category, 0.0)
                        # Engineering scores tend to be slightly lower
                        score = generate_score(profile["base"] - 0.3, profile["variance"], bias, trend)
                        db.add(ResponseAnswer(response_id=resp.id, question_id=q.id, score=score))

                    total_responses += 1

        db.commit()
        print(f"[OK] Created {total_responses} total responses across {len(rounds)} rounds x {len(teams)} teams")
        print("[OK] Dummy data seeded successfully!")

    finally:
        db.close()


if __name__ == "__main__":
    seed_dummy_data()
