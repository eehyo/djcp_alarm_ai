from djcp_alarm_ai.schemas import TagCandidate


class NotFoundError(ValueError):
    pass


class AnswerGenerationError(RuntimeError):
    pass


class AmbiguousTagError(ValueError):
    def __init__(self, tag_name: str, candidates: list[TagCandidate]) -> None:
        super().__init__(f"tag_name is ambiguous: {tag_name}")
        self.tag_name = tag_name
        self.candidates = candidates
