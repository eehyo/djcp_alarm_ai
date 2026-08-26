import pytest

from djcp_alarm_ai.errors import AmbiguousTagError, NotFoundError
from djcp_alarm_ai.schemas import TagCandidate
from djcp_alarm_ai.service import AlarmAnalysisService


class _StubOperationalRepo:
    def __init__(self, candidates):
        self._candidates = candidates
        self.loaded_tag_id = None

    def find_tags_in_text(self, question):
        return self._candidates

    def load_from_tag(self, tag_id, question):
        self.loaded_tag_id = tag_id
        raise AssertionError("should not reach load for these cases")


def _service(candidates):
    return AlarmAnalysisService(
        operational_repository=_StubOperationalRepo(candidates),
        description_repository=object(),
        answer_generator=object(),
    )


def _candidate(tag_id, name):
    return TagCandidate(tag_id=tag_id, tag_name=name, system="DJCP")


def test_ask_with_no_tag_raises_not_found():
    with pytest.raises(NotFoundError):
        _service([]).analyze_question("지금 상태 어때?")


def test_ask_with_multiple_tags_raises_ambiguous():
    candidates = [_candidate(1, "AAA-001"), _candidate(2, "BBB-002")]
    with pytest.raises(AmbiguousTagError) as exc:
        _service(candidates).analyze_question("AAA-001 과 BBB-002 분석해줘")
    assert len(exc.value.candidates) == 2
