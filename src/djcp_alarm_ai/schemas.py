from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AlarmAnalysisRequest(BaseModel):
    tag_id: int
    timestamp: datetime
    question: str = "이 알람이 왜 발생했어?"


class TagAnalysisRequest(BaseModel):
    tag_name: str
    question: str = "이 태그의 상태와 원인을 설명해줘."


class AlarmInfo(BaseModel):
    timestamp: datetime
    tag_id: int
    tag_name: str
    description: str | None = None
    priority: int
    value: float
    is_alm: int
    message: str
    is_ack: int | None = None
    ack_time: datetime | None = None


class TagInfo(BaseModel):
    tag_id: int
    tag_name: str
    description: str | None = None
    display_name: str | None = None
    tag_type_code: str | None = None
    sig_type: str | None = None
    system: str
    eng_unit: str | None = None
    l_engval: float | None = None
    h_engval: float | None = None
    alarm: str | None = None
    ll_alm_val: float | None = None
    lo_alm_val: float | None = None
    hi_alm_val: float | None = None
    hh_alm_val: float | None = None
    ll_alm_prio: int | None = None
    lo_alm_prio: int | None = None
    hi_alm_prio: int | None = None
    hh_alm_prio: int | None = None
    d_alm_prio1: int | None = None
    d_alm_prio2: int | None = None
    alm_cnd: int | None = None
    clsd_msg: str | None = None
    open_msg: str | None = None
    used: str | None = None


class RelatedTagReference(BaseModel):
    tag_name: str
    description: str | None = None


class RelatedTag(BaseModel):
    tag_id: int | None = None
    tag_name: str
    description: str | None = None
    display_name: str | None = None
    tag_type_code: str | None = None
    sig_type: str | None = None
    eng_unit: str | None = None


class AssetInfo(BaseModel):
    id: int
    parent_id: int | None = None
    code: str | None = None
    name: str | None = None
    asset_type: str | None = None
    status: str | None = None
    criticality: str | None = None
    system_name: str | None = None
    location: str | None = None
    description: str | None = None


class AssetPathItem(BaseModel):
    id: int
    parent_id: int | None = None
    code: str | None = None
    name: str | None = None
    asset_type: str | None = None
    depth: int


class MaintenanceInfo(BaseModel):
    id: int
    work_code: str
    asset_id: int | None = None
    work_name: str
    maint_type: str
    priority: str
    worker: str | None = None
    scheduled_at: datetime | None = None
    duration_minutes: int
    completed_at: datetime | None = None
    status: str
    cost: str | None = None
    inspection_result: str | None = None
    next_due_date: date | None = None
    confirmer: str | None = None
    work_description: str | None = None
    team_note: str | None = None


class TagKnowledge(BaseModel):
    tag_id: int
    tag_name: str
    description: str | None = None
    tag_nm: str | None = None
    tag_rmk: str | None = None
    tag_desc: str | None = None
    equipment_description: str | None = None
    tag_description: str | None = None
    value_change_meaning: str | None = None
    key_check_points: str | None = None
    action_guidance: str | None = None
    failure_guidance: str | None = None
    related_tags: list[RelatedTagReference] = Field(default_factory=list)
    sop_tag_name: str | None = None


class SopInfo(BaseModel):
    tag_id: int | None = None
    tag_name: str
    description: str | None = None
    system_name: str | None = None
    kind: str | None = None
    scenarios: list[str] = Field(default_factory=list)
    content: str
    embedding_model: str | None = None


class MimicInfo(BaseModel):
    file_path: str
    file_size: int
    last_write_ticks: int
    chg_date: datetime
    chg_id: str


class AnalysisContext(BaseModel):
    question: str
    alarm: AlarmInfo | None = None
    tag: TagInfo
    asset: AssetInfo | None = None
    asset_path: list[AssetPathItem] = Field(default_factory=list)
    recent_alarms: list[AlarmInfo] = Field(default_factory=list)
    recent_maintenance: list[MaintenanceInfo] = Field(default_factory=list)
    related_tags: list[RelatedTag] = Field(default_factory=list)
    tag_knowledge: TagKnowledge | None = None
    sop: SopInfo | None = None
    mimic: list[MimicInfo] = Field(default_factory=list)


class LikelyCause(BaseModel):
    cause: str
    basis: Literal["DATABASE", "TAG_DESCRIPTION", "INFERENCE"]


