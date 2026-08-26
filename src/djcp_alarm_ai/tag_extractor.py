"""자유질문에서 태그명을 추출한다.

정규식으로 태그처럼 보이는 토큰을 넉넉히 뽑아내고, 실제 태그 여부는
FDAS.TAG_INFO 조회로 검증한다(존재하지 않는 토큰은 자동으로 걸러짐).
따라서 과대추출은 안전하며, 태그 명명 규칙이 달라도 대응할 수 있다.

관찰된 태그명 예: PIT_30_01_A1, RPU_TOT_A3_SUM, 15ATA-118_D, BBAIT-801,
BB_02_3, TBN-TT-402, WWT-LT-131
"""

import re

# 문자/숫자 덩어리가 -, _ 로 이어지거나 숫자를 포함하는 토큰.
_TAG_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*")


def extract_tag_tokens(question: str) -> list[str]:
    """질문에서 태그 후보 토큰을 중복 없이 추출한다(원문 순서 유지)."""
    seen: set[str] = set()
    tokens: list[str] = []
    for match in _TAG_TOKEN_RE.findall(question or ""):
        token = match.strip("-_")
        if not _looks_like_tag(token):
            continue
        key = token.upper()
        if key in seen:
            continue
        seen.add(key)
        tokens.append(token)
    return tokens


def _looks_like_tag(token: str) -> bool:
    if len(token) < 3:
        return False
    has_alpha = any(c.isalpha() for c in token)
    has_digit = any(c.isdigit() for c in token)
    has_sep = "-" in token or "_" in token
    # 태그명은 보통 문자를 포함하며, (숫자 포함) 또는 (구분자 포함) 형태다.
    return has_alpha and (has_digit or has_sep)


# 질문에서 태그명이 안 잡힐 때 설명(DESCRIPTION) 매칭용 키워드를 뽑는다.
_WORD_RE = re.compile(r"[0-9A-Za-z가-힣]+")

# 태그 의미와 무관한 조사/일반어(설명 매칭 노이즈 감소용).
_STOPWORDS = frozenset(
    {
        "지금", "상태", "어때", "어떄", "알람", "발생", "분석", "분석해줘", "태그",
        "원인", "확인", "해줘", "있어", "관련", "정보", "현재", "지역", "값이",
        "무엇", "뭐야", "알려줘", "이거", "저거", "그거", "대해", "대한", "에서",
        "이건", "인데", "있는", "중이야", "중인데", "정상", "설명",
    }
)


def extract_keywords(question: str) -> list[str]:
    """설명 기반 후보 검색용 키워드(중복 제거, 원문 순서)."""
    seen: set[str] = set()
    words: list[str] = []
    for word in _WORD_RE.findall(question or ""):
        if len(word) < 2 or word.isdigit() or word in _STOPWORDS:
            continue
        if word in seen:
            continue
        seen.add(word)
        words.append(word)
    return words
