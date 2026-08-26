from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from djcp_alarm_ai.config import Settings, get_settings
from djcp_alarm_ai.tag_extractor import extract_keywords, extract_tag_tokens
from djcp_alarm_ai.schemas import (
    AlarmInfo,
    AnalysisContext,
    AssetInfo,
    AssetPathItem,
    LotoInfo,
    MaintenanceInfo,
    MimicInfo,
    RelatedTag,
    RelatedTagReference,
    TagCandidate,
    TagInfo,
    TagKnowledge,
)

_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


RECENT_ALARMS_SQL = text(
    """
    SELECT
        av."TIMESTAMP" AS timestamp,
        av."TAG_ID" AS tag_id,
        av."TAG_NAME" AS tag_name,
        av."DESCRIPTION" AS description,
        av."PRIORITY" AS priority,
        av."VALUE" AS value,
        av."IS_ALM" AS is_alm,
        av."MESSAGE" AS message,
        av."IS_ACK" AS is_ack,
        av."ACK_TIME" AS ack_time
    FROM public."ALARM_VALUE" av
    ORDER BY av."TIMESTAMP" DESC, av."TAG_ID"
    LIMIT :limit
    """
)

RECENT_ALARM_CONTEXT_SQL = text(
    """
    SELECT
        av."TIMESTAMP" AS alarm_timestamp,
        av."TAG_ID" AS alarm_tag_id,
        av."TAG_NAME" AS alarm_tag_name,
        av."DESCRIPTION" AS alarm_description,
        av."PRIORITY" AS alarm_priority,
        av."VALUE" AS alarm_value,
        av."IS_ALM" AS alarm_is_alm,
        av."MESSAGE" AS alarm_message,
        av."IS_ACK" AS alarm_is_ack,
        av."ACK_TIME" AS alarm_ack_time,
        ti."TAG_ID" AS tag_id,
        ti."TAG_NAME" AS tag_name,
        ti."DESCRIPTION" AS description,
        tie."DISPLAY_NAME" AS display_name,
        tie."TAG_TYPE_CODE" AS tag_type_code,
        ti."SIG_TYPE" AS sig_type,
        ti."SYSTEM" AS system,
        ti."ENG_UNIT" AS eng_unit,
        ti."L_ENGVAL" AS l_engval,
        ti."H_ENGVAL" AS h_engval,
        NULLIF(BTRIM(ti."ALARM"), '') AS alarm,
        ti."LL_ALM_VAL" AS ll_alm_val,
        ti."LO_ALM_VAL" AS lo_alm_val,
        ti."HI_ALM_VAL" AS hi_alm_val,
        ti."HH_ALM_VAL" AS hh_alm_val,
        ti."LL_ALM_PRIO" AS ll_alm_prio,
        ti."LO_ALM_PRIO" AS lo_alm_prio,
        ti."HI_ALM_PRIO" AS hi_alm_prio,
        ti."HH_ALM_PRIO" AS hh_alm_prio,
        ti."D_ALM_PRIO1" AS d_alm_prio1,
        ti."D_ALM_PRIO2" AS d_alm_prio2,
        ti."ALM_CND" AS alm_cnd,
        ti."CLSD_MSG" AS clsd_msg,
        ti."OPEN_MSG" AS open_msg,
        NULLIF(BTRIM(ti."USED"), '') AS used
    FROM public."ALARM_VALUE" av
    JOIN public."TAG_INFO" ti ON ti."TAG_ID" = av."TAG_ID"
    LEFT JOIN public."TAG_INFO_EXT" tie ON tie."TAG_ID" = ti."TAG_ID"
    WHERE av."TAG_ID" = :tag_id
      AND av."TIMESTAMP" = :timestamp
    """
)

