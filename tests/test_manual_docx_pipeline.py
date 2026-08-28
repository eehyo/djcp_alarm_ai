"""표준 매뉴얼 DOCX 파이프라인(파싱→전처리→적재→업로드 API) 테스트."""

import contextlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from djcp_alarm_ai.cli.parse_manual_docx import parse_manual_docx
from djcp_alarm_ai.cli.preprocess_manual import preprocess_records
from djcp_alarm_ai.config import get_settings
from djcp_alarm_ai.db import get_db_ai
from djcp_alarm_ai.main import create_app
from djcp_alarm_ai.manual_api import get_embedding_client
from djcp_alarm_ai.manual_ingest import ingest_manual_docx_path


DATA_DIR = Path(__file__).parents[1] / "data" / "tg_manual"
DOCX_PATH = (
    Path(__file__).parents[1] / "docs" / "TG매뉴얼 & 비상시 조치사항.docx"
)
DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

# data/ 와 docs/ 는 .gitignore 대상이라 환경에 따라 없을 수 있습니다.
requires_docx = pytest.mark.skipif(
    not DOCX_PATH.exists(),
    reason="원본 DOCX가 없어 건너뜁니다.",
)
requires_generated_data = pytest.mark.skipif(
    not (DATA_DIR / "tg_manual_source.jsonl").exists(),
    reason="생성된 매뉴얼 JSONL이 없어 건너뜁니다.",
)


# --------------------------------------------------------------------------- #
# 파서
# --------------------------------------------------------------------------- #
@requires_docx
def test_parse_docx_extracts_metadata_and_sections() -> None:
    parsed = parse_manual_docx(DOCX_PATH)

    assert parsed.metadata["문서번호"] == "FV-TG-OM-001"
    assert parsed.metadata["문서 버전"] == "1.0"
    assert len(parsed.records) == 284

    numbers = [record["section_no"] for record in parsed.records]
    assert numbers == list(range(1, len(parsed.records) + 1))
    assert len({record["chunk_id"] for record in parsed.records}) == len(numbers)


@requires_docx
def test_parse_docx_assigns_pages_and_numbered_titles() -> None:
    records = parse_manual_docx(DOCX_PATH).records

    for record in records:
        assert str(record["pdf_page"]).isdigit() and int(record["pdf_page"]) > 0
        assert record["pdf_page"] == record["manual_page"]
        assert record["title"].startswith(record["section_number"])
        assert record["content"].strip()
        assert record["review_status"] == "pending"


@requires_docx
def test_parse_docx_bundles_heading4_as_bracket_subheadings() -> None:
    records = parse_manual_docx(DOCX_PATH).records
    esv = next(r for r in records if "ESV Close" in r["title"])

    assert "[Turboset]" in esv["content"]
    assert "[진공 System]" in esv["content"]
    # 개요문은 첫 소제목보다 앞에 있어야 한다.
    assert esv["content"].index("Shut Down Sequence") < esv["content"].index(
        "[Turboset]"
    )


@requires_docx
def test_parse_docx_is_deterministic() -> None:
    first = parse_manual_docx(DOCX_PATH).records
    second = parse_manual_docx(DOCX_PATH).records
    assert first == second


# --------------------------------------------------------------------------- #
# 전처리(일반화된 분리 규칙)
# --------------------------------------------------------------------------- #
def _source(content: str) -> dict:
    return {
        "chunk_id": "m-001",
        "section_no": 1,
        "pdf_page": 1,
        "manual_page": 1,
        "title": "예시 절",
        "content": content,
        "review_status": "pending",
    }


def test_preprocess_keeps_intro_before_subheading_as_leading_chunk() -> None:
    content = "이 절은 계통별 점검을 설명한다.\n[복수기 계통]\n- " + "가" * 1190
    chunks = preprocess_records([_source(content)])

    assert len(chunks) == 2
    assert chunks[0]["chunk_id"] == "m-001-s01"
    assert chunks[0]["parent_chunk_id"] == "m-001"
    assert chunks[0]["title"] == "예시 절"
    assert chunks[0]["content"] == "이 절은 계통별 점검을 설명한다."
    assert chunks[1]["title"].endswith("복수기 계통")
    assert all(len(chunk["content"]) <= 1200 for chunk in chunks)


def test_preprocess_line_splits_long_text_without_subheadings() -> None:
    line = "터빈 윤활유 압력을 확인한다."
    content = "\n".join([line] * 120)
    chunks = preprocess_records([_source(content)])

    assert len(chunks) >= 2
    assert all(len(chunk["content"]) <= 1200 for chunk in chunks)
    assert all(chunk["parent_chunk_id"] == "m-001" for chunk in chunks)
    assert all(chunk["title"] == "예시 절" for chunk in chunks)


