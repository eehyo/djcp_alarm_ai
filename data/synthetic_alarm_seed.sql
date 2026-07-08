-- Synthetic alarm data for LLM/context speed testing.
-- Run only against a demo/test database after:
--   1) data/demo_seed.sql
--   2) djcp-seed-description-tags --split-boilers
--   3) djcp-description-sync
--
-- Inserts up to 10 synthetic alarms for each of 5 tags:
--   BBAIT-801, BBPIT-401, BBFIT-401, BBFCD-401, BBTE-101A

BEGIN;

DO $$
DECLARE
    missing_tags TEXT;
    unsafe_tags TEXT;
BEGIN
    SELECT string_agg(target.tag_name, ', ' ORDER BY target.tag_name)
    INTO missing_tags
    FROM (
        VALUES
            ('BBAIT-801'),
            ('BBPIT-401'),
            ('BBFIT-401'),
            ('BBFCD-401'),
            ('BBTE-101A')
    ) AS target(tag_name)
    LEFT JOIN tag t ON t.tag_name = target.tag_name
    WHERE t.id IS NULL;

    IF missing_tags IS NOT NULL THEN
        RAISE EXCEPTION
            'Synthetic alarm seed refused. Missing tag rows: %. Run djcp-seed-description-tags --split-boilers first.',
            missing_tags;
    END IF;

    SELECT string_agg(t.tag_name || '(' || t.tag_code || ')', ', ' ORDER BY t.tag_name)
    INTO unsafe_tags
    FROM tag t
    WHERE t.tag_name IN (
        'BBAIT-801',
        'BBPIT-401',
        'BBFIT-401',
        'BBFCD-401',
        'BBTE-101A'
    )
      AND t.tag_code NOT LIKE 'DEMO-%'
      AND t.tag_code NOT LIKE 'DESC-%';

    IF unsafe_tags IS NOT NULL THEN
        RAISE EXCEPTION
            'Synthetic alarm seed refused. Target tags do not look like demo tags: %',
            unsafe_tags;
    END IF;
END
$$;

WITH target_tags AS (
    SELECT *
    FROM (
        VALUES
            (1, 'BBAIT-801', '연소가스 산소 농도', '%',      10.0000::numeric, 10.8000::numeric, 0.1800::numeric),
            (2, 'BBPIT-401', '실 에어 송풍기 토출 압력', 'kPa',  8.0000::numeric,  8.4000::numeric, 0.1600::numeric),
            (3, 'BBFIT-401', '보일러 공기 유량', 'Nm3/h',       220.0000::numeric, 225.0000::numeric, 2.5000::numeric),
            (4, 'BBFCD-401', 'FD Fan 출력 명령', '%',           85.0000::numeric,  88.0000::numeric, 0.9000::numeric),
            (5, 'BBTE-101A', '드럼 메탈 온도 상부 좌측', 'degC', 430.0000::numeric, 432.0000::numeric, 1.8000::numeric)
    ) AS target(tag_order, tag_name, description, unit, setpoint, base_value, step_value)
),
updated_tags AS (
    UPDATE tag t
    SET
        description = target.description,
        unit = target.unit,
        alarm_high = target.setpoint,
        current_value = target.base_value + target.step_value * 10,
        last_updated_at = '2026-06-25 10:00:00+09'::timestamptz
    FROM target_tags target
    WHERE t.tag_name = target.tag_name
    RETURNING
        t.id,
        t.tag_name,
        target.tag_order,
        target.setpoint,
        target.base_value,
        target.step_value
),
synthetic_rows AS (
    SELECT
        t.id AS tag_id,
        t.tag_name,
        ('2026-06-25 10:00:00+09'::timestamptz
            - (t.tag_order * interval '1 day')
            - (g.alarm_no * interval '1 hour')) AS start_time,
        CASE
            WHEN g.alarm_no IN (3, 6, 9)
                THEN ('2026-06-25 10:00:00+09'::timestamptz
                    - (t.tag_order * interval '1 day')
                    - (g.alarm_no * interval '1 hour')
                    + interval '25 minutes')
            ELSE NULL
        END AS end_time,
        (t.base_value + t.step_value * g.alarm_no)::numeric(18,4) AS value,
        t.setpoint::numeric(18,4) AS setpoint,
        CASE
            WHEN g.alarm_no IN (4, 8, 10) THEN 'High'::alarm_severity
            ELSE 'Medium'::alarm_severity
        END AS severity,
        CASE
            WHEN g.alarm_no IN (3, 6, 9) THEN '해제'
            ELSE '발생'
        END AS state,
        CASE
            WHEN g.alarm_no IN (3, 6, 9) THEN 'synthetic-operator'
            ELSE NULL
        END AS ack_by
    FROM updated_tags t
    CROSS JOIN generate_series(1, 10) AS g(alarm_no)
)
INSERT INTO alarm (tag_id, start_time, end_time, value, setpoint, severity, state, ack_by)
SELECT
    row.tag_id,
    row.start_time,
    row.end_time,
    row.value,
    row.setpoint,
    row.severity,
    row.state,
    row.ack_by
FROM synthetic_rows row
WHERE NOT EXISTS (
    SELECT 1
    FROM alarm existing
    WHERE existing.tag_id = row.tag_id
      AND existing.start_time = row.start_time
      AND COALESCE(existing.ack_by, '') = COALESCE(row.ack_by, '')
);

COMMIT;

SELECT
    t.tag_name,
    COUNT(a.id) AS alarm_count,
    MAX(a.start_time) AS latest_alarm_time
FROM tag t
LEFT JOIN alarm a ON a.tag_id = t.id
WHERE t.tag_name IN (
    'BBAIT-801',
    'BBPIT-401',
    'BBFIT-401',
    'BBFCD-401',
    'BBTE-101A'
)
GROUP BY t.tag_name
ORDER BY t.tag_name;
