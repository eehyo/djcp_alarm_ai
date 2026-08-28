"""매뉴얼 DOCX 적재 오케스트레이션.

``parse_manual_docx`` → ``preprocess_records`` → ``index_records``로 이어지는
표준 파이프라인을 하나로 묶어, CLI·업로드 API·테스트가 같은 경로를 공유합니다.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from djcp_alarm_ai.cli.index_manual import build_index_records, index_records
from djcp_alarm_ai.cli.parse_manual_docx import ParsedManual, parse_manual_docx
from djcp_alarm_ai.cli.preprocess_manual import MAX_CHUNK_CHARS, preprocess_records
from djcp_alarm_ai.config import Settings, get_settings
from djcp_alarm_ai.manual_rag import EmbeddingClient


DEFAULT_SOURCE_NAME = "tg-emergency-manual"
PARSE_VERSION = "docx-1"


@dataclass(frozen=True)
class ManualIngestResult:
    source_name: str
    document_version: str | None
    document_no: str | None
    file_hash: str
    sections: int
    search_chunks: int
    embedded: int
    reused: int
    metadata: dict[str, str]


def ingest_manual(
    parsed: ParsedManual,
    *,
    file_hash: str,
    source_name: str | None = None,
    document_version: str | None = None,
    db: Session | None = None,
    embedding_client: EmbeddingClient | None = None,
    settings: Settings | None = None,
    max_chunk_chars: int = MAX_CHUNK_CHARS,
) -> ManualIngestResult:
    """파싱된 매뉴얼을 전처리·임베딩하여 pgvector에 적재합니다.

    ``db``를 넘기면 호출자가 트랜잭션을 관리하고, 넘기지 않으면 자체 세션을 엽니다.
    """
    settings = settings or get_settings()
    search_chunks = preprocess_records(parsed.records, max_chunk_chars=max_chunk_chars)
    index_records_list = build_index_records(search_chunks)

    resolved_source = source_name or _default_source_name(parsed.metadata)
    resolved_version = document_version or parsed.metadata.get("문서 버전")

    embedded, reused = index_records(
        records=index_records_list,
        source_name=resolved_source,
        file_hash=file_hash,
        document_version=resolved_version,
        parse_version=PARSE_VERSION,
        db=db,
        embedding_client=embedding_client,
        settings=settings,
    )
    return ManualIngestResult(
        source_name=resolved_source,
        document_version=resolved_version,
        document_no=parsed.metadata.get("문서번호"),
        file_hash=file_hash,
        sections=len(parsed.records),
        search_chunks=len(search_chunks),
        embedded=embedded,
        reused=reused,
        metadata=parsed.metadata,
    )


def ingest_manual_docx_path(
    docx_path: Path,
    *,
    source_name: str | None = None,
    document_version: str | None = None,
    db: Session | None = None,
    embedding_client: EmbeddingClient | None = None,
    settings: Settings | None = None,
) -> ManualIngestResult:
    data = Path(docx_path).read_bytes()
    return ingest_manual(
        parse_manual_docx(docx_path),
        file_hash=hashlib.sha256(data).hexdigest(),
        source_name=source_name,
        document_version=document_version,
        db=db,
        embedding_client=embedding_client,
        settings=settings,
    )


def _default_source_name(metadata: dict[str, str]) -> str:
    document_no = metadata.get("문서번호")
    return document_no.strip().lower() if document_no else DEFAULT_SOURCE_NAME
