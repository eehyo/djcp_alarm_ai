"""질문에 대해 '실제로 분석이 필요한' 태그를 LLM이 후보 중에서 선별한다.

후보는 DB에서 태그명/설명으로 생성하고(카탈로그 근거), LLM은 그 목록 안에서만
고르므로 환각으로 없는 태그를 만들지 않는다. 여러 태그가 언급돼도 질문이 실제로
요구하는 태그만 선택할 수 있다. LLM이 없거나 실패하면 후보 전체로 폴백한다.
"""

import json
import logging
from typing import Protocol

from openai import OpenAI, OpenAIError

from djcp_alarm_ai.config import Settings, get_settings
from djcp_alarm_ai.schemas import TagCandidate

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "너는 발전소 태그 질문 분석의 태그 선별기다. 후보 태그 목록(tag_id, tag_name, "
    "description)이 주어지면, 질문이 실제로 분석·설명을 요구하는 태그의 tag_id만 고른다. "
    "질문과 직접 관련 없는 후보는 제외한다. 반드시 후보 목록에 있는 tag_id만 사용하고, "
    '아래 JSON 형식으로만 답한다: {"tag_ids": [숫자, ...]}. 관련 태그가 없으면 '
    '{"tag_ids": []}.'
)


class TagSelector(Protocol):
    def select(self, question: str, candidates: list[TagCandidate]) -> list[int]:
        ...


class NullTagSelector:
    """LLM 미사용 시: 후보 전체 tag_id를 그대로 반환한다."""

    def select(self, question: str, candidates: list[TagCandidate]) -> list[int]:
        return [c.tag_id for c in candidates]


class LLMTagSelector:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.llm_base_url:
            raise ValueError("LLM_BASE_URL is required")
        self.client = OpenAI(
            api_key=self.settings.llm_api_key or "local",
            base_url=self.settings.llm_base_url,
            timeout=self.settings.llm_timeout_seconds,
            max_retries=1,
        )

    def select(self, question: str, candidates: list[TagCandidate]) -> list[int]:
        if not candidates:
            return []
        if len(candidates) == 1:
            return [candidates[0].tag_id]

        valid_ids = {c.tag_id for c in candidates}
        payload = {
            "question": question,
            "candidates": [
                {
                    "tag_id": c.tag_id,
                    "tag_name": c.tag_name,
                    "description": c.description,
                }
                for c in candidates
            ],
        }
        try:
            response = self.client.chat.completions.create(
                model=self.settings.llm_model,
                temperature=0.0,
                max_tokens=256,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                response_format={"type": "json_object"},
                extra_body={"reasoning": {"effort": "none"}},
            )
            content = response.choices[0].message.content or ""
            selected = _parse_tag_ids(content, valid_ids)
        except (OpenAIError, ValueError, IndexError, KeyError) as exc:
            logger.warning("tag selection failed, fallback to all candidates: %s", exc)
            return [c.tag_id for c in candidates]

        if not selected:
            # LLM이 하나도 못 고르면 후보 순서상 첫 태그로 폴백(빈 응답 방지).
            return [candidates[0].tag_id]
        # 후보 순서를 유지해 반환한다.
        return [c.tag_id for c in candidates if c.tag_id in selected]


def _parse_tag_ids(content: str, valid_ids: set[int]) -> set[int]:
    data = json.loads(content)
    raw = data.get("tag_ids", []) if isinstance(data, dict) else []
    result: set[int] = set()
    for value in raw if isinstance(raw, list) else []:
        try:
            tag_id = int(value)
        except (TypeError, ValueError):
            continue
        if tag_id in valid_ids:
            result.add(tag_id)
    return result


def build_tag_selector(settings: Settings | None = None) -> TagSelector:
    settings = settings or get_settings()
    if not settings.llm_base_url:
        return NullTagSelector()
    return LLMTagSelector(settings)