HISTORY_ALARM_CONTEXT_SQL = text(
    """
    SELECT
        ah."TIMESTAMP" AS alarm_timestamp,
        ah."TAG_ID" AS alarm_tag_id,
        ah."TAG_NAME" AS alarm_tag_name,
        ah."DESCRIPTION" AS alarm_description,
        ah."PRIORITY" AS alarm_priority,
        ah."VALUE" AS alarm_value,
        ah."IS_ALM" AS alarm_is_alm,
        ah."MESSAGE" AS alarm_message,
        NULL::smallint AS alarm_is_ack,
        NULL::timestamptz AS alarm_ack_time,
        ti."TAG_ID" AS tag_id,
        ti."TAG_NAME" AS tag_name,
        ti."DESCRIPTION" AS description,
        tie."DISPLAY_NAME" AS display_name,
        tie."TAG_TYPE_CODE" AS tag_type_code,
        ti."SIG_TYPE" AS sig_type,
        ti."SYSTEM" AS system,
        ti."ENG_UNIT" AS eng_unit,
        ti."L_ENGVAL" AS l_engval,
        ti."H_ENGVAL" AS h_engval,
        NULLIF(BTRIM(ti."ALARM"), '') AS alarm,
        ti."LL_ALM_VAL" AS ll_alm_val,
        ti."LO_ALM_VAL" AS lo_alm_val,
        ti."HI_ALM_VAL" AS hi_alm_val,
        ti."HH_ALM_VAL" AS hh_alm_val,
        ti."LL_ALM_PRIO" AS ll_alm_prio,
        ti."LO_ALM_PRIO" AS lo_alm_prio,
        ti."HI_ALM_PRIO" AS hi_alm_prio,
        ti."HH_ALM_PRIO" AS hh_alm_prio,
        ti."D_ALM_PRIO1" AS d_alm_prio1,
        ti."D_ALM_PRIO2" AS d_alm_prio2,
        ti."ALM_CND" AS alm_cnd,
        ti."CLSD_MSG" AS clsd_msg,
        ti."OPEN_MSG" AS open_msg,
        NULLIF(BTRIM(ti."USED"), '') AS used
    FROM public."ALARM_HIST" ah
    JOIN public."TAG_INFO" ti ON ti."TAG_ID" = ah."TAG_ID"
    LEFT JOIN public."TAG_INFO_EXT" tie ON tie."TAG_ID" = ti."TAG_ID"
    WHERE ah."TAG_ID" = :tag_id
      AND ah."TIMESTAMP" = :timestamp
    ORDER BY ah."PRIORITY", ah."IS_ALM", ah."MESSAGE"
    LIMIT 1
    """
)

TAG_CONTEXT_SQL = text(
    """
    SELECT
        ti."TAG_ID" AS tag_id,
        ti."TAG_NAME" AS tag_name,
        ti."DESCRIPTION" AS description,
        tie."DISPLAY_NAME" AS display_name,
        tie."TAG_TYPE_CODE" AS tag_type_code,
        ti."SIG_TYPE" AS sig_type,
        ti."SYSTEM" AS system,
        ti."ENG_UNIT" AS eng_unit,
        ti."L_ENGVAL" AS l_engval,
        ti."H_ENGVAL" AS h_engval,
        NULLIF(BTRIM(ti."ALARM"), '') AS alarm,
        ti."LL_ALM_VAL" AS ll_alm_val,
        ti."LO_ALM_VAL" AS lo_alm_val,
        ti."HI_ALM_VAL" AS hi_alm_val,
        ti."HH_ALM_VAL" AS hh_alm_val,
        ti."LL_ALM_PRIO" AS ll_alm_prio,
        ti."LO_ALM_PRIO" AS lo_alm_prio,
        ti."HI_ALM_PRIO" AS hi_alm_prio,
        ti."HH_ALM_PRIO" AS hh_alm_prio,
        ti."D_ALM_PRIO1" AS d_alm_prio1,
        ti."D_ALM_PRIO2" AS d_alm_prio2,
        ti."ALM_CND" AS alm_cnd,
        ti."CLSD_MSG" AS clsd_msg,
        ti."OPEN_MSG" AS open_msg,
        NULLIF(BTRIM(ti."USED"), '') AS used
    FROM public."TAG_INFO" ti
    LEFT JOIN public."TAG_INFO_EXT" tie ON tie."TAG_ID" = ti."TAG_ID"
    WHERE ti."TAG_ID" = :tag_id
    """
)

