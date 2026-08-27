import json
from datetime import datetime, timezone

from djcp_alarm_ai.generator import _build_context_payload, _loto_summary
from djcp_alarm_ai.schemas import AnalysisContext, LotoInfo, TagInfo


def _loto(n, status, day):
    return LotoInfo(
        id=n,
        loto_number=f"LOTO-{n:04d}",
        asset_id=13,
        work_name=f"작업 {n}",
        status=status,
        install_dt=datetime(2026, 8, day, tzinfo=timezone.utc),
    )


def _context_with_loto(loto):
    return AnalysisContext(
        question="상태 알려줘",
        tag=TagInfo(tag_id=1, tag_name="T-1", system="DJCP"),
        loto=loto,
    )


def test_loto_summary_counts_and_recent_cap():
    loto = [
        _loto(1, "InUse", 20),
        _loto(2, "Returned", 19),
        _loto(3, "InUse", 18),
        _loto(4, "Returned", 17),
        _loto(5, "Returned", 16),
    ]
    summary = _loto_summary(loto)
    assert summary["total"] == 5
    assert summary["in_use"] == 2
    assert summary["returned"] == 3
    assert len(summary["recent"]) == 3           # 최신 3건만 raw
    assert summary["recent"][0]["loto_number"] == "LOTO-0001"


def test_payload_uses_loto_summary_not_raw_list():
    ctx = _context_with_loto([_loto(1, "InUse", 20), _loto(2, "Returned", 19)])
    payload = json.loads(_build_context_payload(ctx))
    assert "loto" not in payload                 # 원시 목록은 LLM에 안 감
    assert payload["loto_summary"]["total"] == 2
    assert payload["loto_summary"]["in_use"] == 1


def test_payload_without_loto_has_no_summary():
    ctx = _context_with_loto([])
    payload = json.loads(_build_context_payload(ctx))
    assert "loto_summary" not in payload
