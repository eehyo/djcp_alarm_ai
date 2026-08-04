import logging
import re
from dataclasses import dataclass
from typing import Protocol

from openai import OpenAI, OpenAIError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from djcp_alarm_ai.config import Settings, get_settings
from djcp_alarm_ai.schemas import AnalysisContext, ManualChunk


logger = logging.getLogger(__name__)

MAX_MANUAL_RESULTS = 2

MANUAL_SEARCH_SQL = text(
    """
    WITH ranked AS (
        SELECT
            md.source_name,
            mc.chunk_key,
            mc.section_title,
            mc.pdf_page_start,
            mc.pdf_page_end,
            mc.printed_page_start,
            mc.printed_page_end,
            mc.content,
            1 - (mc.embedding <=> CAST(:query_embedding AS vector)) AS similarity
        FROM test.manual_chunk mc
        JOIN test.manual_document md ON md.id = mc.document_id
        WHERE mc.is_active = TRUE
          AND mc.embedding IS NOT NULL
    )
    SELECT *
    FROM ranked
    WHERE similarity >= :candidate_min_similarity
    ORDER BY similarity DESC, chunk_key
    LIMIT :candidate_limit
    """
)


@dataclass(frozen=True)
class ManualIntent:
    required: bool


@dataclass(frozen=True)
class ManualSearchCandidate:
    source_name: str
    chunk_id: str
    title: str
    pdf_page: str
    manual_page: str | None
    content: str
    similarity: float


class EmbeddingClient(Protocol):
    def embed_one(self, value: str) -> list[float]:
        ...


class ManualSearchRepository(Protocol):
    def search(
        self,
        query_embedding: list[float],
        *,
        candidate_limit: int,
        candidate_min_similarity: float,
    ) -> list[ManualSearchCandidate]:
        ...


class ManualRetriever(Protocol):
    def retrieve(self, context: AnalysisContext) -> list[ManualChunk]:
        ...


class NullManualRetriever:
    def retrieve(self, context: AnalysisContext) -> list[ManualChunk]:
        return []


class OpenAICompatibleEmbeddingClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        base_url = self.settings.embedding_base_url or self.settings.llm_base_url
        if not base_url:
            raise ValueError("EMBEDDING_BASE_URL or LLM_BASE_URL is required")
        self.client = OpenAI(
            api_key=(
                self.settings.embedding_api_key
                or self.settings.llm_api_key
                or "local"
            ),
            base_url=base_url,
            timeout=self.settings.embedding_timeout_seconds,
            max_retries=0,
        )

    def embed_one(self, value: str) -> list[float]:
        response = self.client.embeddings.create(
            model=self.settings.embedding_model,
            input=value,
        )
        embedding = list(response.data[0].embedding)
        if len(embedding) != self.settings.embedding_dimension:
            raise ValueError(
                "embedding dimension mismatch: "
                f"expected={self.settings.embedding_dimension}, actual={len(embedding)}"
            )
        return embedding


class PgVectorManualRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def search(
        self,
        query_embedding: list[float],
        *,
        candidate_limit: int,
        candidate_min_similarity: float,
    ) -> list[ManualSearchCandidate]:
        vector_literal = "[" + ",".join(str(value) for value in query_embedding) + "]"
        rows = self.db.execute(
            MANUAL_SEARCH_SQL,
            {
                "query_embedding": vector_literal,
                "candidate_limit": candidate_limit,
                "candidate_min_similarity": candidate_min_similarity,
            },
        ).mappings()
        return [
            ManualSearchCandidate(
                source_name=str(row["source_name"]),
                chunk_id=str(row["chunk_key"]),
                title=str(row["section_title"]),
                pdf_page=_format_page_range(
                    row["pdf_page_start"],
                    row["pdf_page_end"],
                ),
                manual_page=_format_optional_page_range(
                    row["printed_page_start"],
                    row["printed_page_end"],
                ),
                content=str(row["content"]),
                similarity=float(row["similarity"]),
            )
            for row in rows
        ]


class ManualRetrievalPolicy:
    _manual_terms = (
        "매뉴얼",
        "절차",
        "조치",
        "대응",
        "점검",
        "trip",
        "트립",
        "비상",
        "정전",
        "black out",
        "blackout",
        "trouble",
        "고장",
        "이상",
        "원인",
        "왜",
        "보호",
        "조건",
        "복구",
        "재기동",
        "shutdown",
        "shut down",
        "주의",
        "안전",
    )

    def classify(self, question: str) -> ManualIntent:
        normalized = _normalize_text(question)
        return ManualIntent(
            required=any(term in normalized for term in self._manual_terms)
        )

    def select(
        self,
        *,
        query_text: str,
        candidates: list[ManualSearchCandidate],
        min_similarity: float,
        high_similarity: float,
        result_limit: int,
    ) -> list[ManualChunk]:
        query_terms = _search_terms(query_text)
        query_equipment = _equipment_terms(query_text)
        ranked: list[tuple[float, ManualSearchCandidate]] = []

        for candidate in candidates:
            if candidate.similarity < min_similarity:
                continue

            candidate_text = f"{candidate.title}\n{candidate.content}"
            candidate_equipment = _equipment_terms(candidate_text)
            if (
                query_equipment
                and candidate_equipment
                and query_equipment.isdisjoint(candidate_equipment)
            ):
                continue

            lexical_overlap = query_terms & _search_terms(candidate_text)
            if candidate.similarity < high_similarity and not lexical_overlap:
                continue

            rank_score = candidate.similarity
            if query_equipment & candidate_equipment:
                rank_score += 0.04
            if lexical_overlap:
                rank_score += min(len(lexical_overlap), 3) * 0.01
            ranked.append((rank_score, candidate))

        selected: list[ManualChunk] = []
        seen: set[tuple[str, str]] = set()
        capped_limit = min(max(result_limit, 0), MAX_MANUAL_RESULTS)
        for _, candidate in sorted(
            ranked,
            key=lambda item: (-item[0], item[1].chunk_id),
        ):
            key = (candidate.source_name, candidate.chunk_id)
            if key in seen:
                continue
            seen.add(key)
            selected.append(
                ManualChunk(
                    source_name=candidate.source_name,
                    chunk_id=candidate.chunk_id,
                    title=candidate.title,
                    pdf_page=candidate.pdf_page,
                    manual_page=candidate.manual_page,
                    content=candidate.content,
                    similarity=candidate.similarity,
                )
            )
            if len(selected) >= capped_limit:
                break
        return selected


