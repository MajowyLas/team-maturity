"""Parse the Team Maturity Assessment CSV and seed the questions table."""

import csv
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Question

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "questions.csv"

# Columns A–E in the CSV (index 2–6) hold the statements
STATEMENT_COLUMNS = [2, 3, 4, 5, 6]


def parse_questions_csv(path: Path | None = None) -> list[dict]:
    """Read the CSV and return a list of question dicts.

    Each dict has: category, subcategory, statement, display_order
    """
    path = path or CSV_PATH
    questions: list[dict] = []
    order = 0

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)  # skip header row

        for row in reader:
            if len(row) < 3:
                continue

            category = row[0].strip()
            subcategory = row[1].strip()

            if not category or not subcategory:
                continue

            # Each non-empty cell in columns A–E is a separate statement
            for col_idx in STATEMENT_COLUMNS:
                if col_idx < len(row) and row[col_idx].strip():
                    order += 1
                    questions.append(
                        {
                            "category": category,
                            "subcategory": subcategory,
                            "statement": row[col_idx].strip(),
                            "display_order": order,
                        }
                    )

    return questions


def seed_questions(db: Session, force: bool = False) -> int:
    """Insert questions into the DB. Returns the count of questions seeded.

    Skips seeding if questions already exist (unless force=True).
    """
    existing = db.query(Question).count()
    if existing > 0 and not force:
        return existing

    if force:
        db.query(Question).delete()

    questions = parse_questions_csv()
    for q in questions:
        db.add(Question(**q))

    db.commit()
    return len(questions)