TAG_CANDIDATES_SQL = text(
    """
    SELECT
        ti."TAG_ID" AS tag_id,
        ti."TAG_NAME" AS tag_name,
        ti."DESCRIPTION" AS description,
        ti."SYSTEM" AS system,
        tie."DISPLAY_NAME" AS display_name
    FROM public."TAG_INFO" ti
    LEFT JOIN public."TAG_INFO_EXT" tie ON tie."TAG_ID" = ti."TAG_ID"
    WHERE ti."TAG_NAME" = :tag_name
    ORDER BY ti."TAG_ID"
    """
)

RESOLVE_TAGS_BY_NAMES_SQL = text(
    """
    SELECT
        ti."TAG_ID" AS tag_id,
        ti."TAG_NAME" AS tag_name,
        ti."DESCRIPTION" AS description,
        ti."SYSTEM" AS system,
        tie."DISPLAY_NAME" AS display_name
    FROM public."TAG_INFO" ti
    LEFT JOIN public."TAG_INFO_EXT" tie ON tie."TAG_ID" = ti."TAG_ID"
    WHERE upper(ti."TAG_NAME") = ANY(CAST(:names AS varchar[]))
    ORDER BY ti."TAG_ID"
    """
)

SEARCH_TAGS_BY_KEYWORDS_SQL = text(
    """
    SELECT
        ti."TAG_ID" AS tag_id,
        ti."TAG_NAME" AS tag_name,
        ti."DESCRIPTION" AS description,
        ti."SYSTEM" AS system,
        tie."DISPLAY_NAME" AS display_name
    FROM public."TAG_INFO" ti
    LEFT JOIN public."TAG_INFO_EXT" tie ON tie."TAG_ID" = ti."TAG_ID"
    WHERE ti."DESCRIPTION" ILIKE ANY(CAST(:patterns AS text[]))
    ORDER BY ti."TAG_ID"
    LIMIT :limit
    """
)

TAG_ASSETS_SQL = text(
    """
    SELECT
        a.id,
        a.parent_id,
        a.code,
        a.name,
        a.asset_type,
        a.status,
        a.criticality,
        a.system_name,
        a.location,
        a.description
    FROM public.asset_tag_link atl
    JOIN public.asset a ON a.id = atl.asset_id
    WHERE atl.tag_id = :tag_id
    ORDER BY a.id
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
        FROM public.asset a
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
        FROM public.asset parent
        JOIN asset_path child ON child.parent_id = parent.id
        WHERE NOT parent.id = ANY(child.visited_ids)
    )
    SELECT id, parent_id, code, name, asset_type, depth
    FROM asset_path
    ORDER BY depth DESC
    """
)

RECENT_MAINTENANCE_SQL = text(
    """
    SELECT
        m.id,
        m.work_code,
        m.asset_id,
        m.work_name,
        m.maint_type,
        m.priority,
        m.worker,
        m.scheduled_at,
        m.duration_minutes,
        m.completed_at,
        m.status,
        m.cost,
        m.inspection_result,
        m.next_due_date,
        m.confirmer,
        m.work_description,
        m.team_note
    FROM public.maintenance m
    WHERE m.asset_id = :asset_id
    ORDER BY COALESCE(m.completed_at, m.scheduled_at, m.created_at) DESC
    LIMIT :limit
    """
)

_LOTO_COLUMNS = """
        l.id,
        l.loto_number,
        l.asset_id,
        l.work_name,
        l.selected_asset_name,
        l.attachment_place,
        l.lockout_device,
        l.status,
        l.install_dt,
        l.release_dt
"""

# LOTO 경로 ⓐ: 태그가 속한 설비(asset_id)에 발행된 loto
LOTO_BY_ASSET_SQL = text(
    f"""
    SELECT{_LOTO_COLUMNS}
    FROM public.loto l
    WHERE l.asset_id = :asset_id
    ORDER BY l.install_dt DESC NULLS LAST, l.id DESC
    LIMIT :limit
    """
)

