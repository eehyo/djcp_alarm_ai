from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class QuestionRequest(BaseModel):
    question: str = "이 알람이 왜 발생했어?"


class TagAnalysisRequest(BaseModel):
    tag_name: str
    question: str = "이 태그의 상태와 원인을 설명해줘."
    asset_id: int | None = None


class AlarmInfo(BaseModel):
    id: int
    tag_id: int
    start_time: datetime
    end_time: datetime | None = None
    value: Decimal
    setpoint: Decimal
    severity: str
    state: str
    ack_by: str | None = None


class RecentAlarm(AlarmInfo):
    pass


class TagInfo(BaseModel):
    id: int
    asset_id: int
    tag_name: str
    description: str | None = None
    unit: str = ""
    alarm_high: Decimal | None = None
    alarm_low: Decimal | None = None
    current_value: Decimal | None = None
    last_updated_at: datetime | None = None


class RelatedTag(BaseModel):
    id: int
    tag_name: str
    description: str | None = None
    unit: str = ""
    current_value: Decimal | None = None
    last_updated_at: datetime | None = None


class AssetInfo(BaseModel):
    id: int
    parent_id: int | None = None
    code: str
    name: str
    asset_type: str = ""
    system_name: str = ""
    location: str = ""
    criticality: str = "Medium"
    description: str | None = None


class AssetPathItem(BaseModel):
    id: int
    parent_id: int | None = None
    code: str
    name: str
    asset_type: str = ""
    depth: int


class MaintenanceInfo(BaseModel):
    id: int
    asset_id: int
    work_name: str
    maint_type: str
    priority: str
    plan_start_dt: datetime | None = None
    plan_end_dt: datetime | None = None
    actual_end_dt: datetime | None = None
    owner: str = ""
    owner_dept: str = ""
    status: str
    inspection_result: str | None = None
    notes: str | None = None


class TagKnowledge(BaseModel):
    tag_id: int
    tag_name_snapshot: str
    description: str = ""
    tag_nm: str = ""
    tag_rmk: str = ""
    tag_desc: str = ""
    equipment_description: str = ""
    tag_description: str = ""
    value_change_meaning: str = ""
    key_check_points: str = ""
    action_guidance: str = ""
    failure_guidance: str = ""
    is_verified: bool = False


class AnalysisContext(BaseModel):
    question: str
    alarm: AlarmInfo | None = None
    tag: TagInfo
    asset: AssetInfo
    asset_path: list[AssetPathItem] = Field(default_factory=list)
    recent_alarms: list[RecentAlarm] = Field(default_factory=list)
    recent_maintenance: list[MaintenanceInfo] = Field(default_factory=list)
    related_tags: list[RelatedTag] = Field(default_factory=list)
    tag_knowledge: TagKnowledge | None = None


class AnalysisAnswer(BaseModel):
    summary: str
    likely_causes: list[str] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AnalysisResponse(BaseModel):
    context: AnalysisContext
    answer: AnalysisAnswer


class TagCandidate(BaseModel):
    tag_id: int
    tag_name: str
    asset_id: int
    asset_name: str
    asset_code: str
