from datetime import datetime, date
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class ProjectCreate(BaseModel):
    name: str = Field(..., json_schema_extra={"example": "Duliajan-Numaligarh Crude Oil Pipeline"})
    code: str = Field(..., json_schema_extra={"example": "DNPL-SEC-01"})
    client_name: str = Field(default="Oil India Limited", json_schema_extra={"example": "Oil India Limited"})
    target_start_date: Optional[date] = None
    target_finish_date: Optional[date] = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    code: str
    client_name: str
    target_start_date: Optional[date] = None
    target_finish_date: Optional[date] = None
    created_at: datetime


class ScheduleActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    activity_code: str
    name: str
    discipline: str
    wbs_code: str
    wbs_name: Optional[str] = None
    planned_start: Optional[date] = None
    planned_finish: Optional[date] = None
    planned_duration_days: int
    actual_start: Optional[date] = None
    actual_finish: Optional[date] = None
    planned_quantity: float
    actual_quantity: float
    uom: Optional[str] = None
    physical_percent_complete: float
    is_critical: bool
    total_float_days: int
    location_scope: Optional[str] = None
    actuals_version: int = 1


class ScheduleUploadResponse(BaseModel):
    project_id: str
    schedule_version_id: str
    activities_imported: int
    dependencies_imported: int
    message: str
