import argparse
import json
from pathlib import Path

from djcp_alarm_ai.config import get_settings
from djcp_alarm_ai.db import SessionLocal
from djcp_alarm_ai.knowledge.sync import sync_descriptions


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Sync tag descriptions to PostgreSQL.")
    parser.add_argument("--input", type=Path, default=settings.description_path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Write only uniquely resolved descriptions. Use for demo or incremental data only.",
    )
    args = parser.parse_args()

    with args.input.open(encoding="utf-8") as file:
        document = json.load(file)

    db = SessionLocal()
    try:
        report = sync_descriptions(
            db,
            document,
            dry_run=args.dry_run,
            allow_partial=args.allow_partial,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
