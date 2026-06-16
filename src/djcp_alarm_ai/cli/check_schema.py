import argparse
import json

from djcp_alarm_ai.db import SessionLocal
from djcp_alarm_ai.schema_validation import check_operational_schema


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the operational PostgreSQL schema.")
    parser.add_argument("--schema", default="public")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        report = check_operational_schema(db, schema_name=args.schema)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not report["ok"]:
            raise SystemExit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
