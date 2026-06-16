from sqlalchemy import text
from sqlalchemy.orm import Session

from djcp_alarm_ai.config import Settings, get_settings
from djcp_alarm_ai.schemas import (
    AlarmInfo,
    AnalysisContext,
    AssetInfo,
    AssetPathItem,
    MaintenanceInfo,
    RecentAlarm,
    RelatedTag,
    TagCandidate,
    TagInfo,
    TagKnowledge,
)


ALARM_CONTEXT_SQL = text(
    """
    SELECT
        a.id AS alarm_id,
        a.tag_id,
        a.start_time,
        a.end_time,
        a.value,
        a.setpoint,
        a.severity,
        a.state,
        a.ack_by,
        t.id AS resolved_tag_id,
        t.asset_id,
        t.tag_name,
        t.description AS tag_description,
        t.unit,
        t.alarm_high,
        t.alarm_low,
        t.current_value,
        t.last_updated_at,
        s.id AS asset_id,
        s.parent_id AS asset_parent_id,
        s.code AS asset_code,
        s.name AS asset_name,
        s.asset_type,
        s.system_name,
        s.location,
        s.criticality,
        s.description AS asset_description
    FROM alarm a
    JOIN tag t ON t.id = a.tag_id
    JOIN asset s ON s.id = t.asset_id
    WHERE a.id = :alarm_id
    """
)

TAG_CONTEXT_SQL = text(
    """
    SELECT
        t.id AS resolved_tag_id,
        t.asset_id,
        t.tag_name,
        t.description AS tag_description,
        t.unit,
        t.alarm_high,
        t.alarm_low,
        t.current_value,
        t.last_updated_at,
        s.id AS asset_id,
        s.parent_id AS asset_parent_id,
        s.code AS asset_code,
        s.name AS asset_name,
        s.asset_type,
        s.system_name,
        s.location,
        s.criticality,
        s.description AS asset_description
    FROM tag t
    JOIN asset s ON s.id = t.asset_id
    WHERE t.id = :tag_id
    """
)

TAG_CANDIDATES_SQL = text(
    """
    SELECT
        t.id AS tag_id,
        t.tag_name,
        t.asset_id,
        s.name AS asset_name,
        s.code AS asset_code
    FROM tag t
    JOIN asset s ON s.id = t.asset_id
    WHERE t.tag_name = :tag_name
      AND (CAST(:asset_id AS BIGINT) IS NULL OR t.asset_id = CAST(:asset_id AS BIGINT))
    ORDER BY t.id
    """
)

RECENT_ALARMS_SQL = text(
    """
    SELECT
        a.id,
        a.tag_id,
        a.start_time,
        a.end_time,
        a.value,
        a.setpoint,
        a.severity,
        a.state,
        a.ack_by
    FROM alarm a
    WHERE a.tag_id = :tag_id
      AND (CAST(:exclude_alarm_id AS BIGINT) IS NULL OR a.id <> CAST(:exclude_alarm_id AS BIGINT))
    ORDER BY a.start_time DESC
    LIMIT :limit
    """
)

RECENT_MAINTENANCE_SQL = text(
    """
    SELECT
        m.id,
        m.asset_id,
        m.work_name,
        m.maint_type,
        m.priority,
        m.plan_start_dt,
        m.plan_end_dt,
        m.actual_end_dt,
        m.owner,
        m.owner_dept,
        m.status,
        m.inspection_result,
        m.notes
    FROM maintenance m
    WHERE m.asset_id = :asset_id
    ORDER BY COALESCE(m.actual_end_dt, m.plan_start_dt, m.created_at) DESC
    LIMIT :limit
    """
)

ASSET_PATH_SQL = text(
    """
    WITH RECURSIVE asset_path AS (
        SELECT
            a.id,
            a.parent_id,
            a.code,
            a.name,
            a.asset_type,
            0 AS depth,
            ARRAY[a.id] AS visited_ids
        FROM asset a
        WHERE a.id = :asset_id

        UNION ALL

        SELECT
            parent.id,
            parent.parent_id,
            parent.code,
            parent.name,
            parent.asset_type,
            child.depth + 1,
            child.visited_ids || parent.id
        FROM asset parent
        JOIN asset_path child ON child.parent_id = parent.id
        WHERE NOT parent.id = ANY(child.visited_ids)
    )
    SELECT id, parent_id, code, name, asset_type, depth
    FROM asset_path
    ORDER BY depth DESC
    """
)

