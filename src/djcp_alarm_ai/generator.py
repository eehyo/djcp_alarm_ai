import json
import logging
import sys
from pathlib import Path
from time import perf_counter
from typing import Protocol

from openai import OpenAI, OpenAIError
from pydantic import ValidationError

from djcp_alarm_ai.config import Settings, get_settings
from djcp_alarm_ai.errors import AnswerGenerationError
from djcp_alarm_ai.schemas import AnalysisAnswer, AnalysisContext

logger = logging.getLogger(__name__)


class AnswerGenerator(Protocol):
    generation_mode: str

    def generate(self, context: AnalysisContext) -> AnalysisAnswer:
        ...


class UnavailableAnswerGenerator:
    generation_mode: str = "LLM"
    last_llm_response_seconds: float | None = None

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def generate(self, context: AnalysisContext) -> AnalysisAnswer:
        raise AnswerGenerationError(self.reason)


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
        self.generation_mode: str = "LLM"

    def generate(self, context: AnalysisContext) -> AnalysisAnswer:
        system_prompt = (self.prompt_dir / "system.md").read_text(encoding="utf-8")
        context_json = _build_context_payload(context, no_think_question=True)
        self.last_llm_response_seconds = 0.0
        self.generation_mode = "LLM"
        content = self._request_answer_content(system_prompt, context_json)
        try:
            return _parse_answer_content(content)
        except (TypeError, ValueError, ValidationError) as exc:
            logger.warning(
                "LLM answer validation failed: %s; content preview=%r",
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
                max_tokens=self.settings.llm_max_tokens,
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
            self.last_llm_response_seconds = (
                (self.last_llm_response_seconds or 0.0) + elapsed_seconds
            )
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
            self.last_llm_response_seconds = (
                (self.last_llm_response_seconds or 0.0) + elapsed_seconds
            )
            print(f"LLM response failed after: {elapsed_seconds:.3f}s", file=sys.stderr)
            logger.exception("LLM answer request failed")
            raise AnswerGenerationError("LLM answer generation failed") from exc


def build_answer_generator(settings: Settings | None = None) -> AnswerGenerator:
    settings = settings or get_settings()
    if not settings.llm_base_url:
        return UnavailableAnswerGenerator("LLM_BASE_URL is required")
    return OpenAICompatibleAnswerGenerator(settings)


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
            "loto": {"__all__": {"id", "asset_id"}},
            "tag_knowledge": {
                "tag_id",
                "tag_name",
                "description",
                "tag_nm",
                "tag_rmk",
                "tag_desc",
                "related_tags",
            },
        },
    )
    if "manual_chunks" in payload:
        payload["manual_chunks"] = payload["manual_chunks"][:2]
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
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("LLM response must be one complete JSON value") from exc


def _salvage_answer_shape(payload: dict) -> dict:
    """작은 모델이 스키마를 무시하고 {"answer": "줄글"} 형태로 답한 경우,
    최소한 summary로 살려 503 대신 답을 반환한다(구조화 항목은 비움)."""
    if "summary" in payload:
        return payload
    for key in ("answer", "response", "result", "output", "text", "content", "message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            logger.warning("answer payload missing schema; salvaged from %r key", key)
            return {
                "summary": value.strip(),
                "likely_causes": [],
                "checks": [],
                "actions": [],
                "warnings": [],
            }
    return payload


def _normalize_answer_payload(payload: object) -> object:
    if not isinstance(payload, dict):
        return payload

    normalized = _salvage_answer_shape(dict(payload))
    if "likely_causes" in normalized:
        normalized["likely_causes"] = _normalize_causes(
            normalized["likely_causes"]
        )
    for key in ("checks", "actions", "warnings"):
        if key in normalized:
            normalized[key] = _normalize_string_list(normalized[key], key=key)

    return normalized


def _normalize_causes(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise TypeError("likely_causes must be an array")
    normalized: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            raise TypeError("likely_causes items must be objects")
        cause = _normalize_string_item(item, key="likely_causes")
        if not cause:
            continue
        basis = _normalize_basis(item.get("basis"))
        normalized.append(
            {
                "cause": cause,
                "basis": basis,
            }
        )
    return normalized


def _normalize_string_list(value: object, *, key: str) -> list[str]:
    if not isinstance(value, list):
        raise TypeError(f"{key} must be an array")

    normalized: list[str] = []
    for item in value:
        text = _normalize_string_item(item, key=key)
        if text:
            normalized.append(text)
    return normalized


def _normalize_string_item(item: object, *, key: str) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        candidate_keys = {
            "likely_causes": (
                "cause",
                "reason",
                "text",
                "description",
                "message",
                "summary",
            ),
            "checks": (
                "check",
                "check_point",
                "checkpoint",
                "item",
                "step",
                "text",
                "description",
                "message",
            ),
            "actions": (
                "action",
                "guidance",
                "item",
                "step",
                "text",
                "description",
                "message",
            ),
            "warnings": (
                "warning",
                "caution",
                "risk",
                "item",
                "text",
                "description",
                "message",
            ),
        }.get(key, ("text", "description", "message"))
        for candidate_key in candidate_keys:
            value = item.get(candidate_key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _normalize_basis(value: object) -> str:
    normalized = str(value or "INFERENCE").strip().upper()
    aliases = {
        "DB": "DATABASE",
        "DATABASE": "DATABASE",
        "TAG_DESCRIPTION": "TAG_DESCRIPTION",
        "TAG_KNOWLEDGE": "TAG_DESCRIPTION",
        "DESCRIPTION": "TAG_DESCRIPTION",
        "MANUAL": "MANUAL",
        "MANUAL_REFERENCE": "MANUAL",
        "INFERENCE": "INFERENCE",
    }
    return aliases.get(normalized, "INFERENCE")
