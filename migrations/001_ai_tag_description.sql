-- AI-owned tag description table.
-- Does not modify asset, tag, alarm, or maintenance.

BEGIN;

DROP SCHEMA IF EXISTS ai CASCADE;
CREATE SCHEMA IF NOT EXISTS ai;

CREATE TABLE ai.tag_description (
    tag_id                  BIGINT PRIMARY KEY REFERENCES tag(id) ON DELETE CASCADE,
    tag_name_snapshot       VARCHAR(200) NOT NULL,
    description             TEXT NOT NULL DEFAULT '',
    tag_nm                  TEXT NOT NULL DEFAULT '',
    tag_rmk                 TEXT NOT NULL DEFAULT '',
    tag_desc                TEXT NOT NULL DEFAULT '',
    equipment_description   TEXT NOT NULL DEFAULT '',
    tag_description         TEXT NOT NULL DEFAULT '',
    value_change_meaning    TEXT NOT NULL DEFAULT '',
    key_check_points        TEXT NOT NULL DEFAULT '',
    action_guidance         TEXT NOT NULL DEFAULT '',
    failure_guidance        TEXT NOT NULL DEFAULT '',
    source_version          VARCHAR(100) NOT NULL DEFAULT '',
    content_hash            VARCHAR(64) NOT NULL DEFAULT '',
    is_verified             BOOLEAN NOT NULL DEFAULT FALSE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_tag_description_tag_name_snapshot
    ON ai.tag_description(tag_name_snapshot);

COMMIT;