RELATED_TAGS_SQL = text(
    """
    SELECT
        t.id,
        t.tag_name,
        t.description,
        t.unit,
        t.current_value,
        t.last_updated_at
    FROM tag t
    WHERE t.asset_id = :asset_id
      AND t.id <> :tag_id
    ORDER BY t.tag_name
    LIMIT :limit
    """
)

TAG_KNOWLEDGE_SQL = text(
    """
    SELECT
        d.tag_id,
        d.tag_name_snapshot,
        d.description,
        d.tag_nm,
        d.tag_rmk,
        d.tag_desc,
        d.equipment_description,
        d.tag_description,
        d.value_change_meaning,
        d.key_check_points,
        d.action_guidance,
        d.failure_guidance,
        d.is_verified
    FROM ai.tag_description d
    WHERE d.tag_id = :tag_id
    """
)


class OperationalRepository:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    def find_tag_candidates(self, tag_name: str, asset_id: int | None) -> list[TagCandidate]:
        rows = self.db.execute(
            TAG_CANDIDATES_SQL,
            {"tag_name": tag_name, "asset_id": asset_id},
        ).mappings()
        return [TagCandidate.model_validate(row) for row in rows]

    def load_from_alarm(self, alarm_id: int, question: str) -> AnalysisContext | None:
        row = self.db.execute(ALARM_CONTEXT_SQL, {"alarm_id": alarm_id}).mappings().one_or_none()
        if row is None:
            return None
        return self._build_context(row, question=question, alarm_id=alarm_id)

    def load_from_tag(self, tag_id: int, question: str) -> AnalysisContext | None:
        row = self.db.execute(TAG_CONTEXT_SQL, {"tag_id": tag_id}).mappings().one_or_none()
        if row is None:
            return None
        return self._build_context(row, question=question, alarm_id=None)

    def _build_context(self, row, *, question: str, alarm_id: int | None) -> AnalysisContext:
        tag_id = row["resolved_tag_id"]
        asset_id = row["asset_id"]
        alarm = None
        if alarm_id is not None:
            alarm = AlarmInfo(
                id=row["alarm_id"],
                tag_id=row["tag_id"],
                start_time=row["start_time"],
                end_time=row["end_time"],
                value=row["value"],
                setpoint=row["setpoint"],
                severity=row["severity"],
                state=row["state"],
                ack_by=row["ack_by"],
            )

        tag = TagInfo(
            id=tag_id,
            asset_id=row["asset_id"],
            tag_name=row["tag_name"],
            description=row["tag_description"],
            unit=row["unit"],
            alarm_high=row["alarm_high"],
            alarm_low=row["alarm_low"],
            current_value=row["current_value"],
            last_updated_at=row["last_updated_at"],
        )
        asset = AssetInfo(
            id=asset_id,
            parent_id=row["asset_parent_id"],
            code=row["asset_code"],
            name=row["asset_name"],
            asset_type=row["asset_type"],
            system_name=row["system_name"],
            location=row["location"],
            criticality=row["criticality"],
            description=row["asset_description"],
        )

        recent_alarm_rows = self.db.execute(
            RECENT_ALARMS_SQL,
            {
                "tag_id": tag_id,
                "exclude_alarm_id": alarm_id,
                "limit": self.settings.recent_alarm_limit,
            },
        ).mappings()
        maintenance_rows = self.db.execute(
            RECENT_MAINTENANCE_SQL,
            {"asset_id": asset_id, "limit": self.settings.recent_maintenance_limit},
        ).mappings()
        path_rows = self.db.execute(ASSET_PATH_SQL, {"asset_id": asset_id}).mappings()
        related_tag_rows = self.db.execute(
            RELATED_TAGS_SQL,
            {
                "asset_id": asset_id,
                "tag_id": tag_id,
                "limit": self.settings.related_tag_limit,
            },
        ).mappings()

        return AnalysisContext(
            question=question,
            alarm=alarm,
            tag=tag,
            asset=asset,
            asset_path=[AssetPathItem.model_validate(item) for item in path_rows],
            recent_alarms=[RecentAlarm.model_validate(item) for item in recent_alarm_rows],
            recent_maintenance=[
                MaintenanceInfo.model_validate(item) for item in maintenance_rows
            ],
            related_tags=[RelatedTag.model_validate(item) for item in related_tag_rows],
        )


class DescriptionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_tag_id(self, tag_id: int) -> TagKnowledge | None:
        row = self.db.execute(TAG_KNOWLEDGE_SQL, {"tag_id": tag_id}).mappings().one_or_none()
        return TagKnowledge.model_validate(row) if row else None
