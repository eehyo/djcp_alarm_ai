import json

from djcp_alarm_ai.cli.run_scenarios import (
    TAG_SCENARIOS,
    _evaluate_analysis_response,
    _summarize,
    write_report,
)


def _base_response() -> dict:
    return {
        "answer": {
            "summary": "태그 설명 근거를 조회했습니다.",
            "likely_causes": [
                {
                    "cause": "태그 설명에 등록된 값 변화 가능 원인입니다.",
                    "basis": "TAG_DESCRIPTION",
                }
            ],
            "checks": ["관련 계측값을 확인합니다."],
            "actions": ["등록된 조치 지침에 따라 확인합니다."],
            "warnings": ["현장 절차를 우선합니다."],
        },
        "alarm": None,
        "tag": {
            "tag_id": 10011217,
            "tag_name": "BBAIT-801",
            "display_name": "연소가스 산소농도",
            "unit": "%",
            "system": "보일러 계통",
            "alarm_setpoints": {"LL": None, "LO": None, "HI": 10.0, "HH": None},
        },
        "asset": {"id": 13, "name": "Main Boiler 1호기", "description": None},
        "related_tags": [
            {"tag_name": "BBAIT-802A", "description": "Stack Gas O2"}
        ],
        "maintenance": [],
        "mimic": [],
        "manual": [],
        "metrics": {
            "generation_mode": "LLM",
            "llm_response_seconds": 1.0,
            "analysis_total_seconds": 1.1,
        },
    }


def test_tag_knowledge_scenario_accepts_complete_api_response() -> None:
    scenario = next(item for item in TAG_SCENARIOS if item.key == "tag-knowledge-related")

    checks = _evaluate_analysis_response(_base_response(), scenario=scenario)

    assert checks
    assert all(check["passed"] for check in checks)


def test_scenario_rejects_confidence() -> None:
    scenario = next(item for item in TAG_SCENARIOS if item.key == "tag-knowledge-related")
    response = _base_response()
    response["answer"]["likely_causes"][0]["confidence"] = "HIGH"

    checks = _evaluate_analysis_response(response, scenario=scenario)
    failed_names = {check["name"] for check in checks if not check["passed"]}

    assert "confidence 미포함" in failed_names


def test_report_is_saved_as_utf8_json(tmp_path) -> None:
    report = {
        "metadata": {"suite": "quick"},
        "summary": _summarize(
            [
                {"status": "PASS"},
                {"status": "FAIL"},
                {"status": "SKIP"},
            ]
        ),
        "cases": [{"name": "한글 시나리오", "status": "PASS"}],
    }

    output_path = write_report(report, tmp_path)
    loaded = json.loads(output_path.read_text(encoding="utf-8"))

    assert loaded["cases"][0]["name"] == "한글 시나리오"
    assert loaded["summary"] == {
        "total": 3,
        "passed": 1,
        "failed": 1,
        "skipped": 1,
    }
