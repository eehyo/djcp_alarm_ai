-- New operational PostgreSQL schema.
-- Included operational tables: asset, tag, alarm, maintenance
--
-- Run this migration only against a new empty database.

BEGIN;

CREATE TYPE asset_node_kind AS ENUM (
    'Plant',
    'Group',
    'Department',
    'Equipment'
);

CREATE TYPE criticality_level AS ENUM (
    'Critical',
    'High',
    'Medium',
    'Low'
);

CREATE TYPE maintenance_type AS ENUM (
    '예방정비',
    '예지정비',
    '사후정비',
    '개선공사'
);

CREATE TYPE maintenance_priority AS ENUM (
    '긴급',
    '높음',
    '보통',
    '낮음'
);

CREATE TYPE work_status AS ENUM (
    '예정',
    '진행',
    '완료',
    '지연',
    '취소'
);

CREATE TYPE alarm_severity AS ENUM (
    'Critical',
    'High',
    'Medium',
    'Low'
);

CREATE TABLE asset (
    id                      BIGSERIAL PRIMARY KEY,
    parent_id               BIGINT REFERENCES asset(id),
    code                    VARCHAR(50) NOT NULL UNIQUE,
    name                    VARCHAR(200) NOT NULL,
    node_kind               asset_node_kind NOT NULL DEFAULT 'Equipment',
    asset_type              VARCHAR(100) NOT NULL DEFAULT '',
    manufacturer            VARCHAR(200) NOT NULL DEFAULT '',
    model_name              VARCHAR(200) NOT NULL DEFAULT '',
    serial_number           VARCHAR(100) NOT NULL DEFAULT '',
    rated_capacity          VARCHAR(100) NOT NULL DEFAULT '',
    rated_speed             VARCHAR(100) NOT NULL DEFAULT '',
    status                  VARCHAR(50) NOT NULL DEFAULT '정상',
    criticality             criticality_level NOT NULL DEFAULT 'Medium',
    system_name             VARCHAR(200) NOT NULL DEFAULT '',
    location                VARCHAR(200) NOT NULL DEFAULT '',
    owner_dept              VARCHAR(100) NOT NULL DEFAULT '',
    owner_person            VARCHAR(50) NOT NULL DEFAULT '',
    install_date            DATE,
    operation_time_tag_name VARCHAR(100),
    last_alarm              VARCHAR(50),
    image_path              TEXT,
    description             TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_asset_parent_id ON asset(parent_id);
CREATE INDEX idx_asset_code ON asset(code);
CREATE INDEX idx_asset_status ON asset(status);

CREATE TABLE tag (
    id              BIGSERIAL PRIMARY KEY,
    asset_id        BIGINT NOT NULL REFERENCES asset(id),
    tag_code        VARCHAR(100) NOT NULL UNIQUE,
    tag_name        VARCHAR(200) NOT NULL,
    description     TEXT,
    unit            VARCHAR(50) NOT NULL DEFAULT '',
    alarm_high      NUMERIC(18,4),
    alarm_low       NUMERIC(18,4),
    alarm_enabled   BOOLEAN NOT NULL DEFAULT TRUE,
    current_value   NUMERIC(18,4),
    last_updated_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tag_tag_code ON tag(tag_code);
CREATE INDEX idx_tag_alarm_enabled ON tag(alarm_enabled);
CREATE INDEX idx_tag_asset_id ON tag(asset_id);
CREATE INDEX idx_tag_tag_name ON tag(tag_name);

CREATE TABLE alarm (
    id          BIGSERIAL PRIMARY KEY,
    tag_id      BIGINT NOT NULL REFERENCES tag(id),
    start_time  TIMESTAMPTZ NOT NULL,
    end_time    TIMESTAMPTZ,
    value       NUMERIC(18,4) NOT NULL,
    setpoint    NUMERIC(18,4) NOT NULL,
    severity    alarm_severity NOT NULL,
    state       VARCHAR(10) NOT NULL CHECK (state IN ('발생', '해제')),
    ack_by      VARCHAR(50)
);

CREATE INDEX idx_alarm_tag_id ON alarm(tag_id);
CREATE INDEX idx_alarm_start_time ON alarm(start_time DESC);
CREATE INDEX idx_alarm_severity ON alarm(severity);
CREATE INDEX idx_alarm_state ON alarm(state);

CREATE TABLE maintenance (
    id                  BIGSERIAL PRIMARY KEY,
    asset_id            BIGINT NOT NULL REFERENCES asset(id),
    work_name           VARCHAR(300) NOT NULL,
    maint_type          maintenance_type NOT NULL,
    priority            maintenance_priority NOT NULL DEFAULT '보통',
    plan_start_dt       TIMESTAMPTZ,
    plan_end_dt         TIMESTAMPTZ,
    actual_end_dt       TIMESTAMPTZ,
    owner               VARCHAR(100) NOT NULL DEFAULT '',
    owner_dept          VARCHAR(100) NOT NULL DEFAULT '',
    outsource_company   VARCHAR(200),
    approver            VARCHAR(50),
    status              work_status NOT NULL DEFAULT '예정',
    budget_cost         NUMERIC(15,0),
    actual_cost         NUMERIC(15,0),
    inspection_result   VARCHAR(200),
    next_due_date       DATE,
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_maintenance_asset_id ON maintenance(asset_id);
CREATE INDEX idx_maintenance_plan_start ON maintenance(plan_start_dt DESC);
CREATE INDEX idx_maintenance_status ON maintenance(status);
CREATE INDEX idx_maintenance_next_due ON maintenance(next_due_date);

COMMIT;
