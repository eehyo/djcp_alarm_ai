import json
import logging
import re
import sys
from pathlib import Path
from time import perf_counter
from typing import Protocol

from openai import OpenAI, OpenAIError
from pydantic import ValidationError

from djcp_alarm_ai.config import Settings, get_settings
from djcp_alarm_ai.errors import AnswerGenerationError
from djcp_alarm_ai.schemas import AnalysisAnswer, AnalysisContext, LikelyCause

logger = logging.getLogger(__name__)


class AnswerGenerator(Protocol):
    def generate(self, context: AnalysisContext) -> AnalysisAnswer:
        ...


class RuleBasedAnswerGenerator:
    """Deterministic response used when an LLM is not configured."""

    last_llm_response_seconds: float | None = None

    def generate(self, context: AnalysisContext) -> AnalysisAnswer:
        knowledge = context.tag_knowledge
        unit = context.tag.eng_unit or ""
        warnings: list[str] = []
        causes: list[LikelyCause] = []
        checks: list[str] = []
        actions: list[str] = []

        if context.alarm:
            event_state = "발생" if context.alarm.is_alm else "해제"
            summary = (
                f"{context.tag.tag_name} 태그에서 측정값 {context.alarm.value}{unit}의 "
                f"알람 {event_state} 이벤트({context.alarm.message})가 기록되었습니다."
            )
        else:
            summary = f"{context.tag.tag_name} 태그의 기준정보와 연결된 지식을 조회했습니다."

        if knowledge:
            if knowledge.value_change_meaning:
                causes.append(
                    LikelyCause(
                        cause=knowledge.value_change_meaning,
                        basis="TAG_DESCRIPTION",
                    )
                )
            if knowledge.tag_description:
                causes.append(
                    LikelyCause(
                        cause=knowledge.tag_description,
                        basis="TAG_DESCRIPTION",
                    )
                )
            checks = _split_guidance(knowledge.key_check_points)
            actions = _split_guidance(knowledge.action_guidance)
            if knowledge.failure_guidance:
                warnings.append(knowledge.failure_guidance)
        else:
            causes.append(
                LikelyCause(
                    cause="등록된 상세 태그 설명이 없어 운영 데이터만으로 원인을 확정할 수 없습니다.",
                    basis="INFERENCE",
                )
            )
            checks.append("태그 측정값, 설정값, 센서 상태와 현장 설비 상태를 확인하세요.")
            warnings.append("이 태그에 연결된 상세 description이 없습니다.")

        return AnalysisAnswer(
            summary=summary,
            likely_causes=causes,
            checks=checks,
            actions=actions,
            warnings=_dedupe(warnings),
        )


class OpenAICompatibleAnswerGenerator:
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
        self.prompt_dir = Path(__file__).resolve().parent / "prompts"
        self.last_llm_response_seconds: float | None = None

    def generate(self, context: AnalysisContext) -> AnalysisAnswer:
        system_prompt = (self.prompt_dir / "system.md").read_text(encoding="utf-8")
        context_json = _build_context_payload(context, no_think_question=True)

        content = self._request_answer_content(
            system_prompt,
            context_json,
        )
        try:
            return _parse_answer_content(content)
        except (TypeError, ValueError, ValidationError) as exc:
            logger.warning(
                "LLM /no_think answer validation failed: %s; content preview=%r",
                exc,
                content[:1000],
            )
            raise AnswerGenerationError("LLM answer validation failed") from exc

    def _request_answer_content(
        self,
        system_prompt: str,
        user_content: str,
    ) -> str:
        started = perf_counter()
        try:
            response = self.client.chat.completions.create(
                model=self.settings.llm_model,
                temperature=self.settings.llm_temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": user_content,
                    },
                ],
                response_format={"type": "json_object"},
                extra_body={"reasoning": {"effort": "none"}},
            )
            elapsed_seconds = perf_counter() - started
            self.last_llm_response_seconds = elapsed_seconds
            choice = response.choices[0]
            content = choice.message.content or ""
            print(
                (
                    f"LLM response time: {elapsed_seconds:.3f}s "
                    f"finish_reason={choice.finish_reason} content_chars={len(content)}"
                ),
                file=sys.stderr,
            )
            return content
        except (OpenAIError, IndexError) as exc:
            elapsed_seconds = perf_counter() - started
            self.last_llm_response_seconds = elapsed_seconds
            print(f"LLM response failed after: {elapsed_seconds:.3f}s", file=sys.stderr)
            logger.exception("LLM answer request failed")
            raise AnswerGenerationError("LLM answer generation failed") from exc


