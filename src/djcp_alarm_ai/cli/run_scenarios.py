import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from djcp_alarm_ai.db import SessionLocal


REQUIRED_TOP_LEVEL_MEMBERS = {
    "answer",
    "alarm",
    "tag",
    "asset",
    "related_tags",
    "maintenance",
    "mimic",
    "manual",
    "metrics",
}
ALLOWED_CAUSE_BASES = {"DATABASE", "TAG_DESCRIPTION", "MANUAL", "INFERENCE"}
ALLOWED_GENERATION_MODES = {
    "LLM",
}


@dataclass(frozen=True)
class TagScenario:
    key: str
    name: str
    tag_name: str
    question: str
    expected_tag_id: int
    expected_related_tag: str | None = None
    expect_related_empty: bool = False
    require_asset: bool = False
    require_maintenance: bool = False
    expected_basis: str | None = None
    expect_causes_empty: bool = False
    expect_actions_empty: bool = False


TAG_SCENARIOS = (
    TagScenario(
        key="tag-knowledge-related",
        name="태그 설명·관련 태그 연결",
        tag_name="BBAIT-801",
        question=(
            "이 태그의 역할과 값 상승·하강 의미를 설명하고, "
            "등록된 점검 및 조치 방향을 알려줘."
        ),
        expected_tag_id=10011217,
        expected_related_tag="BBAIT-802A",
        require_asset=True,
    ),
    TagScenario(
        key="maintenance",
        name="설비 정비이력 연결",
        tag_name="PIT_30_01_A1",
        question=(
            "이 공급압력 태그에서 이상이 발생할 때 가능한 원인과 "
            "최근 정비이력을 바탕으로 확인할 항목을 알려줘."
        ),
        expected_tag_id=10010001,
        require_asset=True,
        require_maintenance=True,
    ),
    TagScenario(
        key="drum-level",
        name="드럼 수위 대응",
        tag_name="BBDRL-HH",
        question=(
            "드럼 수위 고고 또는 저저 상황에서 확인해야 할 계측값과 "
            "등록된 점검 및 조치 방향을 알려줘."
        ),
        expected_tag_id=10013302,
    ),
    TagScenario(
        key="lng-leak",
        name="LNG 누설 안전 대응",
        tag_name="BBAIA-801_1B",
        question=(
            "이 누설 감지 알람이 발생했을 때 즉시 확인할 항목과 "
            "안전 주의사항을 등록된 태그 설명을 근거로 알려줘."
        ),
        expected_tag_id=10013305,
    ),
    TagScenario(
        key="steam-pressure",
        name="주증기 압력 대응",
        tag_name="BA_PI_144",
        question=(
            "주증기 압력 과상승 또는 급저하 시 가능한 원인, "
            "점검 항목과 조치 방향을 알려줘."
        ),
        expected_tag_id=10014606,
    ),
    TagScenario(
        key="communication-loss",
        name="통신 두절과 설비 이상 구분",
        tag_name="PIT_30_01_STS",
        question=(
            "통신 두절이 발생했을 때 계측 통신 문제와 실제 설비 이상을 "
            "구분하는 점검 순서를 알려줘."
        ),
        expected_tag_id=20010001,
    ),
    TagScenario(
        key="missing-knowledge",
        name="태그 설명이 없는 경우",
        tag_name="15ATA-118_D",
        question=(
            "현재 등록된 데이터만으로 이 태그에서 확인할 수 있는 정보와 "
            "추가로 필요한 정보를 알려줘."
        ),
        expected_tag_id=10014455,
        expect_related_empty=True,
        expect_causes_empty=True,
        expect_actions_empty=True,
    ),
)

QUICK_SCENARIO_KEYS = {
    "tag-knowledge-related",
    "maintenance",
    "lng-leak",
    "missing-knowledge",
}

