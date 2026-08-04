from datetime import datetime
from time import perf_counter

from djcp_alarm_ai.errors import AmbiguousTagError, NotFoundError
from djcp_alarm_ai.generator import AnswerGenerator
from djcp_alarm_ai.manual_rag import ManualRetriever, NullManualRetriever
from djcp_alarm_ai.repositories import DescriptionRepository, OperationalRepository
from djcp_alarm_ai.schemas import AlarmInfo, AnalysisContext, AnalysisMetrics, AnalysisResponse


class AlarmAnalysisService:
    def __init__(
        self,
        operational_repository: OperationalRepository,
        description_repository: DescriptionRepository,
        answer_generator: AnswerGenerator,
        manual_retriever: ManualRetriever | None = None,
    ) -> None:
        self.operational_repository = operational_repository
        self.description_repository = description_repository
        self.answer_generator = answer_generator
        self.manual_retriever = manual_retriever or NullManualRetriever()

    def list_recent_alarms(self) -> list[AlarmInfo]:
        return self.operational_repository.list_recent_alarms()

    def analyze_recent_alarm(
        self,
        tag_id: int,
        timestamp: datetime,
        question: str,
    ) -> AnalysisResponse:
        started = perf_counter()
        context = self.operational_repository.load_from_recent_alarm(
            tag_id,
            timestamp,
            question,
        )
        if context is None:
            raise NotFoundError(
                f"recent alarm not found: tag_id={tag_id}, timestamp={timestamp.isoformat()}"
            )
        return self._analyze(context, started)

    def analyze_history(
        self,
        tag_id: int,
        timestamp: datetime,
        question: str,
    ) -> AnalysisResponse:
        started = perf_counter()
        context = self.operational_repository.load_from_history(
            tag_id,
            timestamp,
            question,
        )
        if context is None:
            raise NotFoundError(
                f"historical alarm not found: tag_id={tag_id}, timestamp={timestamp.isoformat()}"
            )
        return self._analyze(context, started)

    def analyze_tag(
        self,
        tag_name: str,
        question: str,
    ) -> AnalysisResponse:
        started = perf_counter()
        candidates = self.operational_repository.find_tag_candidates(tag_name)
        if not candidates:
            raise NotFoundError(f"tag not found: {tag_name}")
        if len(candidates) > 1:
            raise AmbiguousTagError(tag_name, candidates)
        context = self.operational_repository.load_from_tag(candidates[0].tag_id, question)
        if context is None:
            raise NotFoundError(f"tag not found: {candidates[0].tag_id}")
        return self._analyze(context, started)

    def _analyze(self, context: AnalysisContext, started: float | None = None) -> AnalysisResponse:
        started = perf_counter() if started is None else started
        context.tag_knowledge = self.description_repository.get_by_tag_id(context.tag.tag_id)
        if context.tag_knowledge:
            context.related_tags = self.description_repository.resolve_related_tags(
                context.tag_knowledge.related_tags,
                limit=self.operational_repository.settings.related_tag_limit,
            )
        context.manual_chunks = self.manual_retriever.retrieve(context)[:2]
        answer = self.answer_generator.generate(context)
        metrics = AnalysisMetrics(
            generation_mode=self.answer_generator.generation_mode,
            llm_response_seconds=getattr(
                self.answer_generator,
                "last_llm_response_seconds",
                None,
            ),
            analysis_total_seconds=perf_counter() - started,
        )
        return AnalysisResponse.from_context(context, answer, metrics)
