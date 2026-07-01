import json
import logging
import re
from pathlib import Path
from typing import Protocol

from openai import OpenAI, OpenAIError
from pydantic import ValidationError

from djcp_alarm_ai.config import Settings, get_settings
from djcp_alarm_ai.errors import AnswerGenerationError
from djcp_alarm_ai.schemas import AnalysisAnswer, AnalysisContext, CauseCandidate

logger = logging.getLogger(__name__)


class AnswerGenerator(Protocol):
    def generate(self, context: AnalysisContext) -> AnalysisAnswer:
        ...


class RuleBasedAnswerGenerator:
    """Deterministic response used when an LLM is not configured."""

    def generate(self, context: AnalysisContext) -> AnalysisAnswer:
        knowledge = context.tag_knowledge
        unit = context.tag.unit
        warnings: list[str] = []
        causes: list[CauseCandidate] = []
        checks: list[str] = []
        actions: list[str] = []

        if context.alarm:
            summary = (
                f"{context.tag.tag_name} 태그에서 측정값 {context.alarm.value}{unit}이 "
                f"설정값 {context.alarm.setpoint}{unit} 기준의 알람 상태로 기록되었습니다."
            )
        else:
            value = (
                f" 현재값은 {context.tag.current_value}{unit}입니다."
                if context.tag.current_value is not None
                else ""
            )
            summary = f"{context.tag.tag_name} 태그 상태를 조회했습니다.{value}"

        if knowledge:
            if knowledge.value_change_meaning:
                causes.append(
                    CauseCandidate(
                        cause=knowledge.value_change_meaning,
                        confidence="MEDIUM",
                        basis="TAG_DESCRIPTION",
                    )
                )
            if knowledge.tag_description:
                causes.append(
                    CauseCandidate(
                        cause=knowledge.tag_description,
                        confidence="LOW",
                        basis="TAG_DESCRIPTION",
                    )
                )
            checks = _split_guidance(knowledge.key_check_points)
            actions = _split_guidance(knowledge.action_guidance)
            if knowledge.failure_guidance:
                warnings.append(knowledge.failure_guidance)
            if not knowledge.is_verified:
                warnings.append("현재 태그 설명은 미검증 초기 지식입니다.")
        else:
            causes.append(
                CauseCandidate(
                    cause="등록된 상세 태그 설명이 없어 운영 데이터만으로 원인을 확정할 수 없습니다.",
                    confidence="LOW",
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

    def generate(self, context: AnalysisContext) -> AnalysisAnswer:
        system_prompt = (self.prompt_dir / "system.md").read_text(encoding="utf-8")
        context_json = _build_context_payload(context)

        content = self._request_answer_content(
            system_prompt,
            context_json,
        )
        try:
            return _parse_answer_content(content)
        except (TypeError, ValueError, ValidationError) as first_exc:
            logger.warning(
                "LLM answer validation failed; retrying with /no_think: %s; "
                "content preview=%r",
                first_exc,
                content[:1000],
            )

        retry_content = self._request_answer_content(
            system_prompt,
            _build_context_payload(context, no_think_question=True),
        )
        try:
            answer = _parse_answer_content(retry_content)
        except (TypeError, ValueError, ValidationError) as retry_exc:
            logger.warning(
                "LLM /no_think retry validation failed: %s; content preview=%r",
                retry_exc,
                retry_content[:1000],
            )
            raise AnswerGenerationError("LLM answer validation failed") from retry_exc

        logger.info("LLM /no_think retry succeeded")
        return answer

    def _request_answer_content(
        self,
        system_prompt: str,
        user_content: str,
    ) -> str:
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
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "alarm_analysis_answer",
                        "strict": False,
                        "schema": AnalysisAnswer.model_json_schema(),
                    },
                },
            )
            return response.choices[0].message.content or ""
        except (OpenAIError, IndexError) as exc:
            logger.exception("LLM answer request failed")
            raise AnswerGenerationError("LLM answer generation failed") from exc


def build_answer_generator(settings: Settings | None = None) -> AnswerGenerator:
    settings = settings or get_settings()
    if settings.llm_base_url:
        return OpenAICompatibleAnswerGenerator(settings)
    return RuleBasedAnswerGenerator()


def _split_guidance(value: str) -> list[str]:
    if not value.strip():
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
    payload = context.model_dump(mode="json")
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
    for key in ("likely_causes", "checks", "actions", "warnings"):
        if normalized.get(key) is None:
            normalized[key] = []

    causes = normalized.get("likely_causes")
    if isinstance(causes, list):
        normalized["likely_causes"] = [_normalize_cause_payload(cause) for cause in causes]
    return normalized


def _normalize_cause_payload(payload: object) -> object:
    if not isinstance(payload, dict):
        return payload

    normalized = dict(payload)
    for key in ("confidence", "basis"):
        value = normalized.get(key)
        if isinstance(value, str):
            normalized[key] = value.strip().upper().replace(" ", "_")
    return normalized
