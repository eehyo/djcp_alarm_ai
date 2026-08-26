"""tag_description JSONL 적재 CLI.

담당자 전달 형식: JSONL(한 줄에 태그 하나). tag_description 컬럼을 키로 사용한다.
필수: tag_id, tag_name. 나머지는 선택. related_tags 는 [{tag_name, description}, ...]
형태의 리스트(또는 객체)로 두면 JSONB로 저장된다.

실행 (AI DB = djcp_alarm_ai):
    python -m djcp_alarm_ai.cli.load_tag_description --input tag_description.jsonl
    djcp-load-tag-description --input tag_description.jsonl
"""

import argparse
import json

from sqlalchemy import text

from djcp_alarm_ai.config import get_settings
from djcp_alarm_ai.db import AiSession

_TEXT_FIELDS = (
    "tag_name",
    "description",
    "tag_nm",
    "tag_rmk",
    "tag_desc",
    "equipment_description",
    "tag_description",
    "value_change_meaning",
    "key_check_points",
    "action_guidance",
    "failure_guidance",
    "content_hash",
)


def _upsert_sql(schema: str) -> "text":
    return text(
        f"""
        INSERT INTO {schema}.tag_description (
            tag_id, tag_name, description, tag_nm, tag_rmk, tag_desc,
            equipment_description, tag_description, value_change_meaning,
            key_check_points, action_guidance, failure_guidance,
            related_tags, content_hash, updated_at
        ) VALUES (
            :tag_id, :tag_name, :description, :tag_nm, :tag_rmk, :tag_desc,
            :equipment_description, :tag_description, :value_change_meaning,
            :key_check_points, :action_guidance, :failure_guidance,
            CAST(:related_tags AS jsonb), :content_hash, NOW()
        )
        ON CONFLICT (tag_id) DO UPDATE SET
            tag_name = EXCLUDED.tag_name,
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
            related_tags = EXCLUDED.related_tags,
            content_hash = EXCLUDED.content_hash,
            updated_at = NOW()
        """
    )


def _row_params(record: dict) -> dict:
    if "tag_id" not in record or record.get("tag_name") in (None, ""):
        raise ValueError("각 줄에는 tag_id 와 tag_name 이 있어야 합니다.")
    params = {"tag_id": int(record["tag_id"])}
    for field in _TEXT_FIELDS:
        value = record.get(field)
        params[field] = value if value not in ("",) else None
    related = record.get("related_tags")
    params["related_tags"] = (
        json.dumps(related, ensure_ascii=False) if related is not None else None
    )
    return params


def main() -> None:
    parser = argparse.ArgumentParser(description="Load tag_description rows from JSONL.")
    parser.add_argument("--input", required=True, help="JSONL 파일 경로")
    parser.add_argument("--dry-run", action="store_true", help="적재 없이 검증만")
    args = parser.parse_args()

    schema = get_settings().ai_schema
    records: list[dict] = []
    with open(args.input, encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(_row_params(json.loads(line)))
            except (json.JSONDecodeError, ValueError) as exc:
                raise SystemExit(f"{line_no}번째 줄 파싱 실패: {exc}") from exc

    if args.dry_run:
        print(f"dry-run: {len(records)} rows OK ({args.input})")
        return

    upsert = _upsert_sql(schema)
    with AiSession() as db, db.begin():
        for params in records:
            db.execute(upsert, params)
    print(f"tag_description load complete: {len(records)} rows into {schema}.tag_description")


if __name__ == "__main__":
    main()
