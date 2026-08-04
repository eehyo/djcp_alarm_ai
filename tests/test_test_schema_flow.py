import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from djcp_alarm_ai.errors import AnswerGenerationError
from djcp_alarm_ai.generator import (
    OpenAICompatibleAnswerGenerator,
    _build_context_payload,
    _parse_answer_content,
    build_answer_generator,
)
from djcp_alarm_ai.config import Settings
from djcp_alarm_ai.main import app
from djcp_alarm_ai.schemas import (
    AlarmInfo,
    AnalysisAnswer,
    AnalysisContext,
    AnalysisResponse,
    AssetInfo,
    MaintenanceInfo,
    MimicInfo,
    RelatedTag,
    LikelyCause,
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


def _answer() -> AnalysisAnswer:
    return AnalysisAnswer(
        summary="태그 설명 근거를 조회했습니다.",
        likely_causes=[
            LikelyCause(
                cause="상승 시 과잉 공기 유입 가능성이 있습니다.",
                basis="TAG_DESCRIPTION",
            )
        ],
        checks=["송풍기 상태를 확인합니다."],
        actions=["공기비와 분석기를 점검합니다."],
        warnings=[],
    )


def test_missing_llm_configuration_is_rejected() -> None:
    settings = Settings(_env_file=None, LLM_BASE_URL=None)
    generator = build_answer_generator(settings)

    with pytest.raises(AnswerGenerationError, match="LLM_BASE_URL is required"):
        generator.generate(_context())


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
        _answer(),
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


def test_llm_does_not_retry_only_because_answer_sections_are_empty(monkeypatch) -> None:
    generator = OpenAICompatibleAnswerGenerator(
        Settings(
            _env_file=None,
            LLM_BASE_URL="http://localhost:1/v1",
            LLM_API_KEY="test",
            LLM_MODEL="test-model",
        )
    )
    content = json.dumps(
        {
            "summary": "첫 번째 LLM 응답",
            "likely_causes": [],
            "checks": [],
            "actions": [],
            "warnings": [],
        },
        ensure_ascii=False,
    )
    calls: list[str] = []

    def fake_request(system_prompt: str, user_content: str) -> str:
        calls.append(system_prompt)
        return content

    monkeypatch.setattr(generator, "_request_answer_content", fake_request)

    answer = generator.generate(_context())

    assert len(calls) == 1
    assert answer.summary == "첫 번째 LLM 응답"
    assert generator.generation_mode == "LLM"
    assert answer.checks == []
    assert answer.actions == []


def test_invalid_llm_json_fails_without_retry_or_fallback(monkeypatch) -> None:
    generator = OpenAICompatibleAnswerGenerator(
        Settings(
            _env_file=None,
            LLM_BASE_URL="http://localhost:1/v1",
            LLM_API_KEY="test",
            LLM_MODEL="test-model",
        )
    )
    calls = 0

    def fake_request(system_prompt: str, user_content: str) -> str:
        nonlocal calls
        calls += 1
        return '{"summary": "잘린 응답"'

    monkeypatch.setattr(generator, "_request_answer_content", fake_request)

    with pytest.raises(AnswerGenerationError):
        generator.generate(_context())

    assert calls == 1
    assert generator.generation_mode == "LLM"


def test_llm_json_rejects_surrounding_text() -> None:
    content = (
        '설명 앞부분 {"summary":"응답","likely_causes":[],"checks":[],'
        '"actions":[],"warnings":[]} 설명 뒷부분'
    )

    with pytest.raises(ValueError, match="one complete JSON value"):
        _parse_answer_content(content)


def test_llm_json_rejects_top_level_aliases() -> None:
    content = json.dumps(
        {
            "overview": "별칭 요약",
            "causes": [],
            "check_points": [],
            "recommendations": [],
            "safety_notes": [],
        },
        ensure_ascii=False,
    )

    with pytest.raises(ValidationError):
        _parse_answer_content(content)


def test_llm_json_rejects_scalar_instead_of_array() -> None:
    content = json.dumps(
        {
            "summary": "배열 형식 오류",
            "likely_causes": [],
            "checks": "압력을 확인합니다.",
            "actions": [],
            "warnings": [],
        },
        ensure_ascii=False,
    )

    with pytest.raises(TypeError, match="checks must be an array"):
        _parse_answer_content(content)


def test_llm_json_rejects_unexpected_top_level_fields() -> None:
    content = json.dumps(
        {
            "summary": "추가 필드 오류",
            "likely_causes": [],
            "checks": [],
            "actions": [],
            "warnings": [],
            "confidence": "HIGH",
        },
        ensure_ascii=False,
    )

    with pytest.raises(ValidationError):
        _parse_answer_content(content)


def test_llm_handles_missing_knowledge_before_last_resort(monkeypatch) -> None:
    context = _context()
    context.tag_knowledge = None
    generator = OpenAICompatibleAnswerGenerator(
        Settings(
            _env_file=None,
            LLM_BASE_URL="http://localhost:1/v1",
            LLM_API_KEY="test",
            LLM_MODEL="test-model",
        )
    )
    content = json.dumps(
        {
            "summary": "LLM이 근거 부족을 설명했습니다.",
            "likely_causes": [],
            "checks": ["추가 설명 자료를 확인합니다."],
            "actions": [],
            "warnings": ["원인 판단 근거가 부족합니다."],
        },
        ensure_ascii=False,
    )
    calls = 0

    def fake_request(system_prompt: str, user_content: str) -> str:
        nonlocal calls
        calls += 1
        return content

    monkeypatch.setattr(generator, "_request_answer_content", fake_request)

    answer = generator.generate(context)

    assert calls == 1
    assert answer.summary == "LLM이 근거 부족을 설명했습니다."
    assert generator.generation_mode == "LLM"
    assert answer.likely_causes == []
    assert answer.actions == []


def test_object_shaped_answer_items_are_normalized_without_data_loss() -> None:
    answer = _parse_answer_content(
        json.dumps(
            {
                "summary": "객체형 배열 응답",
                "likely_causes": [
                    {"reason": "통신 장애 가능성", "basis": "TAG_KNOWLEDGE"}
                ],
                "checks": [{"item": "RPU 상태 확인", "priority": "필수"}],
                "actions": [{"action": "재접속 상태 확인", "condition": "미복구 시"}],
                "warnings": [{"warning": "계측값 신뢰성 주의"}],
            },
            ensure_ascii=False,
        )
    )

    assert answer.likely_causes[0].cause == "통신 장애 가능성"
    assert answer.likely_causes[0].basis == "TAG_DESCRIPTION"
    assert answer.checks == ["RPU 상태 확인"]
    assert answer.actions == ["재접속 상태 확인"]
    assert answer.warnings == ["계측값 신뢰성 주의"]


def test_unknown_item_keys_are_ignored_with_exact_top_level_schema() -> None:
    answer = _parse_answer_content(
        json.dumps(
            {
                "summary": "별칭 응답",
                "likely_causes": [
                    {"reason": "밸브 상태 변화 가능성", "basis": "DB"}
                ],
                "checks": [{"detail": "밸브 개도 확인"}],
                "actions": [{"instruction": "관련 태그와 교차 확인"}],
                "warnings": [{"note": "현장 절차 우선"}],
            },
            ensure_ascii=False,
        )
    )

    assert answer.likely_causes[0].cause == "밸브 상태 변화 가능성"
    assert answer.likely_causes[0].basis == "DATABASE"
    assert answer.checks == []
    assert answer.actions == []
    assert answer.warnings == []
