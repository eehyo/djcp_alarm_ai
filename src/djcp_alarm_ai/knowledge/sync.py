import hashlib
import json
from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

TAG_ROWS_SQL = text("SELECT id, tag_name FROM tag ORDER BY id")

UPSERT_DESCRIPTION_SQL = text(
    """
    INSERT INTO ai.tag_description (
        tag_id, tag_name_snapshot,
        description, tag_nm, tag_rmk, tag_desc,
        equipment_description, tag_description, value_change_meaning,
        key_check_points, action_guidance, failure_guidance,
        source_version, content_hash
    ) VALUES (
        :tag_id, :tag_name_snapshot,
        :description, :tag_nm, :tag_rmk, :tag_desc,
        :equipment_description, :tag_description, :value_change_meaning,
        :key_check_points, :action_guidance, :failure_guidance,
        :source_version, :content_hash
    )
    ON CONFLICT (tag_id) DO UPDATE SET
        tag_name_snapshot = EXCLUDED.tag_name_snapshot,
        description = EXCLUDED.description,
        tag_nm = EXCLUDED.tag_nm,
        tag_rmk = EXCLUDED.tag_rmk,
        tag_desc = EXCLUDED.tag_desc,
        equipment_description = EXCLUDED.equipment_description,
        tag_description = EXCLUDED.tag_description,
        value_change_meaning = EXCLUDED.value_change_meaning,
        key_check_points = EXCLUDED.key_check_points,
        action_guidance = EXCLUDED.action_guidance,
        failure_guidance = EXCLUDED.failure_guidance,
        source_version = EXCLUDED.source_version,
        content_hash = EXCLUDED.content_hash,
        updated_at = NOW()
    WHERE ai.tag_description.content_hash <> EXCLUDED.content_hash
       OR ai.tag_description.tag_name_snapshot <> EXCLUDED.tag_name_snapshot
    """
)


def build_mapping_plan(
    document: dict[str, Any],
    db_tags: list[dict[str, Any]],
) -> dict[str, Any]:
    ids_by_name: dict[str, list[int]] = defaultdict(list)
    for tag in db_tags:
        ids_by_name[str(tag["tag_name"])].append(int(tag["id"]))

    resolved: list[dict[str, Any]] = []
    missing: list[str] = []
    ambiguous: dict[str, list[int]] = {}
    record_names = [str(record["tag_name"]) for record in document.get("records", [])]
    duplicate_record_names = sorted(
        name for name, count in Counter(record_names).items() if count > 1
    )

    for record in document.get("records", []):
        tag_name = record["tag_name"]
        if tag_name in duplicate_record_names:
            continue
        tag_ids = ids_by_name.get(tag_name, [])
        if not tag_ids:
            missing.append(tag_name)
            continue
        if len(tag_ids) > 1:
            ambiguous[tag_name] = tag_ids
            continue
        resolved.append({"tag_id": tag_ids[0], "record": record})

    description_names = {record["tag_name"] for record in document.get("records", [])}
    tags_without_description = sorted(
        {
            str(tag["tag_name"])
            for tag in db_tags
            if str(tag["tag_name"]) not in description_names
        }
    )
    return {
        "resolved": resolved,
        "missing_tag_names": sorted(missing),
        "ambiguous_tag_names": ambiguous,
        "duplicate_description_tag_names": duplicate_record_names,
        "db_tag_names_without_description": tags_without_description,
    }


def sync_descriptions(
    db: Session,
    document: dict[str, Any],
    *,
    dry_run: bool = False,
    allow_partial: bool = False,
) -> dict[str, Any]:
    db_tags = [dict(row) for row in db.execute(TAG_ROWS_SQL).mappings()]
    plan = build_mapping_plan(document, db_tags)
    source_version = _source_version(document)
    blocking_errors = {
        "missing_tag_names": plan["missing_tag_names"],
        "ambiguous_tag_names": plan["ambiguous_tag_names"],
        "duplicate_description_tag_names": plan["duplicate_description_tag_names"],
    }

    if not dry_run:
        if any(blocking_errors.values()) and not allow_partial:
            raise ValueError(
                "description sync aborted because tag_name mapping is incomplete or ambiguous"
            )
        for item in plan["resolved"]:
            db.execute(
                UPSERT_DESCRIPTION_SQL,
                _build_description_row(item["tag_id"], item["record"], source_version),
            )
        db.commit()

    return {
        "dry_run": dry_run,
        "allow_partial": allow_partial,
        "source_version": source_version,
        "description_records": len(document.get("records", [])),
        "resolved_records": len(plan["resolved"]),
        "missing_tag_names": plan["missing_tag_names"],
        "ambiguous_tag_names": plan["ambiguous_tag_names"],
        "duplicate_description_tag_names": plan["duplicate_description_tag_names"],
        "db_tag_names_without_description": plan["db_tag_names_without_description"],
    }


def _build_description_row(
    tag_id: int,
    record: dict[str, Any],
    source_version: str,
) -> dict[str, Any]:
    payload = {
        "tag_id": tag_id,
        "tag_name_snapshot": record["tag_name"],
        "description": record.get("description", ""),
        "tag_nm": record.get("tag_nm", ""),
        "tag_rmk": record.get("tag_rmk", ""),
        "tag_desc": record.get("tag_desc", ""),
        "equipment_description": record.get("equipment_description", ""),
        "tag_description": record.get("tag_description", ""),
        "value_change_meaning": record.get("value_change_meaning", ""),
        "key_check_points": record.get("key_check_points", ""),
        "action_guidance": record.get("action_guidance", ""),
        "failure_guidance": record.get("failure_guidance", ""),
        "source_version": source_version,
    }
    payload["content_hash"] = canonical_hash(payload)
    return payload


def _source_version(document: dict[str, Any]) -> str:
    source = document.get("source") or {}
    return str(
        source.get("source_workbook")
        or document.get("schema_version")
        or ""
    )


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
