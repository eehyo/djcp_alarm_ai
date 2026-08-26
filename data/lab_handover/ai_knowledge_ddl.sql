\set ON_ERROR_STOP on
CREATE EXTENSION IF NOT EXISTS vector;

-- 1) 태그 설명 지식 (태그 1:1, tag_id = FDAS.TAG_INFO.TAG_ID)
CREATE TABLE IF NOT EXISTS tag_description (
    tag_id                  INTEGER PRIMARY KEY,
    tag_name                VARCHAR(200) NOT NULL,
    description             VARCHAR(500),
    tag_nm                  VARCHAR(200),
    tag_rmk                 VARCHAR(200),
    tag_desc                VARCHAR(200),
    equipment_description   TEXT,
    tag_description         TEXT,
    value_change_meaning    TEXT,
    key_check_points        TEXT,
    action_guidance         TEXT,
    failure_guidance        TEXT,
    related_tags            JSONB,
    content_hash            VARCHAR(64),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2) 매뉴얼 RAG 저장소
CREATE TABLE IF NOT EXISTS manual_document (
    id BIGSERIAL PRIMARY KEY,
    source_name TEXT NOT NULL,
    file_hash VARCHAR(64) NOT NULL,
    document_version TEXT,
    parse_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_name, file_hash)
);

CREATE TABLE IF NOT EXISTS manual_chunk (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES manual_document(id),
    chunk_key TEXT NOT NULL UNIQUE,
    parent_chunk_key TEXT,
    section_title TEXT NOT NULL,
    pdf_page_start INTEGER NOT NULL,
    pdf_page_end INTEGER NOT NULL,
    printed_page_start INTEGER,
    printed_page_end INTEGER,
    content TEXT NOT NULL,
    embedding_text TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    embedding_model VARCHAR(100),
    embedding vector(1024),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_manual_chunk_embedding
ON manual_chunk USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_manual_chunk_active
ON manual_chunk (is_active);