LATEST_HISTORY_SQL = text(
    """
    SELECT
        "TAG_ID" AS tag_id,
        "TIMESTAMP" AS timestamp,
        "IS_ALM" AS is_alm
    FROM test."ALARM_HIST"
    ORDER BY "TIMESTAMP" DESC, "TAG_ID"
    LIMIT 1
    """
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run DJCP alarm API integration scenarios and save raw responses "
            "with pass/fail checks."
        )
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Running API base URL (default: http://localhost:8000).",
    )
    parser.add_argument(
        "--suite",
        choices=("quick", "full"),
        default="quick",
        help="quick runs 4 tag cases; full runs all 7 tag cases.",
    )
    parser.add_argument(
        "--output-dir",
        default="test_outputs",
        help="Directory for the timestamped JSON report.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help="Timeout in seconds for each API call.",
    )
    parser.add_argument(
        "--skip-history",
        action="store_true",
        help="Do not query ALARM_HIST or run the history scenario.",
    )
    parser.add_argument(
        "--skip-recent",
        action="store_true",
        help="Do not run the optional ALARM_VALUE scenario.",
    )
    args = parser.parse_args()

    report = run_scenarios(
        base_url=args.base_url,
        suite=args.suite,
        timeout=args.timeout,
        include_history=not args.skip_history,
        include_recent=not args.skip_recent,
    )
    output_path = write_report(report, Path(args.output_dir))

    for case in report["cases"]:
        print(f"[{case['status']}] {case['name']}")
        if case["status"] == "FAIL":
            for check in case.get("checks", []):
                if not check["passed"]:
                    print(f"  - {check['name']}: {check['detail']}")
            if case.get("error"):
                print(f"  - error: {case['error']}")

    summary = report["summary"]
    print(
        "Summary: "
        f"PASS={summary['passed']} FAIL={summary['failed']} SKIP={summary['skipped']}"
    )
    print(f"Report: {output_path.resolve()}")
    if summary["failed"]:
        raise SystemExit(1)


