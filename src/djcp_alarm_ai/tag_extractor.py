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