class VectorManualRetriever:
    def __init__(
        self,
        repository: ManualSearchRepository,
        embedding_client: EmbeddingClient,
        settings: Settings | None = None,
        policy: ManualRetrievalPolicy | None = None,
    ) -> None:
        self.repository = repository
        self.embedding_client = embedding_client
        self.settings = settings or get_settings()
        self.policy = policy or ManualRetrievalPolicy()

    def retrieve(self, context: AnalysisContext) -> list[ManualChunk]:
        intent = self.policy.classify(context.question)
        if not intent.required:
            return []

        query_text = build_manual_query(context)
        try:
            embedding = self.embedding_client.embed_one(query_text)
            candidates = self.repository.search(
                embedding,
                candidate_limit=self.settings.manual_rag_candidate_limit,
                candidate_min_similarity=self.settings.manual_rag_candidate_min_similarity,
            )
        except (OpenAIError, SQLAlchemyError, ValueError, IndexError) as exc:
            logger.warning("manual retrieval skipped: %s", exc)
            return []

        return self.policy.select(
            query_text=query_text,
            candidates=candidates,
            min_similarity=self.settings.manual_rag_min_similarity,
            high_similarity=self.settings.manual_rag_high_similarity,
            result_limit=self.settings.manual_rag_result_limit,
        )


def build_manual_retriever(
    db: Session,
    settings: Settings | None = None,
) -> ManualRetriever:
    settings = settings or get_settings()
    if not settings.manual_rag_enabled:
        return NullManualRetriever()
    if not (settings.embedding_base_url or settings.llm_base_url):
        logger.warning("manual RAG enabled without an embedding base URL")
        return NullManualRetriever()
    return VectorManualRetriever(
        repository=PgVectorManualRepository(db),
        embedding_client=OpenAICompatibleEmbeddingClient(settings),
        settings=settings,
    )


def build_manual_query(context: AnalysisContext) -> str:
    knowledge = context.tag_knowledge
    parts = [
        ("질문", context.question),
        ("태그명", context.tag.tag_name),
        ("표시명", context.tag.display_name),
        ("태그 설명", context.tag.description),
        ("계통", context.tag.system),
        ("알람 메시지", context.alarm.message if context.alarm else None),
        ("알람 설명", context.alarm.description if context.alarm else None),
        ("설비", context.asset.name if context.asset else None),
        ("설비 설명", context.asset.description if context.asset else None),
        (
            "상위 설비",
            " > ".join(
                item.name or item.code or ""
                for item in context.asset_path
                if item.name or item.code
            ),
        ),
        ("태그 설비 설명", knowledge.equipment_description if knowledge else None),
        ("태그 의미", knowledge.tag_description if knowledge else None),
        ("값 변화 의미", knowledge.value_change_meaning if knowledge else None),
    ]
    values: list[str] = []
    seen: set[str] = set()
    for label, raw_value in parts:
        value = str(raw_value or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        values.append(f"{label}: {value[:700]}")
    return "\n".join(values)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _search_terms(value: str) -> set[str]:
    stop_words = {
        "그리고",
        "또는",
        "에서",
        "으로",
        "이것",
        "해당",
        "알려줘",
        "설명",
        "질문",
        "태그",
        "알람",
        "현재",
        "관련",
        "상태",
    }
    return {
        token
        for token in re.findall(r"[0-9a-zA-Z가-힣]+", value.lower())
        if len(token) >= 2 and token not in stop_words
    }


def _equipment_terms(value: str) -> set[str]:
    normalized = _normalize_text(value)
    aliases = {
        "TBN": ("tbn", "t/g", "turbine", "터빈"),
        "GEN": ("gen", "generator", "발전기"),
        "BLR": ("blr", "boiler", "보일러"),
        "BFP": ("bfp", "boiler feed pump", "보일러 급수펌프", "급수펌프"),
        "DCS": ("dcs",),
        "DTR": ("dtr", "deaerator", "탈기기"),
        "CWP": ("cwp", "냉각수펌프", "냉각수 펌프"),
        "AIR_COMP": ("air compressor", "air comp", "공기압축기"),
        "BLACK_OUT": ("black out", "blackout", "정전"),
    }
    return {
        canonical
        for canonical, terms in aliases.items()
        if any(_contains_equipment_alias(normalized, term) for term in terms)
    }


def _contains_equipment_alias(value: str, alias: str) -> bool:
    if re.fullmatch(r"[a-z0-9/ ]+", alias):
        pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
        return re.search(pattern, value) is not None
    return alias in value


def _format_page_range(start: int, end: int) -> str:
    return str(start) if start == end else f"{start}-{end}"


def _format_optional_page_range(start: int | None, end: int | None) -> str | None:
    if start is None or end is None:
        return None
    return _format_page_range(start, end)
