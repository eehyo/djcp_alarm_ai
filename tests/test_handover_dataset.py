import re
from pathlib import Path


HANDOVER_DIR = Path(__file__).parents[1] / "data" / "lab_handover"


def _id_name_pairs(sql: str, table: str) -> list[tuple[int, str]]:
    pattern = re.compile(
        rf"^INSERT INTO {table} .*? VALUES \((\d+), '((?:''|[^'])*)'",
        re.MULTILINE,
    )
    return [
        (int(tag_id), tag_name.replace("''", "'"))
        for tag_id, tag_name in pattern.findall(sql)
    ]


def test_handover_tag_knowledge_and_sop_keys_are_consistent() -> None:
    tag_sql = (HANDOVER_DIR / "tag_description.sql").read_text(encoding="utf-8")
    sop_sql = (HANDOVER_DIR / "sop_document.sql").read_text(encoding="utf-8")

    tag_pairs = _id_name_pairs(tag_sql, "tag_description")
    sop_pairs = _id_name_pairs(sop_sql, "sop_document")

    assert tag_pairs
    assert set(tag_pairs) == set(sop_pairs)
    assert len(tag_pairs) == len(set(tag_pairs))
    assert len({tag_id for tag_id, _ in tag_pairs}) == len(tag_pairs)
    assert len({tag_name for _, tag_name in tag_pairs}) == len(tag_pairs)

    tag_names = {tag_name for _, tag_name in tag_pairs}
    related_tag_names = set(re.findall(r'"tag_name":\s*"([^"]+)"', tag_sql))
    sop_tag_names = {
        value.replace("''", "'")
        for value in re.findall(
            r", '((?:''|[^'])*)', '[0-9a-f]{64}'\) ON CONFLICT \(tag_id\)",
            tag_sql,
        )
    }

    assert related_tag_names <= tag_names
    assert sop_tag_names == tag_names


def test_handover_asset_and_maintenance_keys_are_consistent() -> None:
    asset_sql = (HANDOVER_DIR / "asset.sql").read_text(encoding="utf-8")
    maintenance_sql = (HANDOVER_DIR / "maintenance.sql").read_text(encoding="utf-8")

    asset_rows = [
        (int(asset_id), int(parent_id) if parent_id != "NULL" else None)
        for asset_id, parent_id in re.findall(
            r"^INSERT INTO asset .*? VALUES \((\d+), (NULL|\d+),",
            asset_sql,
            re.MULTILINE,
        )
    ]
    asset_ids = {asset_id for asset_id, _ in asset_rows}
    parent_ids = {parent_id for _, parent_id in asset_rows if parent_id is not None}
    link_asset_ids = {
        int(asset_id)
        for asset_id in re.findall(
            r"^INSERT INTO asset_tag_link .*? VALUES \((\d+), \d+\)",
            asset_sql,
            re.MULTILINE,
        )
    }
    maintenance_asset_ids = {
        int(asset_id)
        for asset_id in re.findall(
            r"^INSERT INTO maintenance .*? VALUES \('(?:''|[^'])*', (\d+),",
            maintenance_sql,
            re.MULTILINE,
        )
    }

    assert asset_rows
    assert parent_ids <= asset_ids
    assert link_asset_ids <= asset_ids
    assert maintenance_asset_ids <= asset_ids
