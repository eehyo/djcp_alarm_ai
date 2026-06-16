from djcp_alarm_ai.errors import AmbiguousTagError, NotFoundError
from djcp_alarm_ai.generator import AnswerGenerator, build_answer_generator
from djcp_alarm_ai.repositories import DescriptionRepository, OperationalRepository
from djcp_alarm_ai.schemas import AnalysisContext, AnalysisResponse


class AlarmAnalysisService:
    def __init__(
        self,
        operational_repository: OperationalRepository,
        description_repository: DescriptionRepository,
        answer_generator: AnswerGenerator | None = None,
    ) -> None:
        self.operational_repository = operational_repository
        self.description_repository = description_repository
        self.answer_generator = answer_generator or build_answer_generator()

    def analyze_alarm(self, alarm_id: int, question: str) -> AnalysisResponse:
        context = self.operational_repository.load_from_alarm(alarm_id, question)
        if context is None:
            raise NotFoundError(f"alarm not found: {alarm_id}")
        return self._analyze(context)

    def analyze_tag(
        self,
        tag_name: str,
        question: str,
        asset_id: int | None = None,
    ) -> AnalysisResponse:
        candidates = self.operational_repository.find_tag_candidates(tag_name, asset_id)
        if not candidates:
            raise NotFoundError(f"tag not found: {tag_name}")
        if len(candidates) > 1:
            raise AmbiguousTagError(tag_name, candidates)
        context = self.operational_repository.load_from_tag(candidates[0].tag_id, question)
        if context is None:
            raise NotFoundError(f"tag not found: {candidates[0].tag_id}")
        return self._analyze(context)

    def _analyze(self, context: AnalysisContext) -> AnalysisResponse:
        context.tag_knowledge = self.description_repository.get_by_tag_id(context.tag.id)
        answer = self.answer_generator.generate(context)
        return AnalysisResponse(context=context, answer=answer)
