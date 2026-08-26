from djcp_alarm_ai.generator import _parse_answer_content


def test_salvages_answer_only_response_into_summary():
    # 작은 모델이 스키마 대신 {"answer": "줄글"} 로 답한 경우.
    content = '{"answer": "TBN 윤활유 압력 저하는 Trip 조건이 아닙니다."}'
    answer = _parse_answer_content(content)
    assert answer.summary.startswith("TBN 윤활유 압력 저하")
    assert answer.likely_causes == []
    assert answer.checks == []
    assert answer.actions == []
    assert answer.warnings == []


def test_normal_schema_still_parses():
    content = (
        '{"summary": "요약", "likely_causes": [], "checks": ["c1"], '
        '"actions": [], "warnings": []}'
    )
    answer = _parse_answer_content(content)
    assert answer.summary == "요약"
    assert answer.checks == ["c1"]


def test_screen_name_extracts_basename_from_windows_path():
    from djcp_alarm_ai.generator import _screen_name

    p = r"D:\Project\FLab\doc\Daejeon\DCS\21. Steam Turbine System 2.G"
    assert _screen_name(p) == "21. Steam Turbine System 2.G"
    assert _screen_name(None) == ""
