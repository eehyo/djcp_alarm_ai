import pytest

from djcp_alarm_ai.errors import NotFoundError
from djcp_alarm_ai.schemas import (
    AnalysisAnswer,
    AnalysisContext,
    TagCandidate,
    TagInfo,
)
from djcp_alarm_ai.service import AlarmAnalysisService


class _StubOperationalRepo:
    def __init__(self, name_hits, keyword_hits=None):
        self._name_hits = name_hits
        self._keyword_hits = keyword_hits or []
        self.loaded_ids = []

    def find_tags_in_text(self, question):
        return self._name_hits

    def find_tag_candidates_by_keywords(self, question):
        return self._keyword_hits

    def load_from_tag(self, tag_id, question):
        self.loaded_ids.append(tag_id)
        return AnalysisContext(
            question=question,
            tag=TagInfo(tag_id=tag_id, tag_name=f"TAG-{tag_id}", system="DJCP"),
        )


class _StubDescriptionRepo:
    def get_by_tag_id(self, tag_id):
        return None


class _StubGenerator:
    generation_mode = "LLM"
    last_llm_response_seconds = 0.1

    def generate(self, context):
        return AnalysisAnswer(
            summary="ok", likely_causes=[], checks=[], actions=[], warnings=[]
        )


class _PickFirstSelector:
    """항상 첫 후보 하나만 고르는 선별기(선별 로직 검증용)."""

    def select(self, question, candidates):
        return [candidates[0].tag_id]


def _candidate(tag_id, name, description=None):
    return TagCandidate(
        tag_id=tag_id, tag_name=name, description=description, system="DJCP"
    )


def _service(repo, selector=None):
    return AlarmAnalysisService(
        operational_repository=repo,
        description_repository=_StubDescriptionRepo(),
        answer_generator=_StubGenerator(),
        tag_selector=selector,
    )


def test_ask_with_no_tag_raises_not_found():
    repo = _StubOperationalRepo(name_hits=[], keyword_hits=[])
    with pytest.raises(NotFoundError):
        _service(repo).analyze_question("지금 상태 어때?")


def test_ask_falls_back_to_keyword_candidates_when_no_name():
    repo = _StubOperationalRepo(
        name_hits=[],
        keyword_hits=[_candidate(10, "OXY-1", "연소가스 산소 농도")],
    )
    result = _service(repo).analyze_question("산소 농도 태그 알려줘")
    assert repo.loaded_ids == [10]
    assert len(result.analyses) == 1


def test_ask_selects_relevant_subset_via_selector():
    repo = _StubOperationalRepo(
        name_hits=[_candidate(1, "AAA-001"), _candidate(2, "BBB-002")]
    )
    result = _service(repo, selector=_PickFirstSelector()).analyze_question(
        "AAA-001 과 BBB-002 중 무엇을 봐야 해?"
    )
    # 선별기가 첫 태그만 골랐으므로 하나만 분석된다.
    assert repo.loaded_ids == [1]
    assert result.question.startswith("AAA-001")
    assert len(result.analyses) == 1


def test_ask_analyzes_multiple_selected_tags():
    repo = _StubOperationalRepo(
        name_hits=[_candidate(1, "AAA-001"), _candidate(2, "BBB-002")]
    )
    # 기본 NullTagSelector = 후보 전체 선택.
    result = _service(repo).analyze_question("AAA-001 과 BBB-002 둘 다 분석해줘")
    assert repo.loaded_ids == [1, 2]
    assert len(result.analyses) == 2
