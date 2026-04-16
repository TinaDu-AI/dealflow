from __future__ import annotations

import json
from pathlib import Path

import db

DATA_FILE = Path(__file__).parent / "data" / "companies.json"


def main() -> None:
    db.init_db()
    companies = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    for company in companies:
        db.upsert_company(company)
    print(f"Seeded {len(companies)} companies into {db.DB_PATH}")


if __name__ == "__main__":
    main()
