import json
from datetime import datetime, timezone
from decimal import Decimal

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
            id=1,
            tag_id=10010002,
            start_time=datetime.now(timezone.utc),
            value=Decimal("12.4"),
            setpoint=Decimal("10.0"),
            severity="High",
            state="발생",
        ),
        tag=TagInfo(
            id=10010002,
            asset_id=42,
            tag_name="BBAIT-801",
            description="연소가스 산소 농도",
            unit="%",
            alarm_high=Decimal("10.0"),
            current_value=Decimal("12.4"),
        ),
        asset=AssetInfo(
            id=42,
            code="BLR-001",
            name="1호기 보일러",
            asset_type="Boiler",
        ),
        tag_knowledge=TagKnowledge(
            tag_id=10010002,
            tag_name_snapshot="BBAIT-801",
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