# LOTO 경로 ⓑ: loto_tag.tag_code = TAG_NAME 으로 매핑된 loto
LOTO_BY_TAG_CODE_SQL = text(
    f"""
    SELECT{_LOTO_COLUMNS}
    FROM public.loto_tag lt
    JOIN public.loto l ON l.id = lt.loto_id
    WHERE lt.tag_code = :tag_name
    ORDER BY l.install_dt DESC NULLS LAST, l.id DESC
    LIMIT :limit
    """
)

RECENT_HISTORY_SQL = text(
    """
    SELECT
        ah."TIMESTAMP" AS timestamp,
        ah."TAG_ID" AS tag_id,
        ah."TAG_NAME" AS tag_name,
        ah."DESCRIPTION" AS description,
        ah."PRIORITY" AS priority,
        ah."VALUE" AS value,
        ah."IS_ALM" AS is_alm,
        ah."MESSAGE" AS message,
        NULL::smallint AS is_ack,
        NULL::timestamptz AS ack_time
    FROM public."ALARM_HIST" ah
    WHERE ah."TAG_ID" = :tag_id
      AND (
        CAST(:selected_timestamp AS timestamptz) IS NULL
        OR ah."TIMESTAMP" <> CAST(:selected_timestamp AS timestamptz)
      )
    ORDER BY ah."TIMESTAMP" DESC
    LIMIT :limit
    """
)

MIMIC_SQL = text(
    """
    SELECT
        mf."FILE_PATH" AS file_path,
        mf."FILE_SIZE" AS file_size,
        mf."LAST_WRITE_TICKS" AS last_write_ticks,
        mf."CHG_DATE" AS chg_date,
        mf."CHG_ID" AS chg_id
    FROM public."MIMIC_FILE_TAG" mft
    JOIN public."MIMIC_FILE" mf ON mf."FILE_PATH" = mft."FILE_PATH"
    WHERE mft."TAG_NAME" = :tag_name
    ORDER BY mf."FILE_PATH"
    """
)

_AI_SCHEMA = get_settings().ai_schema

TAG_KNOWLEDGE_SQL = text(
    f"""
    SELECT
        d.tag_id,
        d.tag_name,
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
        d.related_tags
    FROM {_AI_SCHEMA}.tag_description d
    WHERE d.tag_id = :tag_id
    """
)

RELATED_TAGS_SQL = text(
    """
    SELECT
        ti."TAG_ID" AS tag_id,
        ti."TAG_NAME" AS tag_name,
        ti."DESCRIPTION" AS description,
        tie."DISPLAY_NAME" AS display_name,
        tie."TAG_TYPE_CODE" AS tag_type_code,
        ti."SIG_TYPE" AS sig_type,
        ti."ENG_UNIT" AS eng_unit
    FROM public."TAG_INFO" ti
    LEFT JOIN public."TAG_INFO_EXT" tie ON tie."TAG_ID" = ti."TAG_ID"
    WHERE ti."TAG_NAME" = ANY(CAST(:tag_names AS varchar[]))
    ORDER BY ti."TAG_NAME", ti."TAG_ID"
    """
)


