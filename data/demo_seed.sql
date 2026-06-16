-- Demo-only operational data for testing the complete alarm analysis flow.
-- Run only against a new or demo database.

BEGIN;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM asset WHERE code NOT LIKE 'DEMO-%')
       OR EXISTS (
           SELECT 1
           FROM tag
           WHERE tag_code NOT LIKE 'DEMO-%'
             AND tag_code NOT LIKE 'DESC-%'
       ) THEN
        RAISE EXCEPTION 'Demo seed refused: non-demo asset or tag data already exists';
    END IF;
END
$$;

INSERT INTO asset (code, name, node_kind, asset_type, status, criticality)
VALUES ('DEMO-PLANT', '데모 발전소', 'Plant', 'Plant', '정상', 'Medium')
ON CONFLICT (code) DO UPDATE SET
    name = EXCLUDED.name;

INSERT INTO asset (parent_id, code, name, node_kind, asset_type, status, criticality)
SELECT id, 'DEMO-UNIT-1', '데모 1호기', 'Group', 'Unit', '정상', 'Medium'
FROM asset
WHERE code = 'DEMO-PLANT'
ON CONFLICT (code) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    name = EXCLUDED.name;

INSERT INTO asset (parent_id, code, name, node_kind, asset_type, status, criticality)
SELECT id, 'DEMO-UNIT-2', '데모 2호기', 'Group', 'Unit', '정상', 'Medium'
FROM asset
WHERE code = 'DEMO-PLANT'
ON CONFLICT (code) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    name = EXCLUDED.name;

INSERT INTO asset (
    parent_id, code, name, node_kind, asset_type, status, criticality,
    system_name, location, description
)
SELECT
    id, 'DEMO-BOILER-1', '데모 1호기 보일러', 'Equipment', 'Boiler', '정상', 'High',
    '보일러 계통', '데모 1호기', '알람 분석 파이프라인 테스트 설비'
FROM asset
WHERE code = 'DEMO-UNIT-1'
ON CONFLICT (code) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    name = EXCLUDED.name,
    description = EXCLUDED.description;

INSERT INTO asset (
    parent_id, code, name, node_kind, asset_type, status, criticality,
    system_name, location, description
)
SELECT
    id, 'DEMO-BOILER-2', '데모 2호기 보일러', 'Equipment', 'Boiler', '정상', 'High',
    '보일러 계통', '데모 2호기', '알람 분석 파이프라인 테스트 설비'
FROM asset
WHERE code = 'DEMO-UNIT-2'
ON CONFLICT (code) DO UPDATE SET
    parent_id = EXCLUDED.parent_id,
    name = EXCLUDED.name,
    description = EXCLUDED.description;

INSERT INTO tag (
    asset_id, tag_code, tag_name, description, unit,
    alarm_high, alarm_enabled, current_value, last_updated_at
)
SELECT
    id, 'DEMO-BBAIT-801', 'BBAIT-801', '연소가스 산소 농도', '%',
    10.0000, TRUE, 12.4000, NOW()
FROM asset
WHERE code = 'DEMO-BOILER-1'
ON CONFLICT (tag_code) DO UPDATE SET
    asset_id = EXCLUDED.asset_id,
    tag_name = EXCLUDED.tag_name,
    description = EXCLUDED.description,
    unit = EXCLUDED.unit,
    alarm_high = EXCLUDED.alarm_high,
    current_value = EXCLUDED.current_value,
    last_updated_at = EXCLUDED.last_updated_at;

UPDATE tag
SET asset_id = (SELECT id FROM asset WHERE code = 'DEMO-BOILER-1')
WHERE tag_name LIKE 'BB%';

UPDATE tag
SET asset_id = (SELECT id FROM asset WHERE code = 'DEMO-BOILER-2')
WHERE tag_name LIKE 'BC%';

INSERT INTO alarm (tag_id, start_time, end_time, value, setpoint, severity, state, ack_by)
SELECT
    id, '2026-06-12 09:00:00+09', NULL, 12.4000, 10.0000, 'High', '발생', NULL
FROM tag
WHERE tag_code = 'DEMO-BBAIT-801'
  AND NOT EXISTS (
      SELECT 1
      FROM alarm
      WHERE tag_id = tag.id
        AND start_time = '2026-06-12 09:00:00+09'
  );

INSERT INTO alarm (tag_id, start_time, end_time, value, setpoint, severity, state, ack_by)
SELECT
    id, '2026-06-10 09:00:00+09', '2026-06-10 09:20:00+09',
    11.3000, 10.0000, 'Medium', '해제', 'demo-operator'
FROM tag
WHERE tag_code = 'DEMO-BBAIT-801'
  AND NOT EXISTS (
      SELECT 1
      FROM alarm
      WHERE tag_id = tag.id
        AND start_time = '2026-06-10 09:00:00+09'
  );

INSERT INTO maintenance (
    asset_id, work_name, maint_type, priority, actual_end_dt,
    owner, owner_dept, status, inspection_result, notes
)
SELECT
    id, '데모 산소 분석기 점검', '예방정비', '보통', '2026-06-01 15:00:00+09',
    'demo-operator', '운영팀', '완료', '센서 오염 없음', '파이프라인 테스트 데이터'
FROM asset
WHERE code = 'DEMO-BOILER-1'
  AND NOT EXISTS (
      SELECT 1
      FROM maintenance
      WHERE asset_id = asset.id
        AND work_name = '데모 산소 분석기 점검'
  );

COMMIT;

SELECT
    alarm.id AS demo_alarm_id,
    tag.id AS demo_tag_id,
    tag.tag_name,
    asset.id AS demo_asset_id
FROM alarm
JOIN tag ON tag.id = alarm.tag_id
JOIN asset ON asset.id = tag.asset_id
WHERE tag.tag_code = 'DEMO-BBAIT-801'
  AND alarm.state = '발생'
ORDER BY alarm.start_time DESC
LIMIT 1;
