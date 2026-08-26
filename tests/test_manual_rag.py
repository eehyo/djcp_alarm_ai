import json
from pathlib import Path

from djcp_alarm_ai.cli.index_manual import (
    build_embedding_text,
    load_manual_records,
    parse_page_range,
)
from djcp_alarm_ai.config import Settings
from djcp_alarm_ai.generator import _build_context_payload
from djcp_alarm_ai.manual_rag import (
    ManualRetrievalPolicy,
    ManualSearchCandidate,
    VectorManualRetriever,
    build_manual_query,
)
from djcp_alarm_ai.schemas import (
    AnalysisAnswer,
    AnalysisContext,
    AnalysisResponse,
    AssetInfo,
    ManualChunk,
    TagInfo,
    TagKnowledge,
)


DATA_PATH = (
    Path(__file__).parents[1]
    / "data"
    / "tg_manual"
    / "tg_manual_search_chunks_003_015.jsonl"
)


def _context(question: str) -> AnalysisContext:
    return AnalysisContext(
        question=question,
        tag=TagInfo(
            tag_id=10,
            tag_name="TBN_LO_PRESS",
            description="Turbine Lube Oil Pressure",
            display_name="터빈 윤활유 압력",
            system="TBN LUBE OIL",
        ),
        asset=AssetInfo(
            id=20,
            name="Turbine Lubrication Oil System",
            description="터빈 윤활유 계통",
        ),
        tag_knowledge=TagKnowledge(
            tag_id=10,
            tag_name="TBN_LO_PRESS",
            equipment_description="터빈 윤활유 압력 계측",
            tag_description="터빈 베어링에 공급되는 윤활유 압력",
            value_change_meaning="압력 저하는 윤활유 공급 부족 가능성을 의미",
        ),
    )


def _candidate(
    chunk_id: str,
    title: str,
    content: str,
    similarity: float,
) -> ManualSearchCandidate:
    return ManualSearchCandidate(
        source_name="tg-emergency-manual",
        chunk_id=chunk_id,
        title=title,
        pdf_page="12",
        manual_page="10",
        content=content,
        similarity=similarity,
    )


def test_manual_selection_requires_relevance_and_returns_at_most_two() -> None:
    policy = ManualRetrievalPolicy()
    query = "터빈 TBN 윤활유 압력 저하 Trip 조건"
    candidates = [
        _candidate(
            "tbn-oil-pressure",
            "TBN Trip 조건",
            "Lube Oil Press Low 윤활유 압력 저하",
            0.78,
        ),
        _candidate(
            "tbn-oil-action",
            "TBN / GEN TRIP시 조치사항",
            "Oil system과 JOP 상태를 확인한다.",
            0.84,
        ),
        _candidate(
            "tbn-vibration",
            "TBN Trip 조건",
            "Shaft Vibration High",
            0.83,
        ),
        _candidate(
            "gen-voltage",
            "GEN Trip 조건",
            "Generator Under Voltage",
            0.95,
        ),
        _candidate(
            "low-score",
            "TBN Trip 조건",
            "Lube Oil Press Low",
            0.55,
        ),
    ]

    selected = policy.select(
        query_text=query,
        candidates=candidates,
        min_similarity=0.60,
        high_similarity=0.70,
        result_limit=10,
    )

    assert len(selected) == 2
    assert {item.chunk_id for item in selected} <= {
        "tbn-oil-pressure",
        "tbn-oil-action",
        "tbn-vibration",
    }
    assert "gen-voltage" not in {item.chunk_id for item in selected}


def test_manual_retriever_searches_even_for_non_manual_question() -> None:
    class FakeEmbeddingClient:
        calls = 0

        def embed_one(self, value: str) -> list[float]:
            self.calls += 1
            return [0.1]

    class FakeRepository:
        calls = 0

        def search(self, *args, **kwargs):
            self.calls += 1
            return []

    embedding_client = FakeEmbeddingClient()
    repository = FakeRepository()
    retriever = VectorManualRetriever(
        repository=repository,
        embedding_client=embedding_client,
        settings=Settings(_env_file=None),
    )

    result = retriever.retrieve(_context("현재 값과 단위를 알려줘."))

    assert result == []
    assert embedding_client.calls == 1
    assert repository.calls == 1


