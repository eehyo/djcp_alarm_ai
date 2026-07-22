import json
from datetime import datetime, timezone

from djcp_alarm_ai.config import get_settings
from djcp_alarm_ai.errors import AnswerGenerationError
from djcp_alarm_ai.generator import RuleBasedAnswerGenerator, build_answer_generator
from djcp_alarm_ai.schemas import (
    AlarmInfo,
    AnalysisContext,
    AssetInfo,
    TagInfo,
    TagKnowledge,
)


def main() -> None:
    settings = get_settings()
    generator = build_answer_generator(settings)
    if isinstance(generator, RuleBasedAnswerGenerator):
        raise SystemExit("Set LLM_BASE_URL to run the local LLM smoke test.")

    context = AnalysisContext(
        question="이 알람이 발생한 가능한 원인과 점검 순서를 알려줘.",
        alarm=AlarmInfo(
            tag_id=10011217,
            tag_name="BBAIT-801",
            timestamp=datetime.now(timezone.utc),
            priority=1,
            value=12.4,
            is_alm=1,
            message="연소가스 산소농도 알람",
        ),
        tag=TagInfo(
            tag_id=10011217,
            tag_name="BBAIT-801",
            description="연소가스 산소 농도",
            display_name="연소가스 산소농도",
            sig_type="AI",
            system="BOILER",
            eng_unit="%",
            hi_alm_val=10.0,
        ),
        asset=AssetInfo(
            id=13,
            parent_id=12,
            code="ASSET-002",
            name="Main Boiler 1호기",
            status="정상",
            criticality="Medium",
        ),
        tag_knowledge=TagKnowledge(
            tag_id=10011217,
            tag_name="BBAIT-801",
            description="연소가스 산소 농도",
            value_change_meaning="상승 시 과잉 공기 유입 또는 부하 증가 가능성이 있습니다.",
            key_check_points="송풍기 상태, 분석기 오염, DCS 제어 모드를 확인합니다.",
            action_guidance="공기비를 확인하고 센서 상태를 점검합니다.",
        ),
    )

    try:
        answer = generator.generate(context)
    except AnswerGenerationError:
        raise SystemExit(
            f"Local LLM request failed at {settings.llm_base_url}. "
            "Start the model server and confirm LLM_MODEL is installed."
        ) from None
    print(json.dumps(answer.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
