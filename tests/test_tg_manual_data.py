import json
from pathlib import Path

import pytest


DATA_PATH = (
    Path(__file__).parents[1]
    / "data"
    / "tg_manual"
    / "tg_manual_pages_003_015.jsonl"
)
SEARCH_DATA_PATH = (
    Path(__file__).parents[1]
    / "data"
    / "tg_manual"
    / "tg_manual_search_chunks_003_015.jsonl"
)


def _load_records() -> list[dict]:
    return [
        json.loads(line)
        for line in DATA_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_tg_manual_candidate_has_expected_sections() -> None:
    records = _load_records()

    assert len(records) == 15
    assert [record["section_no"] for record in records] == list(range(1, 16))
    assert len({record["chunk_id"] for record in records}) == 15


def test_tg_manual_candidate_uses_minimal_schema() -> None:
    expected_fields = {
        "chunk_id",
        "section_no",
        "pdf_page",
        "manual_page",
        "title",
        "content",
        "review_status",
    }

    for record in _load_records():
        assert set(record) == expected_fields
        assert record["review_status"] == "pending"
        assert record["title"].strip()
        assert record["content"].strip()


def test_tg_manual_search_chunks_follow_deterministic_split_rules() -> None:
    records = [
        json.loads(line)
        for line in SEARCH_DATA_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(records) == 22
    assert max(len(record["content"]) for record in records) <= 1200
    assert len({record["chunk_id"] for record in records}) == len(records)
    assert all(
        set(record)
        == {
            "chunk_id",
            "parent_chunk_id",
            "section_no",
            "pdf_page",
            "manual_page",
            "title",
            "content",
        }
        for record in records
    )


def test_tg_manual_trip_search_chunks_keep_complete_sections() -> None:
    records = [
        json.loads(line)
        for line in SEARCH_DATA_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    complete_section_ids = {
        "tg-manual-012",
        "tg-manual-013",
        "tg-manual-014",
        "tg-manual-015",
    }
    complete_sections = [
        record for record in records if record["chunk_id"] in complete_section_ids
    ]
    source_by_id = {
        record["chunk_id"]: record
        for record in _load_records()
        if record["chunk_id"] in complete_section_ids
    }

    assert len(complete_sections) == 4
    for record in complete_sections:
        numbered_lines = [
            line
            for line in record["content"].splitlines()
            if line.strip() and line.split(")", maxsplit=1)[0].isdigit()
        ]
        assert len(numbered_lines) > 1
        assert record["parent_chunk_id"] is None
        assert record["chunk_id"] in source_by_id
        assert record["title"] == source_by_id[record["chunk_id"]]["title"]
        assert record["content"] == source_by_id[record["chunk_id"]]["content"]


def test_tg_manual_search_file_is_reproducible_from_source() -> None:
    from djcp_alarm_ai.cli.preprocess_manual import preprocess_records

    generated = preprocess_records(_load_records())
    committed = [
        json.loads(line)
        for line in SEARCH_DATA_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert generated == committed


def test_short_record_keeps_complete_section_even_with_subheadings() -> None:
    from djcp_alarm_ai.cli.preprocess_manual import preprocess_records

    source = {
        "chunk_id": "manual-001",
        "section_no": 1,
        "pdf_page": "1",
        "manual_page": "1",
        "title": "설비 점검 목록",
        "content": "[압력]\n1) 압력 확인\n\n[온도]\n1) 온도 확인",
        "review_status": "pending",
    }

    chunks = preprocess_records([source])

    assert len(chunks) == 1
    assert chunks[0]["chunk_id"] == "manual-001"
    assert chunks[0]["parent_chunk_id"] is None
    assert chunks[0]["content"] == source["content"]


def test_long_record_preprocessing_uses_structural_headings() -> None:
    from djcp_alarm_ai.cli.preprocess_manual import preprocess_records

    source = {
        "chunk_id": "manual-001",
        "section_no": 1,
        "pdf_page": "1",
        "manual_page": "1",
        "title": "설비 Trouble 조치사항",
        "content": (
            "복수기 계통\n- " + "가" * 600
            + "\n\n윤활유 계통\n- " + "나" * 600
        ),
        "review_status": "pending",
    }

    chunks = preprocess_records([source])

    assert [chunk["chunk_id"] for chunk in chunks] == [
        "manual-001-s01",
        "manual-001-s02",
    ]
    assert chunks[0]["title"].endswith("복수기 계통")
    assert chunks[1]["title"].endswith("윤활유 계통")


def test_preprocessing_rejects_long_text_without_safe_boundary() -> None:
    from djcp_alarm_ai.cli.preprocess_manual import preprocess_records

    source = {
        "chunk_id": "manual-001",
        "section_no": 1,
        "pdf_page": "1",
        "manual_page": "1",
        "title": "경계 없는 절차",
        "content": "가" * 1201,
        "review_status": "pending",
    }

    with pytest.raises(ValueError, match="without a safe heading"):
        preprocess_records([source])
