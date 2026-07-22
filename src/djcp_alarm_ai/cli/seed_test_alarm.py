import argparse
import json
from datetime import datetime, timezone

from sqlalchemy import text

from djcp_alarm_ai.db import SessionLocal


TAG_SQL = text(
    """
    SELECT
        "TAG_ID" AS tag_id,
        "TAG_NAME" AS tag_name,
        "DESCRIPTION" AS description
    FROM test."TAG_INFO"
    WHERE "TAG_ID" = :tag_id
    """
)

INSERT_VALUE_SQL = text(
    """
    INSERT INTO test."ALARM_VALUE" (
        "TIMESTAMP", "TAG_ID", "TAG_NAME", "DESCRIPTION",
        "PRIORITY", "VALUE", "IS_ALM", "MESSAGE"
    ) VALUES (
        :timestamp, :tag_id, :tag_name, :description,
        :priority, :value, :is_alm, :message
    )
    """
)

INSERT_HIST_SQL = text(
    """
    INSERT INTO test."ALARM_HIST" (
        "TIMESTAMP", "TAG_ID", "TAG_NAME", "DESCRIPTION",
        "PRIORITY", "VALUE", "IS_ALM", "MESSAGE"
    ) VALUES (
        :timestamp, :tag_id, :tag_name, :description,
        :priority, :value, :is_alm, :message
    )
    """
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Insert one synthetic event into test.ALARM_VALUE and test.ALARM_HIST "
            "using an existing test.TAG_INFO tag."
        )
    )
    parser.add_argument("--tag-id", type=int, required=True)
    parser.add_argument("--value", type=float, required=True)
    parser.add_argument("--priority", type=int, required=True)
    parser.add_argument("--message", required=True)
    parser.add_argument("--is-alm", type=int, choices=(0, 1), default=1)
    parser.add_argument(
        "--timestamp",
        type=_parse_timestamp,
        default=None,
        help="ISO-8601 timestamp with timezone; defaults to current UTC time.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not -32768 <= args.priority <= 32767:
        parser.error("--priority must fit PostgreSQL smallint")
    if len(args.message) > 50:
        parser.error("--message must be at most 50 characters")

    db = SessionLocal()
    try:
        tag = db.execute(TAG_SQL, {"tag_id": args.tag_id}).mappings().one_or_none()
        if tag is None:
            raise ValueError(f"TAG_INFO tag not found: {args.tag_id}")
        if len(tag["tag_name"]) > 40:
            raise ValueError(
                f"TAG_NAME does not fit ALARM_VALUE.TAG_NAME: {tag['tag_name']}"
            )

        payload = {
            "timestamp": args.timestamp or datetime.now(timezone.utc),
            "tag_id": tag["tag_id"],
            "tag_name": tag["tag_name"],
            "description": (tag["description"] or "")[:72] or None,
            "priority": args.priority,
            "value": args.value,
            "is_alm": args.is_alm,
            "message": args.message,
        }

        if not args.dry_run:
            # trim_alarm_value() uses an unqualified ALARM_VALUE reference.
            db.execute(text("SET LOCAL search_path TO test, public"))
            db.execute(INSERT_VALUE_SQL, payload)
            db.execute(INSERT_HIST_SQL, payload)
            db.commit()

        print(
            json.dumps(
                {"dry_run": args.dry_run, **payload},
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include a timezone")
    return parsed


if __name__ == "__main__":
    main()