class OperationalRepository:
    """태그·알람·화면은 FDAS DB, 설비·정비·LOTO는 FDAS_AMS DB에서 조회한다.

    두 DB가 물리적으로 분리되어 단일 SQL JOIN이 불가능하므로,
    FDAS에서 태그·알람을 조회한 뒤 얻은 TAG_ID/TAG_NAME으로 AMS를 조회하여
    애플리케이션 레벨에서 컨텍스트를 조립한다.
    """

    def __init__(
        self,
        fdas_db: Session,
        ams_db: Session,
        settings: Settings | None = None,
    ) -> None:
        self.fdas_db = fdas_db
        self.ams_db = ams_db
        self.settings = settings or get_settings()

    def list_recent_alarms(self) -> list[AlarmInfo]:
        rows = self.fdas_db.execute(
            RECENT_ALARMS_SQL,
            {"limit": self.settings.recent_alarm_limit},
        ).mappings()
        return [AlarmInfo.model_validate(row) for row in rows]

    def find_tag_candidates(self, tag_name: str) -> list[TagCandidate]:
        rows = self.fdas_db.execute(TAG_CANDIDATES_SQL, {"tag_name": tag_name}).mappings()
        return [TagCandidate.model_validate(row) for row in rows]

    def find_tags_in_text(self, question: str) -> list[TagCandidate]:
        """자유질문에서 태그 후보를 추출해 FDAS.TAG_INFO로 검증한 실태그 목록을 반환한다."""
        tokens = extract_tag_tokens(question)
        if not tokens:
            return []
        rows = self.fdas_db.execute(
            RESOLVE_TAGS_BY_NAMES_SQL,
            {"names": [token.upper() for token in tokens]},
        ).mappings()
        # tag_id 기준 중복 제거(여러 토큰이 같은 태그를 가리킬 수 있음).
        by_id: dict[int, TagCandidate] = {}
        for row in rows:
            candidate = TagCandidate.model_validate(row)
            by_id.setdefault(candidate.tag_id, candidate)
        return list(by_id.values())

    def find_tag_candidates_by_keywords(
        self,
        question: str,
        *,
        limit: int = 15,
    ) -> list[TagCandidate]:
        """질문에서 태그명이 안 잡힐 때, DESCRIPTION 키워드로 후보 태그를 찾는다."""
        keywords = extract_keywords(question)
        if not keywords:
            return []
        patterns = [f"%{keyword}%" for keyword in keywords]
        rows = self.fdas_db.execute(
            SEARCH_TAGS_BY_KEYWORDS_SQL,
            {"patterns": patterns, "limit": limit},
        ).mappings()
        return [TagCandidate.model_validate(row) for row in rows]

    def load_from_recent_alarm(
        self,
        tag_id: int,
        timestamp: datetime,
        question: str,
    ) -> AnalysisContext | None:
        row = self.fdas_db.execute(
            RECENT_ALARM_CONTEXT_SQL,
            {"tag_id": tag_id, "timestamp": timestamp},
        ).mappings().one_or_none()
        return self._build_context(row, question=question) if row else None

    def load_from_history(
        self,
        tag_id: int,
        timestamp: datetime,
        question: str,
    ) -> AnalysisContext | None:
        row = self.fdas_db.execute(
            HISTORY_ALARM_CONTEXT_SQL,
            {"tag_id": tag_id, "timestamp": timestamp},
        ).mappings().one_or_none()
        return self._build_context(row, question=question) if row else None

    def load_from_tag(self, tag_id: int, question: str) -> AnalysisContext | None:
        row = self.fdas_db.execute(
            TAG_CONTEXT_SQL, {"tag_id": tag_id}
        ).mappings().one_or_none()
        return self._build_context(row, question=question) if row else None

    def _build_context(self, row, *, question: str) -> AnalysisContext:
        tag = TagInfo.model_validate(row)
        alarm = _alarm_from_context_row(row)

        # 설비·정비·LOTO는 FDAS_AMS DB에서 TAG_ID/TAG_NAME 기준으로 조회한다.
        asset_rows = list(
            self.ams_db.execute(TAG_ASSETS_SQL, {"tag_id": tag.tag_id}).mappings()
        )
        asset = AssetInfo.model_validate(asset_rows[0]) if asset_rows else None
        asset_path: list[AssetPathItem] = []
        maintenance: list[MaintenanceInfo] = []
        loto: list[LotoInfo] = []
        if asset is not None:
            asset_path = [
                AssetPathItem.model_validate(item)
                for item in self.ams_db.execute(
                    ASSET_PATH_SQL,
                    {"asset_id": asset.id},
                ).mappings()
            ]
            maintenance = [
                MaintenanceInfo.model_validate(item)
                for item in self.ams_db.execute(
                    RECENT_MAINTENANCE_SQL,
                    {
                        "asset_id": asset.id,
                        "limit": self.settings.recent_maintenance_limit,
                    },
                ).mappings()
            ]
        loto = self._load_loto(asset_id=asset.id if asset else None, tag_name=tag.tag_name)

        history = [
            AlarmInfo.model_validate(item)
            for item in self.fdas_db.execute(
                RECENT_HISTORY_SQL,
                {
                    "tag_id": tag.tag_id,
                    "selected_timestamp": alarm.timestamp if alarm else None,
                    "limit": self.settings.recent_alarm_limit,
                },
            ).mappings()
        ]
        mimic = [
            MimicInfo.model_validate(item)
            for item in self.fdas_db.execute(
                MIMIC_SQL, {"tag_name": tag.tag_name}
            ).mappings()
        ]

        return AnalysisContext(
            question=question,
            alarm=alarm,
            tag=tag,
            asset=asset,
            asset_path=asset_path,
            recent_alarms=history,
            recent_maintenance=maintenance,
            mimic=mimic,
            loto=loto,
        )

    def _load_loto(self, *, asset_id: int | None, tag_name: str) -> list[LotoInfo]:
        """LOTO 2경로를 합집합으로 조회한다.

        ⓐ asset 경로 : 태그가 속한 설비(asset_id)에 발행된 loto
        ⓑ tag_code 경로: loto_tag.tag_code = TAG_NAME 으로 매핑된 loto
        두 결과를 loto.id 기준으로 dedupe, install_dt 내림차순 정렬한다.
        """
        by_id: dict[int, LotoInfo] = {}
        limit = self.settings.recent_maintenance_limit
        if asset_id is not None:
            for item in self.ams_db.execute(
                LOTO_BY_ASSET_SQL, {"asset_id": asset_id, "limit": limit}
            ).mappings():
                loto = LotoInfo.model_validate(item)
                by_id[loto.id] = loto
        for item in self.ams_db.execute(
            LOTO_BY_TAG_CODE_SQL, {"tag_name": tag_name, "limit": limit}
        ).mappings():
            loto = LotoInfo.model_validate(item)
            by_id.setdefault(loto.id, loto)

        return sorted(
            by_id.values(),
            key=lambda x: x.install_dt or _EPOCH,
            reverse=True,
        )


