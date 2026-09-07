import csv
import io
import re
from datetime import datetime, date
from typing import List, Dict, Any, Optional
from pydantic import BaseModel


class ParsedActivityItem(BaseModel):
    activity_code: str
    name: str
    discipline: str = "GENERAL"
    wbs_code: str = ""
    wbs_name: Optional[str] = None
    planned_start: Optional[date] = None
    planned_finish: Optional[date] = None
    planned_duration_days: int = 0
    planned_quantity: float = 0.0
    uom: str = "UNITS"
    is_critical: bool = False
    location_scope: Optional[str] = None
    predecessors_raw: List[str] = []


def parse_date(val: Optional[str]) -> Optional[date]:
    if not val or not val.strip():
        return None
    val = val.strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    return None


def parse_schedule_csv(csv_content: str) -> List[ParsedActivityItem]:
    """
    Deterministically parses tabular CSV schedule export into normalized activity items.
    Handles varying header casing and common construction industry field names.
    """
    reader = csv.DictReader(io.StringIO(csv_content))
    activities: List[ParsedActivityItem] = []

    for row in reader:
        # Normalize keys (lowercase and remove spaces/underscores)
        normalized_row: Dict[str, str] = {
            re.sub(r'[\s_]+', '', k.lower()): (v.strip() if v else "")
            for k, v in row.items() if k
        }

        # Helper getter for flexible field matching
        def get_field(*keys: str, default: str = "") -> str:
            for k in keys:
                clean_k = re.sub(r'[\s_]+', '', k.lower())
                if clean_k in normalized_row and normalized_row[clean_k]:
                    return normalized_row[clean_k]
            return default

        act_code = get_field("activitycode", "activityid", "taskcode", "taskid", "id", "code")
        name = get_field("activityname", "taskname", "name", "description", "activitydescription")

        if not act_code and not name:
            continue

        if not act_code:
            act_code = f"ACT-{len(activities) + 1:04d}"
        if not name:
            name = act_code

        discipline = get_field("discipline", "trade", "department", default="GENERAL").upper()
        wbs_code = get_field("wbscode", "wbs", default="")
        wbs_name = get_field("wbsname", "wbsdescription", default="")

        start_date = parse_date(get_field("plannedstart", "startdate", "start", "earlystart"))
        finish_date = parse_date(get_field("plannedfinish", "finishdate", "finish", "earlyfinish"))

        duration_raw = get_field("planneddurationdays", "durationdays", "duration", "plannedduration", default="0")
        try:
            duration = int(float(re.sub(r'[^\d.]', '', duration_raw) or 0))
        except ValueError:
            duration = 0

        # Calculate duration from dates if not provided
        if duration <= 0 and start_date and finish_date:
            duration = max(1, (finish_date - start_date).days)

        qty_raw = get_field("plannedquantity", "quantity", "plannedqty", "qty", default="0")
        try:
            quantity = float(re.sub(r'[^\d.]', '', qty_raw) or 0.0)
        except ValueError:
            quantity = 0.0

        uom = get_field("uom", "unit", "unitofmeasure", default="UNITS").upper()
        
        crit_raw = get_field("iscritical", "critical", "criticalpath", default="false").lower()
        is_critical = crit_raw in ("true", "yes", "1", "t", "y")

        location = get_field("locationscope", "location", "chainage", default="")

        # Predecessors parsing (e.g. "ACT-1010; ACT-1020" or "ACT-1010:FS:0")
        pred_raw = get_field("predecessors", "predecessor", "preds", default="")
        predecessors: List[str] = []
        if pred_raw:
            for p in re.split(r'[,;]+', pred_raw):
                p_clean = p.strip()
                if p_clean:
                    predecessors.append(p_clean)

        activities.append(
            ParsedActivityItem(
                activity_code=act_code,
                name=name,
                discipline=discipline,
                wbs_code=wbs_code,
                wbs_name=wbs_name or None,
                planned_start=start_date,
                planned_finish=finish_date,
                planned_duration_days=duration,
                planned_quantity=quantity,
                uom=uom,
                is_critical=is_critical,
                location_scope=location or None,
                predecessors_raw=predecessors,
            )
        )

    return activities