class AnalysisAnswer(BaseModel):
    summary: str
    likely_causes: list[LikelyCause] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AnalysisMetrics(BaseModel):
    llm_response_seconds: float | None = None
    analysis_total_seconds: float | None = None


class AlarmResponse(BaseModel):
    timestamp: datetime
    tag_id: int
    tag_name: str
    priority: int
    value: float
    is_alm: int
    message: str


class AlarmSetpoints(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ll: float | None = Field(default=None, serialization_alias="LL")
    lo: float | None = Field(default=None, serialization_alias="LO")
    hi: float | None = Field(default=None, serialization_alias="HI")
    hh: float | None = Field(default=None, serialization_alias="HH")


class TagResponse(BaseModel):
    tag_id: int
    tag_name: str
    display_name: str | None = None
    unit: str | None = None
    system: str
    alarm_setpoints: AlarmSetpoints


class AssetResponse(BaseModel):
    id: int
    name: str | None = None
    description: str | None = None


class RelatedTagResponse(BaseModel):
    tag_name: str
    description: str | None = None


class SopResponse(BaseModel):
    tag_name: str
    scenarios: list[str] = Field(default_factory=list)
    content: str


class MaintenanceResponse(BaseModel):
    work_name: str
    maint_type: str
    status: str
    completed_at: datetime | None = None
    inspection_result: str | None = None
    work_description: str | None = None


class MimicResponse(BaseModel):
    file_path: str
    file_size: int


class AnalysisResponse(BaseModel):
    answer: AnalysisAnswer
    alarm: AlarmResponse | None = None
    tag: TagResponse
    asset: AssetResponse | None = None
    related_tags: list[RelatedTagResponse] = Field(default_factory=list)
    sop: SopResponse | None = None
    maintenance: list[MaintenanceResponse] = Field(default_factory=list)
    mimic: list[MimicResponse] = Field(default_factory=list)
    metrics: AnalysisMetrics | None = None

    @classmethod
    def from_context(
        cls,
        context: AnalysisContext,
        answer: AnalysisAnswer,
        metrics: AnalysisMetrics | None = None,
    ) -> "AnalysisResponse":
        alarm = (
            AlarmResponse(
                timestamp=context.alarm.timestamp,
                tag_id=context.alarm.tag_id,
                tag_name=context.alarm.tag_name,
                priority=context.alarm.priority,
                value=context.alarm.value,
                is_alm=context.alarm.is_alm,
                message=context.alarm.message,
            )
            if context.alarm
            else None
        )
        tag = TagResponse(
            tag_id=context.tag.tag_id,
            tag_name=context.tag.tag_name,
            display_name=context.tag.display_name,
            unit=context.tag.eng_unit,
            system=context.tag.system,
            alarm_setpoints=AlarmSetpoints(
                ll=context.tag.ll_alm_val,
                lo=context.tag.lo_alm_val,
                hi=context.tag.hi_alm_val,
                hh=context.tag.hh_alm_val,
            ),
        )
        asset = (
            AssetResponse(
                id=context.asset.id,
                name=context.asset.name,
                description=context.asset.description,
            )
            if context.asset
            else None
        )
        sop = (
            SopResponse(
                tag_name=context.sop.tag_name,
                scenarios=context.sop.scenarios,
                content=context.sop.content,
            )
            if context.sop
            else None
        )
        return cls(
            answer=answer,
            alarm=alarm,
            tag=tag,
            asset=asset,
            related_tags=[
                RelatedTagResponse(
                    tag_name=related_tag.tag_name,
                    description=related_tag.description,
                )
                for related_tag in context.related_tags
            ],
            sop=sop,
            maintenance=[
                MaintenanceResponse(
                    work_name=item.work_name,
                    maint_type=item.maint_type,
                    status=item.status,
                    completed_at=item.completed_at,
                    inspection_result=item.inspection_result,
                    work_description=item.work_description,
                )
                for item in context.recent_maintenance
            ],
            mimic=[
                MimicResponse(
                    file_path=item.file_path,
                    file_size=item.file_size,
                )
                for item in context.mimic
            ],
            metrics=metrics,
        )


class TagCandidate(BaseModel):
    tag_id: int
    tag_name: str
    description: str | None = None
    system: str
    display_name: str | None = None
