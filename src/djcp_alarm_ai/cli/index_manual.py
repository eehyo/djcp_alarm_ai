import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text

from djcp_alarm_ai.config import get_settings
from djcp_alarm_ai.db import AiSession
from djcp_alarm_ai.manual_rag import OpenAICompatibleEmbeddingClient


DEFAULT_INPUT = (
    Path(__file__).parents[3]
    / "data"
    / "tg_manual"
    / "tg_manual_search_chunks_003_015.jsonl"
)

UPSERT_DOCUMENT_SQL = text(
    """
    INSERT INTO public.manual_document (
        source_name, file_hash, document_version, parse_version
    )
    VALUES (:source_name, :file_hash, :document_version, :parse_version)
    ON CONFLICT (source_name, file_hash) DO UPDATE SET
        document_version = EXCLUDED.document_version,
        parse_version = EXCLUDED.parse_version
    RETURNING id
    """
)

DEACTIVATE_SOURCE_SQL = text(
    """
    UPDATE public.manual_chunk mc
    SET is_active = FALSE, updated_at = NOW()
    FROM public.manual_document md
    WHERE mc.document_id = md.id
      AND md.source_name = :source_name
    """
)

EXISTING_CHUNK_SQL = text(
    """
    SELECT content_hash, embedding_model, embedding IS NOT NULL AS has_embedding
    FROM public.manual_chunk
    WHERE chunk_key = :chunk_key
    """
)

REFRESH_CHUNK_SQL = text(
    """
    UPDATE public.manual_chunk
    SET
        document_id = :document_id,
        parent_chunk_key = :parent_chunk_key,
        section_title = :section_title,
        pdf_page_start = :pdf_page_start,
        pdf_page_end = :pdf_page_end,
        printed_page_start = :printed_page_start,
        printed_page_end = :printed_page_end,
        content = :content,
        embedding_text = :embedding_text,
        is_active = TRUE,
        updated_at = NOW()
    WHERE chunk_key = :chunk_key
    """
)

UPSERT_CHUNK_SQL = text(
    """
    INSERT INTO public.manual_chunk (
        document_id,
        chunk_key,
        parent_chunk_key,
        section_title,
        pdf_page_start,
        pdf_page_end,
        printed_page_start,
        printed_page_end,
        content,
        embedding_text,
        content_hash,
        embedding_model,
        embedding,
        is_active,
        updated_at
    )
    VALUES (
        :document_id,
        :chunk_key,
        :parent_chunk_key,
        :section_title,
        :pdf_page_start,
        :pdf_page_end,
        :printed_page_start,
        :printed_page_end,
        :content,
        :embedding_text,
        :content_hash,
        :embedding_model,
        CAST(:embedding AS vector),
        TRUE,
        NOW()
    )
    ON CONFLICT (chunk_key) DO UPDATE SET
        document_id = EXCLUDED.document_id,
        parent_chunk_key = EXCLUDED.parent_chunk_key,
        section_title = EXCLUDED.section_title,
        pdf_page_start = EXCLUDED.pdf_page_start,
        pdf_page_end = EXCLUDED.pdf_page_end,
        printed_page_start = EXCLUDED.printed_page_start,
        printed_page_end = EXCLUDED.printed_page_end,
        content = EXCLUDED.content,
        embedding_text = EXCLUDED.embedding_text,
        content_hash = EXCLUDED.content_hash,
        embedding_model = EXCLUDED.embedding_model,
        embedding = EXCLUDED.embedding,
        is_active = TRUE,
        updated_at = NOW()
    """
)


@dataclass(frozen=True)
class ManualIndexRecord:
    chunk_key: str
    parent_chunk_key: str | None
    section_title: str
    pdf_page_start: int
    pdf_page_end: int
    printed_page_start: int | None
    printed_page_end: int | None
    content: str
    embedding_text: str
    content_hash: str


def load_manual_records(input_path: Path) -> list[ManualIndexRecord]:
    records: list[ManualIndexRecord] = []
    for line in input_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)

        pdf_start, pdf_end = parse_page_range(str(payload["pdf_page"]))
        printed_start, printed_end = parse_page_range(
            str(payload["manual_page"]),
        )
        content = str(payload["content"]).strip()
        title = str(payload["title"]).strip()
        embedding_text = build_embedding_text(
            title=title,
            content=content,
        )
        content_hash = hashlib.sha256(
            f"{title}\n{content}".encode("utf-8")
        ).hexdigest()
        records.append(
            ManualIndexRecord(
                chunk_key=str(payload["chunk_id"]),
                parent_chunk_key=payload.get("parent_chunk_id"),
                section_title=title,
                pdf_page_start=pdf_start,
                pdf_page_end=pdf_end,
                printed_page_start=printed_start,
                printed_page_end=printed_end,
                content=content,
                embedding_text=embedding_text,
                content_hash=content_hash,
            )
        )
    return records


def parse_page_range(value: str) -> tuple[int, int]:
    parts = [int(part.strip()) for part in value.split("-", maxsplit=1)]
    return (parts[0], parts[0]) if len(parts) == 1 else (parts[0], parts[1])


def build_embedding_text(*, title: str, content: str) -> str:
    return f"제목: {title}\n본문:\n{content}"


def index_records(
    *,
    records: list[ManualIndexRecord],
    source_name: str,
    file_hash: str,
    document_version: str | None,
    parse_version: str,
) -> tuple[int, int]:
    settings = get_settings()
    embedding_client = OpenAICompatibleEmbeddingClient(settings)
    embedded = 0
    reused = 0

    with AiSession() as db, db.begin():
        document_id = db.execute(
            UPSERT_DOCUMENT_SQL,
            {
                "source_name": source_name,
                "file_hash": file_hash,
                "document_version": document_version,
                "parse_version": parse_version,
            },
        ).scalar_one()
        db.execute(DEACTIVATE_SOURCE_SQL, {"source_name": source_name})

        for record in records:
            values = {
                "document_id": document_id,
                **record.__dict__,
            }
            existing = db.execute(
                EXISTING_CHUNK_SQL,
                {"chunk_key": record.chunk_key},
            ).mappings().one_or_none()
            if (
                existing
                and existing["content_hash"] == record.content_hash
                and existing["embedding_model"] == settings.embedding_model
                and existing["has_embedding"]
            ):
                db.execute(REFRESH_CHUNK_SQL, values)
                reused += 1
                continue

            embedding = embedding_client.embed_one(record.embedding_text)
            db.execute(
                UPSERT_CHUNK_SQL,
                {
                    **values,
                    "embedding_model": settings.embedding_model,
                    "embedding": "[" + ",".join(str(value) for value in embedding) + "]",
                },
            )
            embedded += 1

    return embedded, reused


def main() -> None:
    parser = argparse.ArgumentParser(
        description="검수된 매뉴얼 JSONL을 임베딩하고 pgvector에 적재합니다.",
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--source-name", default="tg-emergency-manual")
    parser.add_argument("--document-version")
    parser.add_argument("--parse-version", default="3")
    args = parser.parse_args()

    source_bytes = args.input.read_bytes()
    records = load_manual_records(args.input)
    if not records:
        parser.error("적재 가능한 청크가 없습니다.")
    embedded, reused = index_records(
        records=records,
        source_name=args.source_name,
        file_hash=hashlib.sha256(source_bytes).hexdigest(),
        document_version=args.document_version,
        parse_version=args.parse_version,
    )
    print(
        f"manual index complete: total={len(records)} embedded={embedded} reused={reused}"
    )


if __name__ == "__main__":
    main()
