"""매뉴얼 문서 업로드·벡터화 API.

향후 매뉴얼(.docx)을 업로드하면 표준 파이프라인(파싱→전처리→임베딩→적재)을
실행합니다. 임베딩 서버 없이 파이프라인만 점검하려면 ``/preview``를 사용합니다.
"""

import hashlib
import io
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from openai import OpenAIError
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from djcp_alarm_ai.cli.parse_manual_docx import ParsedManual, parse_manual_docx
from djcp_alarm_ai.cli.preprocess_manual import preprocess_records
from djcp_alarm_ai.config import Settings, get_settings
from djcp_alarm_ai.db import get_db_ai
from djcp_alarm_ai.manual_ingest import ingest_manual
from djcp_alarm_ai.manual_rag import (
    EmbeddingClient,
    OpenAICompatibleEmbeddingClient,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/manual", tags=["manual"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024

LIST_DOCUMENTS_SQL = """
    SELECT
        md.source_name,
        md.document_version,
        md.parse_version,
        md.file_hash,
        md.created_at,
        COUNT(mc.id) FILTER (WHERE mc.is_active) AS active_chunks
    FROM {schema}.manual_document md
    LEFT JOIN {schema}.manual_chunk mc ON mc.document_id = md.id
    GROUP BY md.id
    ORDER BY md.created_at DESC, md.source_name
"""


class ManualChunkView(BaseModel):
    chunk_id: str
    title: str
    pdf_page: int
    content_length: int


class ManualSplitSection(BaseModel):
    parent_chunk_id: str
    title: str
    parts: int
    part_chunk_ids: list[str]
    content_lengths: list[int]


class ManualPreviewResponse(BaseModel):
    metadata: dict[str, str]
    sections: int          # 원본 섹션 후보 수
    search_chunks: int     # 최종 검색 청크 수
    whole_sections: int    # 1,200자 이하로 통째 유지된 섹션 수
    split_sections: int    # 길어서 여러 청크로 쪼개진 섹션 수
    max_content_length: int
    splits: list[ManualSplitSection]   # 쪼개진 섹션의 분할 상세
    sample: list[ManualChunkView]      # 앞부분 청크 미리보기


class ManualIngestResponse(BaseModel):
    source_name: str
    document_no: str | None
    document_version: str | None
    file_hash: str
    sections: int
    search_chunks: int
    embedded: int
    reused: int


class ManualDocumentInfo(BaseModel):
    source_name: str
    document_version: str | None
    parse_version: str
    file_hash: str
    active_chunks: int
    created_at: str


def get_embedding_client(
    settings: Settings = Depends(get_settings),
) -> EmbeddingClient:
    if not (settings.embedding_base_url or settings.llm_base_url):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="임베딩 서버(EMBEDDING_BASE_URL)가 설정되지 않았습니다.",
        )
    return OpenAICompatibleEmbeddingClient(settings)


async def _read_docx_upload(file: UploadFile) -> bytes:
    name = (file.filename or "").lower()
    if not name.endswith(".docx"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="지원하지 않는 형식입니다. .docx 파일을 업로드하세요.",
        )
    data = await file.read()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="빈 파일입니다.",
        )
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"파일이 너무 큽니다(최대 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB).",
        )
    return data


def _parse_docx(data: bytes) -> ParsedManual:
    try:
        return parse_manual_docx(io.BytesIO(data))
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"문서 구조를 해석할 수 없습니다: {exc}",
        ) from exc


@router.post("/documents/preview", response_model=ManualPreviewResponse)
async def preview_manual_document(
    file: UploadFile = File(...),
) -> ManualPreviewResponse:
    """임베딩·DB 적재 없이 파싱·전처리 결과와 청크 분할 내역을 확인합니다."""
    data = await _read_docx_upload(file)
    parsed = _parse_docx(data)
    search_chunks = preprocess_records(parsed.records)

    # parent_chunk_id 로 묶어 쪼개진 섹션을 복원합니다(원문 순서 유지).
    split_groups: dict[str, list[dict]] = {}
    whole_sections = 0
    for chunk in search_chunks:
        parent = chunk["parent_chunk_id"]
        if parent is None:
            whole_sections += 1
        else:
            split_groups.setdefault(parent, []).append(chunk)

    splits = [
        ManualSplitSection(
            parent_chunk_id=parent,
            title=parts[0]["title"],
            parts=len(parts),
            part_chunk_ids=[part["chunk_id"] for part in parts],
            content_lengths=[len(part["content"]) for part in parts],
        )
        for parent, parts in split_groups.items()
    ]

    return ManualPreviewResponse(
        metadata=parsed.metadata,
        sections=len(parsed.records),
        search_chunks=len(search_chunks),
        whole_sections=whole_sections,
        split_sections=len(split_groups),
        max_content_length=max(len(c["content"]) for c in search_chunks),
        splits=splits,
        sample=[
            ManualChunkView(
                chunk_id=chunk["chunk_id"],
                title=chunk["title"],
                pdf_page=int(str(chunk["pdf_page"]).split("-")[0]),
                content_length=len(chunk["content"]),
            )
            for chunk in search_chunks[:5]
        ],
    )


@router.post("/documents", response_model=ManualIngestResponse)
async def upload_manual_document(
    file: UploadFile = File(...),
    source_name: str | None = Form(default=None),
    document_version: str | None = Form(default=None),
    db: Session = Depends(get_db_ai),
    settings: Settings = Depends(get_settings),
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
) -> ManualIngestResponse:
    """매뉴얼(.docx)을 업로드하여 파싱·전처리·임베딩 후 pgvector에 적재합니다."""
    data = await _read_docx_upload(file)
    parsed = _parse_docx(data)  # 임베딩 전에 구조 오류를 조기 검출

    try:
        with db.begin():
            result = ingest_manual(
                parsed,
                file_hash=hashlib.sha256(data).hexdigest(),
                source_name=source_name,
                document_version=document_version,
                db=db,
                embedding_client=embedding_client,
                settings=settings,
            )
    except (OpenAIError, ValueError) as exc:
        logger.warning("manual ingest failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"임베딩·적재에 실패했습니다: {exc}",
        ) from exc

    return ManualIngestResponse(
        source_name=result.source_name,
        document_no=result.document_no,
        document_version=result.document_version,
        file_hash=result.file_hash,
        sections=result.sections,
        search_chunks=result.search_chunks,
        embedded=result.embedded,
        reused=result.reused,
    )


@router.get("/documents", response_model=list[ManualDocumentInfo])
def list_manual_documents(
    db: Session = Depends(get_db_ai),
    settings: Settings = Depends(get_settings),
) -> list[ManualDocumentInfo]:
    sql = text(LIST_DOCUMENTS_SQL.format(schema=settings.ai_schema))
    try:
        rows = db.execute(sql).mappings().all()
    except SQLAlchemyError as exc:
        logger.warning("manual document listing failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="매뉴얼 문서 목록을 조회할 수 없습니다.",
        ) from exc
    return [
        ManualDocumentInfo(
            source_name=str(row["source_name"]),
            document_version=row["document_version"],
            parse_version=str(row["parse_version"]),
            file_hash=str(row["file_hash"]),
            active_chunks=int(row["active_chunks"] or 0),
            created_at=row["created_at"].isoformat(),
        )
        for row in rows
    ]