def run_scenarios(
    *,
    base_url: str,
    suite: str,
    timeout: float,
    include_history: bool,
    include_recent: bool,
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    base_url = base_url.rstrip("/")
    cases: list[dict[str, Any]] = []

    health = _execute_http_case(
        name="API 상태 확인",
        method="GET",
        url=f"{base_url}/health",
        payload=None,
        timeout=timeout,
        evaluator=_evaluate_health,
    )
    cases.append(health)

    if health["status"] == "PASS":
        selected = (
            TAG_SCENARIOS
            if suite == "full"
            else tuple(item for item in TAG_SCENARIOS if item.key in QUICK_SCENARIO_KEYS)
        )
        for scenario in selected:
            cases.append(_execute_tag_scenario(base_url, scenario, timeout))

        if include_history:
            cases.append(_execute_history_scenario(base_url, timeout))
        if include_recent:
            cases.append(_execute_recent_scenario(base_url, timeout))
    else:
        cases.append(
            _skipped_case(
                "나머지 시나리오",
                "API 상태 확인이 실패하여 추가 호출을 중단했습니다.",
            )
        )

    finished_at = datetime.now(timezone.utc)
    return {
        "metadata": {
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "base_url": base_url,
            "suite": suite,
            "timeout_seconds": timeout,
        },
        "summary": _summarize(cases),
        "cases": cases,
    }


def write_report(report: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"integration_{timestamp}.json"
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def _execute_tag_scenario(
    base_url: str,
    scenario: TagScenario,
    timeout: float,
) -> dict[str, Any]:
    payload = {"tag_name": scenario.tag_name, "question": scenario.question}
    return _execute_http_case(
        name=scenario.name,
        method="POST",
        url=f"{base_url}/v2/analyses/from-tag",
        payload=payload,
        timeout=timeout,
        evaluator=lambda body: _evaluate_analysis_response(body, scenario=scenario),
    )


def _execute_history_scenario(base_url: str, timeout: float) -> dict[str, Any]:
    try:
        with SessionLocal() as db:
            row = db.execute(LATEST_HISTORY_SQL).mappings().one_or_none()
    except SQLAlchemyError as exc:
        return _failed_case(
            "과거 ALARM_HIST 이벤트",
            f"ALARM_HIST 조회 실패: {type(exc).__name__}: {exc}",
        )
    if row is None:
        return _skipped_case("과거 ALARM_HIST 이벤트", "ALARM_HIST가 비어 있습니다.")

    payload = {
        "tag_id": row["tag_id"],
        "timestamp": row["timestamp"].isoformat(),
        "question": "이 과거 이벤트의 상태와 가능한 원인, 확인 항목을 알려줘.",
    }
    return _execute_http_case(
        name="과거 ALARM_HIST 이벤트",
        method="POST",
        url=f"{base_url}/v2/analyses/from-history",
        payload=payload,
        timeout=timeout,
        evaluator=lambda body: _evaluate_alarm_response(
            body,
            expected_tag_id=row["tag_id"],
            expected_is_alm=row["is_alm"],
        ),
    )


def _execute_recent_scenario(base_url: str, timeout: float) -> dict[str, Any]:
    status, body, error, elapsed = _request_json(
        "GET",
        f"{base_url}/v2/analyses/recent-alarms",
        None,
        timeout,
    )
    if error or status != 200:
        return {
            "name": "최근 ALARM_VALUE 이벤트",
            "status": "FAIL",
            "request": {
                "method": "GET",
                "url": f"{base_url}/v2/analyses/recent-alarms",
                "body": None,
            },
            "http_status": status,
            "duration_seconds": elapsed,
            "checks": [],
            "response": body,
            "error": error or f"HTTP {status}",
        }
    if not isinstance(body, list) or not body:
        return _skipped_case(
            "최근 ALARM_VALUE 이벤트",
            "ALARM_VALUE가 비어 있어 최근 알람 분석을 생략했습니다.",
        )

    alarm = body[0]
    payload = {
        "tag_id": alarm.get("tag_id"),
        "timestamp": alarm.get("timestamp"),
        "question": "이 최근 알람의 가능한 원인과 점검 순서를 알려줘.",
    }
    return _execute_http_case(
        name="최근 ALARM_VALUE 이벤트",
        method="POST",
        url=f"{base_url}/v2/analyses/from-recent-alarm",
        payload=payload,
        timeout=timeout,
        evaluator=lambda response: _evaluate_alarm_response(
            response,
            expected_tag_id=alarm.get("tag_id"),
            expected_is_alm=alarm.get("is_alm"),
        ),
    )


def _execute_http_case(
    *,
    name: str,
    method: str,
    url: str,
    payload: dict[str, Any] | None,
    timeout: float,
    evaluator: Any,
) -> dict[str, Any]:
    status, body, error, elapsed = _request_json(method, url, payload, timeout)
    checks = evaluator(body) if status == 200 and error is None else []
    passed = status == 200 and error is None and all(item["passed"] for item in checks)
    return {
        "name": name,
        "status": "PASS" if passed else "FAIL",
        "request": {"method": method, "url": url, "body": payload},
        "http_status": status,
        "duration_seconds": elapsed,
        "checks": checks,
        "response": body,
        "error": error or (None if status == 200 else f"HTTP {status}"),
    }


def _request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None,
    timeout: float,
) -> tuple[int | None, Any, str | None, float]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else None
    request = Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    started = perf_counter()
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            body = json.loads(raw) if raw else None
            return response.status, body, None, perf_counter() - started
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            body = raw
        return exc.code, body, f"HTTP {exc.code}", perf_counter() - started
    except (URLError, TimeoutError, OSError) as exc:
        return None, None, f"{type(exc).__name__}: {exc}", perf_counter() - started
    except json.JSONDecodeError as exc:
        return None, None, f"Invalid JSON response: {exc}", perf_counter() - started


def _evaluate_health(body: Any) -> list[dict[str, Any]]:
    return [
        _check(
            "health.status",
            isinstance(body, dict) and body.get("status") == "ok",
            "ok",
            body.get("status") if isinstance(body, dict) else body,
        )
    ]


def _evaluate_analysis_response(
    body: Any,
    *,
    scenario: TagScenario,
) -> list[dict[str, Any]]:
    if not isinstance(body, dict):
        return [_check("JSON 객체 응답", False, "object", type(body).__name__)]

    checks = _common_analysis_checks(body)
    tag = body.get("tag") if isinstance(body.get("tag"), dict) else {}
    checks.extend(
        [
            _check("tag.tag_name", tag.get("tag_name") == scenario.tag_name, scenario.tag_name, tag.get("tag_name")),
            _check("tag.tag_id", tag.get("tag_id") == scenario.expected_tag_id, scenario.expected_tag_id, tag.get("tag_id")),
            _check("태그 질문의 alarm", body.get("alarm") is None, None, body.get("alarm")),
        ]
    )

    related = body.get("related_tags") if isinstance(body.get("related_tags"), list) else []
    related_names = {
        item.get("tag_name") for item in related if isinstance(item, dict)
    }
    if scenario.expected_related_tag:
        checks.append(
            _check(
                f"related_tags: {scenario.expected_related_tag}",
                scenario.expected_related_tag in related_names,
                True,
                scenario.expected_related_tag in related_names,
            )
        )
    if scenario.expect_related_empty:
        checks.append(_check("related_tags 빈 배열", not related, [], related))
    if scenario.require_asset:
        checks.append(_check("asset 연결", isinstance(body.get("asset"), dict), "present", body.get("asset")))
    if scenario.require_maintenance:
        maintenance = body.get("maintenance")
        checks.append(
            _check(
                "maintenance 1건 이상",
                isinstance(maintenance, list) and len(maintenance) > 0,
                ">= 1",
                len(maintenance) if isinstance(maintenance, list) else maintenance,
            )
        )

    answer = body.get("answer") if isinstance(body.get("answer"), dict) else {}
    if scenario.expected_basis:
        bases = {
            item.get("basis")
            for item in answer.get("likely_causes", [])
            if isinstance(item, dict)
        }
        checks.append(
            _check(
                f"likely_causes basis={scenario.expected_basis}",
                scenario.expected_basis in bases,
                scenario.expected_basis,
                sorted(value for value in bases if value),
            )
        )
    if scenario.expect_causes_empty:
        causes = answer.get("likely_causes")
        checks.append(
            _check("likely_causes 빈 배열", causes == [], [], causes)
        )
    if scenario.expect_actions_empty:
        actions = answer.get("actions")
        checks.append(_check("actions 빈 배열", actions == [], [], actions))
    return checks


def _evaluate_alarm_response(
    body: Any,
    *,
    expected_tag_id: Any,
    expected_is_alm: Any,
) -> list[dict[str, Any]]:
    if not isinstance(body, dict):
        return [_check("JSON 객체 응답", False, "object", type(body).__name__)]
    checks = _common_analysis_checks(body)
    alarm = body.get("alarm") if isinstance(body.get("alarm"), dict) else {}
    answer = body.get("answer") if isinstance(body.get("answer"), dict) else {}
    checks.extend(
        [
            _check("alarm 존재", bool(alarm), "present", alarm),
            _check("alarm.tag_id", alarm.get("tag_id") == expected_tag_id, expected_tag_id, alarm.get("tag_id")),
            _check("alarm.is_alm 원본 보존", alarm.get("is_alm") == expected_is_alm, expected_is_alm, alarm.get("is_alm")),
        ]
    )
    if expected_is_alm == 0:
        summary = str(answer.get("summary") or "")
        checks.append(
            _check(
                "IS_ALM=0 해제 이벤트 표현",
                "해제" in summary and "현재" not in summary,
                "summary contains '해제' and excludes '현재'",
                summary,
            )
        )
    return checks


def _common_analysis_checks(body: dict[str, Any]) -> list[dict[str, Any]]:
    members = set(body)
    answer = body.get("answer") if isinstance(body.get("answer"), dict) else {}
    causes = answer.get("likely_causes") if isinstance(answer.get("likely_causes"), list) else []
    confidence_found = any(
        isinstance(item, dict) and "confidence" in item for item in causes
    )
    invalid_bases = sorted(
        {
            str(item.get("basis"))
            for item in causes
            if isinstance(item, dict) and item.get("basis") not in ALLOWED_CAUSE_BASES
        }
    )
    metrics = body.get("metrics") if isinstance(body.get("metrics"), dict) else {}
    generation_mode = metrics.get("generation_mode")
    return [
        _check(
            "최상위 응답 멤버",
            REQUIRED_TOP_LEVEL_MEMBERS <= members,
            sorted(REQUIRED_TOP_LEVEL_MEMBERS),
            sorted(members),
        ),
        _check("answer 객체", bool(answer), "present", answer),
        _check("confidence 미포함", not confidence_found, False, confidence_found),
        _check("likely_causes.basis 허용값", not invalid_bases, [], invalid_bases),
        _check(
            "metrics.generation_mode",
            generation_mode in ALLOWED_GENERATION_MODES,
            sorted(ALLOWED_GENERATION_MODES),
            generation_mode,
        ),
    ]


def _check(name: str, passed: bool, expected: Any, actual: Any) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "detail": f"expected={expected!r}, actual={actual!r}",
    }


def _skipped_case(name: str, reason: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": "SKIP",
        "request": None,
        "http_status": None,
        "duration_seconds": 0.0,
        "checks": [],
        "response": None,
        "error": None,
        "skip_reason": reason,
    }


def _failed_case(name: str, error: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": "FAIL",
        "request": None,
        "http_status": None,
        "duration_seconds": 0.0,
        "checks": [],
        "response": None,
        "error": error,
    }


def _summarize(cases: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(cases),
        "passed": sum(case["status"] == "PASS" for case in cases),
        "failed": sum(case["status"] == "FAIL" for case in cases),
        "skipped": sum(case["status"] == "SKIP" for case in cases),
    }


if __name__ == "__main__":
    main()
