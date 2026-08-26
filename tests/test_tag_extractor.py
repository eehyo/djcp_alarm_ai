from djcp_alarm_ai.tag_extractor import extract_tag_tokens


def test_extracts_various_tag_name_styles():
    q = "PIT_30_01_A1 가 알람이 발생 중인데, 15ATA-118_D 와 BBAIT-801 도 확인해줘"
    tokens = extract_tag_tokens(q)
    assert "PIT_30_01_A1" in tokens
    assert "15ATA-118_D" in tokens
    assert "BBAIT-801" in tokens


def test_ignores_plain_korean_and_short_words():
    assert extract_tag_tokens("이 태그 지금 상태 어때?") == []


def test_ignores_pure_number_dates():
    # 날짜/시간처럼 문자가 없는 토큰은 태그로 보지 않는다.
    tokens = extract_tag_tokens("2026-08-26 상태 알려줘")
    assert tokens == []


def test_dedupes_case_insensitively_and_preserves_order():
    tokens = extract_tag_tokens("TBN-TT-402 그리고 tbn-tt-402 재확인")
    assert tokens == ["TBN-TT-402"]
