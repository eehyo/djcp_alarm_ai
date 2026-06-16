import argparse
import json
from pathlib import Path
from typing import Any

from sqlalchemy import text

from djcp_alarm_ai.config import get_settings
from djcp_alarm_ai.db import SessionLocal


ASSET_ID_SQL = text("SELECT id FROM asset WHERE code = :asset_code")
ASSET_IDS_SQL = text(
    """
    SELECT code, id
    FROM asset
    WHERE code IN (:boiler_1_asset_code, :boiler_2_asset_code)
    """
)

TAG_COUNTS_SQL = text(
    """
    SELECT tag_name, COUNT(*) AS count
    FROM tag
    GROUP BY tag_name
    """
)

INSERT_TAG_SQL = text(
    """
    INSERT INTO tag (
        asset_id, tag_code, tag_name, description, unit, alarm_enabled
    ) VALUES (
        :asset_id, :tag_code, :tag_name, :description, '', TRUE
    )
    ON CONFLICT (tag_code) DO NOTHING
    """
)

UPDATE_TAG_ASSET_SQL = text(
    """
    UPDATE tag
    SET asset_id = :asset_id
    WHERE tag_name = :tag_name
    """
)


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Create demo tag rows for every tag_name in the Description JSON."
    )
    parser.add_argument("--input", type=Path, default=settings.description_path)
    parser.add_argument("--asset-code", default="DEMO-BOILER-1")
    parser.add_argument("--boiler-1-asset-code", default="DEMO-BOILER-1")
    parser.add_argument("--boiler-2-asset-code", default="DEMO-BOILER-2")
    parser.add_argument("--split-boilers", action="store_true")
    parser.add_argument("--tag-code-prefix", default="DESC")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with args.input.open(encoding="utf-8") as file:
        document = json.load(file)

    db = SessionLocal()
    try:
        report = seed_description_tags(
            db,
            document,
            asset_code=args.asset_code,
            boiler_1_asset_code=args.boiler_1_asset_code,
            boiler_2_asset_code=args.boiler_2_asset_code,
            split_boilers=args.split_boilers,
            tag_code_prefix=args.tag_code_prefix,
            dry_run=args.dry_run,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def seed_description_tags(
    db,
    document: dict[str, Any],
    *,
    asset_code: str,
    boiler_1_asset_code: str = "DEMO-BOILER-1",
    boiler_2_asset_code: str = "DEMO-BOILER-2",
    split_boilers: bool = False,
    tag_code_prefix: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    if split_boilers:
        rows = db.execute(
            ASSET_IDS_SQL,
            {
                "boiler_1_asset_code": boiler_1_asset_code,
                "boiler_2_asset_code": boiler_2_asset_code,
            },
        ).mappings()
        asset_ids = {str(row["code"]): int(row["id"]) for row in rows}
        missing_asset_codes = sorted(
            {boiler_1_asset_code, boiler_2_asset_code} - set(asset_ids)
        )
        if missing_asset_codes:
            raise ValueError(f"asset not found: {', '.join(missing_asset_codes)}")
    else:
        asset_id = db.execute(ASSET_ID_SQL, {"asset_code": asset_code}).scalar_one_or_none()
        if asset_id is None:
            raise ValueError(f"asset not found: {asset_code}")
        asset_ids = {asset_code: int(asset_id)}

    records = document.get("records", [])
    tag_names = [str(record["tag_name"]) for record in records]
    existing_counts = {
        str(row["tag_name"]): int(row["count"])
        for row in db.execute(TAG_COUNTS_SQL).mappings()
    }

    ambiguous_existing = sorted(
        tag_name
        for tag_name in tag_names
        if existing_counts.get(tag_name, 0) > 1
    )
    if ambiguous_existing:
        raise ValueError(f"ambiguous existing tag_name rows: {ambiguous_existing}")

    to_insert = [
        record
        for record in records
        if existing_counts.get(str(record["tag_name"]), 0) == 0
    ]
    to_update = [
        record
        for record in records
        if existing_counts.get(str(record["tag_name"]), 0) == 1
    ]

    if not dry_run:
        if split_boilers:
            for record in to_update:
                db.execute(
                    UPDATE_TAG_ASSET_SQL,
                    {
                        "asset_id": _resolve_asset_id(
                            record["tag_name"],
                            asset_ids,
                            asset_code=asset_code,
                            boiler_1_asset_code=boiler_1_asset_code,
                            boiler_2_asset_code=boiler_2_asset_code,
                            split_boilers=split_boilers,
                        ),
                        "tag_name": record["tag_name"],
                    },
                )
        for record in to_insert:
            db.execute(
                INSERT_TAG_SQL,
                {
                    "asset_id": _resolve_asset_id(
                        record["tag_name"],
                        asset_ids,
                        asset_code=asset_code,
                        boiler_1_asset_code=boiler_1_asset_code,
                        boiler_2_asset_code=boiler_2_asset_code,
                        split_boilers=split_boilers,
                    ),
                    "tag_code": f"{tag_code_prefix}-{record['tag_name']}",
                    "tag_name": record["tag_name"],
                    "description": record.get("description", ""),
                },
            )
        db.commit()

    return {
        "dry_run": dry_run,
        "asset_code": asset_code,
        "asset_ids": asset_ids,
        "split_boilers": split_boilers,
        "description_records": len(records),
        "existing_tags": len(records) - len(to_insert),
        "created_tags": len(to_insert),
        "updated_existing_tag_assets": len(to_update) if split_boilers else 0,
        "ambiguous_existing_tag_names": ambiguous_existing,
        "created_tag_names": [record["tag_name"] for record in to_insert],
    }


def _resolve_asset_id(
    tag_name: str,
    asset_ids: dict[str, int],
    *,
    asset_code: str,
    boiler_1_asset_code: str,
    boiler_2_asset_code: str,
    split_boilers: bool,
) -> int:
    if not split_boilers:
        return asset_ids[asset_code]
    if tag_name.startswith("BC"):
        return asset_ids[boiler_2_asset_code]
    return asset_ids[boiler_1_asset_code]


if __name__ == "__main__":
    main()
