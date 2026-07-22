import json
from datetime import datetime, timezone

from djcp_alarm_ai.generator import RuleBasedAnswerGenerator, _build_context_payload
from djcp_alarm_ai.main import app
from djcp_alarm_ai.schemas import (
    AlarmInfo,
    AnalysisContext,
    AnalysisResponse,
    AssetInfo,
    MaintenanceInfo,
    MimicInfo,
    RelatedTag,
    SopInfo,
    TagInfo,
    TagKnowledge,
)


def _context() -> AnalysisContext:
    now = datetime(2026, 7, 22, 10, 30, tzinfo=timezone.utc)
    return AnalysisContext(
        question="이 알람의 원인을 알려줘.",
        alarm=AlarmInfo(
            timestamp=now,
            tag_id=10011217,
            tag_name="BBAIT-801",
            priority=4,
            value=12.4,
            is_alm=1,
            message="O2 alarm",
        ),
        tag=TagInfo(
            tag_id=10011217,
            tag_name="BBAIT-801",
            description="Fuel Gas O2",
            sig_type="AI",
            system="BOILER",
            eng_unit="%",
            hi_alm_val=10.0,
        ),
        tag_knowledge=TagKnowledge(
            tag_id=10011217,
            tag_name="BBAIT-801",
            tag_nm="LLM에 불필요한 중복 표시명",
            value_change_meaning="상승 시 과잉 공기 유입 가능성이 있습니다.",
            key_check_points="1. 송풍기 상태 확인. 2. 분석기 상태 확인.",
            action_guidance="공기비와 분석기를 점검합니다.",
        ),
        asset=AssetInfo(
            id=13,
            name="Main Boiler 1호기",
            description="보일러 설비",
        ),
        related_tags=[
            RelatedTag(
                tag_id=10011224,
                tag_name="BBAIT-802A",
                description="Stack Gas O2",
            )
        ],
        sop=SopInfo(
            tag_id=10011217,
            tag_name="BBAIT-801",
            scenarios=["연소 지표 이상(고)", "연소 지표 이상(저)"],
            content="# SOP — Fuel Gas O2 알람 대응",
        ),
        recent_maintenance=[
            MaintenanceInfo(
                id=1,
                work_code="WORK-001",
                asset_id=13,
                work_name="분석기 교정",
                maint_type="예방정비",
                priority="보통",
                worker="작업자",
                duration_minutes=60,
                status="완료",
                cost="100000",
                confirmer="확인자",
                team_note="내부 메모",
            )
        ],
        mimic=[
            MimicInfo(
                file_path="C:/mimic/boiler.g",
                file_size=100,
                last_write_ticks=1,
                chg_date=now,
                chg_id="tester",
            )
        ],
    )


def test_rule_answer_uses_real_alarm_event_without_virtual_setpoint() -> None:
    answer = RuleBasedAnswerGenerator().generate(_context())

    assert "12.4%" in answer.summary
    assert "O2 alarm" in answer.summary
    assert answer.likely_causes[0].basis == "TAG_DESCRIPTION"
    assert answer.checks == ["송풍기 상태 확인", "분석기 상태 확인"]


def test_llm_payload_excludes_mimic_navigation_metadata() -> None:
    payload = json.loads(_build_context_payload(_context()))

    assert "mimic" not in payload
    assert payload["alarm"]["tag_id"] == 10011217
    assert "is_ack" not in payload["alarm"]
    assert payload["tag"]["hi_alm_val"] == 10.0
    assert payload["recent_maintenance"][0]["work_name"] == "분석기 교정"
    assert "worker" not in payload["recent_maintenance"][0]
    assert "cost" not in payload["recent_maintenance"][0]
    assert "team_note" not in payload["recent_maintenance"][0]
    assert "tag_nm" not in payload["tag_knowledge"]


def test_api_response_projects_required_evidence_to_top_level() -> None:
    context = _context()
    response = AnalysisResponse.from_context(
        context,
        RuleBasedAnswerGenerator().generate(context),
    ).model_dump(mode="json", by_alias=True)

    assert "context" not in response
    assert response["alarm"]["tag_id"] == 10011217
    assert response["tag"]["alarm_setpoints"]["HI"] == 10.0
    assert response["asset"] == {
        "id": 13,
        "name": "Main Boiler 1호기",
        "description": "보일러 설비",
    }
    assert response["related_tags"][0]["tag_name"] == "BBAIT-802A"
    assert response["sop"]["tag_name"] == "BBAIT-801"
    assert response["maintenance"][0]["work_name"] == "분석기 교정"
    assert "worker" not in response["maintenance"][0]
    assert response["mimic"] == [
        {"file_path": "C:/mimic/boiler.g", "file_size": 100}
    ]
    assert response["answer"]["likely_causes"][0]["basis"] == "TAG_DESCRIPTION"


def test_api_uses_tag_id_and_timestamp_instead_of_alarm_id() -> None:
    paths = app.openapi()["paths"]

    assert "/v2/analyses/from-recent-alarm" in paths
    assert "/v2/analyses/from-history" in paths
    assert "/v2/analyses/from-alarm/{alarm_id}" not in paths