class DescriptionRepository:
    """태그 지식(tag_description)은 AI DB(djcp_alarm_ai)에서,
    관련 태그 해석(TAG_INFO)은 FDAS DB에서 조회한다."""

    def __init__(self, ai_db: Session, fdas_db: Session) -> None:
        self.ai_db = ai_db
        self.fdas_db = fdas_db

    def get_by_tag_id(self, tag_id: int) -> TagKnowledge | None:
        row = self.ai_db.execute(
            TAG_KNOWLEDGE_SQL, {"tag_id": tag_id}
        ).mappings().one_or_none()
        if row is None:
            return None
        payload = dict(row)
        payload["related_tags"] = payload.get("related_tags") or []
        return TagKnowledge.model_validate(payload)

    def resolve_related_tags(
        self,
        references: list[RelatedTagReference],
        *,
        limit: int,
    ) -> list[RelatedTag]:
        references = references[:limit]
        if not references:
            return []

        rows = self.fdas_db.execute(
            RELATED_TAGS_SQL,
            {"tag_names": [reference.tag_name for reference in references]},
        ).mappings()
        resolved_by_name = {
            str(row["tag_name"]): RelatedTag.model_validate(row)
            for row in rows
        }
        return [
            resolved_by_name.get(
                reference.tag_name,
                RelatedTag(
                    tag_name=reference.tag_name,
                    description=reference.description,
                ),
            )
            for reference in references
        ]


def _alarm_from_context_row(row) -> AlarmInfo | None:
    timestamp = row.get("alarm_timestamp")
    if timestamp is None:
        return None
    return AlarmInfo(
        timestamp=timestamp,
        tag_id=row["alarm_tag_id"],
        tag_name=row["alarm_tag_name"],
        description=row["alarm_description"],
        priority=row["alarm_priority"],
        value=row["alarm_value"],
        is_alm=row["alarm_is_alm"],
        message=row["alarm_message"],
        is_ack=row["alarm_is_ack"],
        ack_time=row["alarm_ack_time"],
    )
