"""Parse assessment CSVs and seed the questions table."""

import csv
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Question

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TEAM_CSV = DATA_DIR / "questions.csv"
ENGINEERING_CSV = DATA_DIR / "engineering_delivery_assessment.csv"

# Columns A–E in the team CSV (index 2–6) hold the statements
STATEMENT_COLUMNS = [2, 3, 4, 5, 6]


def parse_team_csv(path: Path | None = None) -> list[dict]:
    """Read the team survey CSV and return a list of question dicts."""
    path = path or TEAM_CSV
    questions: list[dict] = []
    order = 0

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader)  # skip header row

        for row in reader:
            if len(row) < 3:
                continue

            category = row[0].strip()
            subcategory = row[1].strip()

            if not category or not subcategory:
                continue

            for col_idx in STATEMENT_COLUMNS:
                if col_idx < len(row) and row[col_idx].strip():
                    order += 1
                    questions.append(
                        {
                            "category": category,
                            "subcategory": subcategory,
                            "statement": row[col_idx].strip(),
                            "display_order": order,
                            "assessment_type": "team",
                        }
                    )

    return questions


def parse_engineering_csv(path: Path | None = None) -> list[dict]:
    """Read the engineering delivery assessment CSV (rubric format).

    CSV columns: Category, Subcategory, Area, Base, Beginner, Intermediate, Advanced, Expert
    """
    path = path or ENGINEERING_CSV
    questions: list[dict] = []
    order = 0

    if not path.exists():
        return questions

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader)  # skip header

        for row in reader:
            if len(row) < 8:
                continue

            category = row[0].strip()
            subcategory = row[1].strip()
            area = row[2].strip()

            if not category or not subcategory or not area:
                continue

            order += 1
            questions.append(
                {
                    "category": category,
                    "subcategory": subcategory,
                    "statement": area,
                    "display_order": order,
                    "assessment_type": "engineering",
                    "level_1": row[3].strip(),  # Base
                    "level_2": row[4].strip(),  # Beginner
                    "level_3": row[5].strip(),  # Intermediate
                    "level_4": row[6].strip(),  # Advanced
                    "level_5": row[7].strip(),  # Expert
                }
            )

    return questions


def seed_questions(db: Session, force: bool = False) -> int:
    """Insert team survey questions. Returns count seeded.

    Skips if team questions already exist (unless force=True).
    """
    existing = db.query(Question).filter(Question.assessment_type == "team").count()
    if existing > 0 and not force:
        return existing

    if force:
        db.query(Question).filter(Question.assessment_type == "team").delete()

    questions = parse_team_csv()
    for q in questions:
        db.add(Question(**q))

    db.commit()
    return len(questions)


def seed_engineering_questions(db: Session, force: bool = False) -> int:
    """Insert engineering delivery assessment questions. Returns count seeded.

    Skips if engineering questions already exist (unless force=True).
    """
    existing = (
        db.query(Question).filter(Question.assessment_type == "engineering").count()
    )
    if existing > 0 and not force:
        return existing

    if force:
        db.query(Question).filter(Question.assessment_type == "engineering").delete()

    questions = parse_engineering_csv()
    for q in questions:
        db.add(Question(**q))

    db.commit()
    return len(questions)
