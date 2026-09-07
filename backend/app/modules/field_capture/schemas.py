from datetime import datetime, date
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class RawTextReportCreate(BaseModel):
    project_id: str = Field(..., description="ID of the target project")
    raw_text: str = Field(..., description="Unstructured DPR text notes from field engineer")
    reporter_name: str = Field(default="Site Execution Engineer", description="Author of report")
    report_date: Optional[date] = Field(default_factory=date.today, description="Date of progress report")


class ProgressEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    field_report_id: str
    work_description: str
    discipline: str
    location_chainage: Optional[str] = None
    quantity_reported: Optional[float] = None
    uom: Optional[str] = None
    status_claim: str
    event_date: Optional[date] = None
    raw_text_snippet: str
    created_at: datetime


class FieldReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    report_date: date
    reporter_name: str
    raw_source_text: str
    source_type: str
    created_at: datetime
    events: List[ProgressEventResponse] = []