def test_manual_query_uses_compact_context_without_long_knowledge_noise() -> None:
    query = build_manual_query(_context("윤활유 압력 저하 원인을 알려줘."))

    assert "TBN_LO_PRESS" in query
    assert "터빈 윤활유 압력" in query
    assert "Turbine Lubrication Oil System" in query
    assert "터빈 베어링에 공급되는" not in query
    assert "압력 저하는" not in query


def test_manual_selection_accepts_equipment_match_at_base_threshold() -> None:
    selected = ManualRetrievalPolicy().select(
        query_text="터닝기어 자동 체결 실패",
        candidates=[
            _candidate(
                "turning-gear",
                "Turning Gear engage fail 시",
                "Local에서 수동으로 Turning Gear를 engage한다.",
                0.62,
            )
        ],
        min_similarity=0.60,
        high_similarity=0.70,
        result_limit=2,
    )

    assert [item.chunk_id for item in selected] == ["turning-gear"]


def test_manual_selection_rejects_unknown_equipment_below_high_threshold() -> None:
    selected = ManualRetrievalPolicy().select(
        query_text="LNG 누출 시 비상조치 절차를 알려줘.",
        candidates=[
            _candidate(
                "black-out",
                "정상운전중 BLACK OUT시 조치사항",
                "전원 복구 후 주요 회전기기를 확인한다.",
                0.65,
            )
        ],
        min_similarity=0.60,
        high_similarity=0.70,
        result_limit=2,
    )

    assert selected == []


def test_manual_selection_accepts_high_score_without_known_equipment() -> None:
    selected = ManualRetrievalPolicy().select(
        query_text="회전체 부속 계통 상태를 확인해줘.",
        candidates=[
            _candidate(
                "seal-steam",
                "밀봉 증기 System",
                "밀봉 증기 압력과 진공 상태를 점검한다.",
                0.72,
            )
        ],
        min_similarity=0.60,
        high_similarity=0.70,
        result_limit=2,
    )

    assert [item.chunk_id for item in selected] == ["seal-steam"]


def test_manual_context_is_sent_to_llm_but_score_is_not_exposed() -> None:
    context = _context("TBN Trip 조건을 알려줘.")
    context.manual_chunks = [
        ManualChunk(
            source_name="tg-emergency-manual",
            chunk_id="tg-manual-012",
            title="TBN Trip 조건",
            pdf_page="12",
            manual_page="10",
            content=(
                "1) TBN Speed N > 110% (> 3960 rpm)\n"
                "6) Lube Oil Press < Min Min (< 1.02)"
            ),
            similarity=0.91,
        )
    ]

    payload = json.loads(_build_context_payload(context))
    response = AnalysisResponse.from_context(
        context,
        AnalysisAnswer(
            summary="TBN Trip 조건을 조회했습니다.",
            likely_causes=[],
            checks=[],
            actions=[],
            warnings=[],
        ),
    ).model_dump(mode="json")

    assert "Lube Oil Press < Min Min" in payload["manual_chunks"][0]["content"]
    assert "similarity" not in payload["manual_chunks"][0]
    assert response["manual"] == [
        {
            "source_name": "tg-emergency-manual",
            "chunk_id": "tg-manual-012",
            "title": "TBN Trip 조건",
            "pdf_page": "12",
            "manual_page": "10",
        }
    ]


def test_manual_index_does_not_map_curation_status_to_runtime_status() -> None:
    records = load_manual_records(DATA_PATH)

    assert len(records) == 22
    assert not hasattr(records[0], "review_status")
    assert not hasattr(records[0], "content_type")
    assert parse_page_range("4-5") == (4, 5)
    embedding_text = build_embedding_text(
        title="TBN Trip 조건",
        content="Lube Oil Press Low",
    )
    assert "제목: TBN Trip 조건" in embedding_text
    assert "유형:" not in embedding_text