def build_answer_generator(settings: Settings | None = None) -> AnswerGenerator:
    settings = settings or get_settings()
    if settings.llm_base_url:
        return OpenAICompatibleAnswerGenerator(settings)
    return RuleBasedAnswerGenerator()


def _split_guidance(value: str | None) -> list[str]:
    if not value or not value.strip():
        return []
    numbered = [
        item.strip(" .")
        for item in re.split(r"(?:^|\s)\d+\.\s*", value)
        if item.strip(" .")
    ]
    if len(numbered) > 1:
        return numbered
    return [value.strip()]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _build_context_payload(
    context: AnalysisContext,
    *,
    no_think_question: bool = False,
) -> str:
    # API 응답용 메타데이터 중 알람 원인 판단에 불필요한 값은 LLM에 보내지 않는다.
    payload = context.model_dump(
        mode="json",
        exclude_none=True,
        exclude={
            "mimic": True,
            "recent_maintenance": {
                "__all__": {
                    "id",
                    "work_code",
                    "asset_id",
                    "worker",
                    "cost",
                    "confirmer",
                    "team_note",
                }
            },
            "tag_knowledge": {
                "tag_id",
                "tag_name",
                "description",
                "tag_nm",
                "tag_rmk",
                "tag_desc",
                "related_tags",
                "sop_tag_name",
            },
            "sop": {"embedding_model"},
        },
    )
    if no_think_question:
        question = str(payload.get("question") or "")
        if not question.lstrip().startswith("/no_think"):
            payload["question"] = f"/no_think\n{question}"
    return json.dumps(payload, ensure_ascii=False)


def _parse_answer_content(content: str) -> AnalysisAnswer:
    payload = _extract_json_payload(content)
    payload = _normalize_answer_payload(payload)
    return AnalysisAnswer.model_validate(payload)


def _extract_json_payload(content: str) -> object:
    decoder = json.JSONDecoder()
    stripped = content.strip()
    try:
        payload, _ = decoder.raw_decode(stripped)
        if _looks_like_answer_payload(payload):
            return payload
    except json.JSONDecodeError:
        pass

    first_payload = None
    for index, char in enumerate(content):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(content[index:])
            if _looks_like_answer_payload(payload):
                return payload
            if first_payload is None:
                first_payload = payload
        except json.JSONDecodeError:
            continue
    if first_payload is not None:
        return first_payload
    raise ValueError("LLM response did not contain a JSON object")


def _looks_like_answer_payload(payload: object) -> bool:
    return isinstance(payload, dict) and "summary" in payload


def _normalize_answer_payload(payload: object) -> object:
    if not isinstance(payload, dict):
        return payload

    normalized = dict(payload)
    normalized["likely_causes"] = _normalize_causes(normalized.get("likely_causes"))
    for key in ("checks", "actions", "warnings"):
        normalized[key] = _normalize_string_list(normalized.get(key), key=key)

    return normalized


def _normalize_causes(value: object) -> list[dict[str, str]]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    normalized: list[dict[str, str]] = []
    for item in items:
        if isinstance(item, str) and item.strip():
            normalized.append(
                {
                    "cause": item.strip(),
                    "basis": "INFERENCE",
                }
            )
            continue
        if not isinstance(item, dict):
            continue
        cause = _normalize_string_item(item, key="likely_causes")
        if not cause:
            continue
        basis = str(item.get("basis") or "INFERENCE").upper()
        normalized.append(
            {
                "cause": cause,
                "basis": (
                    basis
                    if basis in {"DATABASE", "TAG_DESCRIPTION", "INFERENCE"}
                    else "INFERENCE"
                ),
            }
        )
    return normalized


def _normalize_string_list(value: object, *, key: str) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]

    normalized: list[str] = []
    for item in items:
        text = _normalize_string_item(item, key=key)
        if text:
            normalized.append(text)
    return normalized


def _normalize_string_item(item: object, *, key: str) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        for candidate_key in ("cause", "text", "description", "message"):
            value = item.get(candidate_key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        if key == "likely_causes":
            value = item.get("summary")
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""