def test_preprocess_rejects_unsplittable_long_line() -> None:
    with pytest.raises(ValueError, match="without a safe heading"):
        preprocess_records([_source("가" * 1201)])


@requires_generated_data
def test_committed_search_chunks_reproduce_from_source() -> None:
    import json

    source_path = (
        Path(__file__).parents[1] / "data" / "tg_manual" / "tg_manual_source.jsonl"
    )
    search_path = (
        Path(__file__).parents[1]
        / "data"
        / "tg_manual"
        / "tg_manual_search_chunks.jsonl"
    )
    source = [
        json.loads(line)
        for line in source_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    committed = [
        json.loads(line)
        for line in search_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert preprocess_records(source) == committed
    assert max(len(chunk["content"]) for chunk in committed) <= 1200


# --------------------------------------------------------------------------- #
# 적재 오케스트레이션 (임베딩·DB는 가짜로 주입)
# --------------------------------------------------------------------------- #
class _FakeResult:
    def __init__(self, scalar=None, mapping=None) -> None:
        self._scalar = scalar
        self._mapping = mapping

    def scalar_one(self):
        return self._scalar

    def mappings(self):
        return self

    def one_or_none(self):
        return self._mapping

    def all(self):
        return []


class _FakeSession:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append(sql)
        if "RETURNING id" in sql:
            return _FakeResult(scalar=1)
        if "has_embedding" in sql:  # 기존 청크 조회 → 항상 신규
            return _FakeResult(mapping=None)
        return _FakeResult()

    @contextlib.contextmanager
    def begin(self):
        yield self


class _FakeEmbedding:
    def __init__(self) -> None:
        self.calls = 0

    def embed_one(self, value: str) -> list[float]:
        self.calls += 1
        return [0.01] * 1024


@requires_docx
def test_ingest_docx_path_embeds_every_chunk() -> None:
    db = _FakeSession()
    embedding = _FakeEmbedding()

    result = ingest_manual_docx_path(
        DOCX_PATH,
        db=db,
        embedding_client=embedding,
        settings=get_settings(),
    )

    assert result.sections == 284
    assert result.search_chunks == 500
    assert result.embedded == 500
    assert result.reused == 0
    assert embedding.calls == 500
    assert result.document_no == "FV-TG-OM-001"
    assert result.source_name == "fv-tg-om-001"


# --------------------------------------------------------------------------- #
# 업로드 API
# --------------------------------------------------------------------------- #
@requires_docx
def test_preview_endpoint_returns_pipeline_summary() -> None:
    client = TestClient(create_app())
    with open(DOCX_PATH, "rb") as handle:
        response = client.post(
            "/v2/manual/documents/preview",
            files={"file": ("manual.docx", handle, DOCX_CONTENT_TYPE)},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["sections"] == 284
    assert body["search_chunks"] == 500
    assert body["max_content_length"] <= 1200
    assert body["metadata"]["문서번호"] == "FV-TG-OM-001"
    assert len(body["sample"]) == 5


@requires_docx
def test_upload_endpoint_ingests_with_injected_dependencies() -> None:
    app = create_app()
    embedding = _FakeEmbedding()
    app.dependency_overrides[get_db_ai] = lambda: _FakeSession()
    app.dependency_overrides[get_embedding_client] = lambda: embedding
    client = TestClient(app)

    with open(DOCX_PATH, "rb") as handle:
        response = client.post(
            "/v2/manual/documents",
            files={"file": ("manual.docx", handle, DOCX_CONTENT_TYPE)},
            data={"source_name": "test-manual"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["source_name"] == "test-manual"
    assert body["embedded"] == 500
    assert body["search_chunks"] == 500
    assert embedding.calls == 500
    app.dependency_overrides.clear()


def test_upload_endpoint_rejects_non_docx() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/v2/manual/documents",
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 415


@requires_docx
def test_upload_endpoint_reports_missing_embedding_server() -> None:
    app = create_app()
    no_embedding = get_settings().model_copy(
        update={"embedding_base_url": None, "llm_base_url": None}
    )
    app.dependency_overrides[get_settings] = lambda: no_embedding
    client = TestClient(app)

    with open(DOCX_PATH, "rb") as handle:
        response = client.post(
            "/v2/manual/documents",
            files={"file": ("manual.docx", handle, DOCX_CONTENT_TYPE)},
        )

    assert response.status_code == 503
    app.dependency_overrides.clear()
