import hashlib
import re
from datetime import date
from typing import List, Optional

from app.ai.base import BaseLLMProvider, BaseEmbeddingProvider, ExtractedProgressEventDTO


class MockProvider(BaseLLMProvider, BaseEmbeddingProvider):
    """
    Deterministic Mock AI Provider for offline test execution, CI, and judge evaluation.
    Requires zero external network requests and operates with 100% reproducibility.
    """

    async def extract_events(
        self, raw_text: str, report_date: Optional[str] = None
    ) -> List[ExtractedProgressEventDTO]:
        events: List[ExtractedProgressEventDTO] = []
        parsed_date = date.fromisoformat(report_date) if report_date else date.today()

        # Split into distinct sentences or lines
        lines = [line.strip() for line in re.split(r'[\r\n]+', raw_text) if len(line.strip()) > 5]

        for line in lines:
            line_lower = line.lower()
            
            # 1. Determine discipline & standardized work description
            discipline = "GENERAL"
            work_desc = "General site execution"
            if any(k in line_lower for k in ["spool", "manifold", "actuator", "pump house", "valve station", "compressor", "skid", "turbine"]):
                discipline = "MECHANICAL"
                if "manifold" in line_lower and "actuator" in line_lower:
                    work_desc = "Valve station manifold piping and actuator mounting"
                elif "manifold" in line_lower:
                    work_desc = "Manifold piping fabrication and installation"
                elif "spool" in line_lower:
                    work_desc = "Pipe spool erection"
                elif "actuator" in line_lower:
                    work_desc = "Actuator mounting and calibration"
                elif "pump" in line_lower:
                    work_desc = "Pump house equipment installation"
                else:
                    work_desc = "Mechanical equipment installation"
            elif any(k in line_lower for k in ["survey", "peg marking", "trench", "excavat", "dig", "earthwork", "grading", "row clearing", "clearing", "civil", "concrete", "foundation", "bund wall", "raft"]):
                discipline = "CIVIL"
                if "survey" in line_lower or "peg" in line_lower:
                    work_desc = "Topographical survey and peg marking"
                elif "trench" in line_lower:
                    work_desc = "Trench excavation and grading"
                elif "clearing" in line_lower or "grading" in line_lower:
                    work_desc = "Right of Way (ROW) clearing and grading"
                elif "concrete" in line_lower or "foundation" in line_lower or "raft" in line_lower or "bund wall" in line_lower:
                    work_desc = "Civil foundation concrete casting"
                else:
                    work_desc = "Civil earthworks"
            elif any(k in line_lower for k in ["weld", "stringing", "hauling", "bending", "hydrotest", "piping", "joint", "ndt", "lowering", "tie-in"]):
                discipline = "PIPING"
                if "weld" in line_lower:
                    if "tie-in" in line_lower or "golden" in line_lower:
                        work_desc = "Mainline tie-in welding and golden joints"
                    else:
                        work_desc = "Pipeline mainline joint welding"
                elif "stringing" in line_lower or "hauling" in line_lower:
                    work_desc = "Pipe stringing along ROW"
                elif "bending" in line_lower:
                    work_desc = "Cold field pipe bending"
                elif "hydrotest" in line_lower or "testing" in line_lower:
                    work_desc = "Hydrostatic pressure testing"
                elif "lowering" in line_lower:
                    work_desc = "Pipe lowering and padding"
                elif "ndt" in line_lower or "radiography" in line_lower or "crawler" in line_lower:
                    work_desc = "Non-destructive testing (radiography/UT)"
                elif "crossing" in line_lower or "hdd" in line_lower:
                    work_desc = "HDD river crossing installation"
                else:
                    work_desc = "Piping fabrication and installation"
            elif any(k in line_lower for k in ["cable", "transformer", "switchgear", "solar", "anode", "groundbed", "cathodic"]):
                discipline = "ELECTRICAL"
                if "anode" in line_lower or "cathodic" in line_lower or "groundbed" in line_lower:
                    work_desc = "Cathodic protection deep well anode installation"
                elif "solar" in line_lower or "rtu" in line_lower:
                    work_desc = "SCADA RTU panel and solar power system installation"
                else:
                    work_desc = "Electrical cabling and termination"
            elif any(k in line_lower for k in ["instrument", "sensor", "scada", "plc", "calibration"]):
                discipline = "INSTRUMENTATION"
                work_desc = "Instrumentation and SCADA loop checking"

            # 2. Extract chainage or location corridor
            location = None
            loc_matches = [
                m.upper().strip()
                for m in re.findall(
                    r'(?:ch(?:ainage)?\s*[\d\.\+]+\s*(?:to|-)?\s*[\d\.\+]*|sv-?\d+|valve\s*station\s*[\w\-]*|well\s*pad\s*[\w\-]*|section\s*[\w\-]*|pump\s*house|burhi\s*dihing|river\s*crossing|crossing|terminal)',
                    line_lower,
                )
                if m.strip()
            ]
            if loc_matches:
                loc_matches_sorted = sorted(
                    loc_matches,
                    key=lambda x: 0 if ("SV" in x or "CH" in x) else 1,
                )
                seen = set()
                deduped = [x for x in loc_matches_sorted if not (x in seen or seen.add(x))]
                location = ", ".join(deduped)

            # 3. Extract quantity and UOM
            # Matches patterns like '450m', '450 m', '1.2 km', '25 joints', '100 cum'
            qty_match = re.search(r'(\d+(?:\.\d+)?)\s*(m|mtr|meter|km|joints?|cum|sqm|ton|mt|nos?)\b', line_lower)
            qty = None
            uom = None
            if qty_match:
                qty = float(qty_match.group(1))
                unit = qty_match.group(2).upper()
                if unit in ["M", "MTR", "METER"]:
                    uom = "M"
                elif unit == "KM":
                    uom = "KM"
                elif "JOINT" in unit:
                    uom = "JOINTS"
                else:
                    uom = unit
            else:
                # Standalone number fallback: ignore identifiers like "Line 24", "SV-01", "Unit 2", "Section 1", "Ch 15+000"
                line_without_tags = re.sub(r'\b(?:line|unit|section|sv|gate|well|pad|rev|ch(?:ainage)?)\s*[\d\.\+]+', '', line_lower)
                num_match = re.search(r'\b(\d+(?:\.\d+)?)\s*(?:units?|ea|nos?)?\b', line_without_tags)
                if num_match and float(num_match.group(1)) > 0:
                    if any(u in line_without_tags for u in ["unit", "nos", "ea"]):
                        qty = float(num_match.group(1))
                        uom = "UNITS"

            # 4. Status claim
            status = "IN_PROGRESS"
            if any(k in line_lower for k in ["completed", "done", "finished", "cleared", "tested"]):
                status = "MILESTONE_COMPLETED"
            elif any(k in line_lower for k in ["started", "commenced", "initiated"]):
                status = "STARTED"

            events.append(
                ExtractedProgressEventDTO(
                    work_description=work_desc,
                    discipline=discipline,
                    location_chainage=location,
                    quantity_reported=qty,
                    uom=uom,
                    status_claim=status,
                    event_date=parsed_date,
                    raw_text_snippet=line,
                )
            )

        # Fallback if no lines matched
        if not events and raw_text.strip():
            events.append(
                ExtractedProgressEventDTO(
                    work_description="General site construction activity",
                    discipline="GENERAL",
                    location_chainage=None,
                    quantity_reported=None,
                    uom=None,
                    status_claim="IN_PROGRESS",
                    event_date=parsed_date,
                    raw_text_snippet=raw_text.strip()[:200],
                )
            )

        return events

    async def arbitrate_candidates(
        self,
        event_dict: dict,
        candidate_1: dict,
        candidate_2: dict,
    ) -> "CandidateArbitrationDTO":
        from app.ai.base import CandidateArbitrationDTO

        ev_desc = event_dict.get("work_description", "").lower()
        ev_raw = event_dict.get("raw_text_snippet", "").lower()
        name1 = candidate_1.get("name", "").lower()
        name2 = candidate_2.get("name", "").lower()
        code1 = candidate_1.get("activity_code", "")
        code2 = candidate_2.get("activity_code", "")
        score1 = candidate_1.get("confidence_score", 0.0)
        score2 = candidate_2.get("confidence_score", 0.0)

        # Count keyword token overlaps
        tokens_event = set(re.findall(r'\b\w{3,}\b', f"{ev_desc} {ev_raw}"))
        overlap1 = len(tokens_event.intersection(set(re.findall(r'\b\w{3,}\b', name1))))
        overlap2 = len(tokens_event.intersection(set(re.findall(r'\b\w{3,}\b', name2))))

        if overlap1 > overlap2 or score1 >= score2:
            preferred = candidate_1
            preferred_code = code1
            alt_code = code2
            reason = (
                f"Candidate [{code1}] is preferred over [{code2}] because its scope and technical descriptors "
                f"align more directly with reported site operation '{event_dict.get('work_description')}', "
                f"though score difference ({abs(score1 - score2):.3f}) warrants review."
            )
        else:
            preferred = candidate_2
            preferred_code = code2
            alt_code = code1
            reason = (
                f"Candidate [{code2}] is preferred over [{code1}] due to closer contextual alignment with "
                f"reported field location/discipline in DPR notes, though score difference ({abs(score1 - score2):.3f}) "
                f"is narrow."
            )

        return CandidateArbitrationDTO(
            preferred_activity_id=preferred.get("activity_id", ""),
            preferred_activity_code=preferred_code,
            reasoning=reason,
            confidence_adjustment=0.01 if overlap1 != overlap2 else 0.0,
        )

    PIPELINE_CONCEPT_CLUSTERS = {
        "PIPING_SPOOL_MANIFOLD": [
            "spool", "manifold", "piping", "erection", "actuator", "flange", "valve", "skid", "fittings"
        ],
        "PIPELINE_WELDING": [
            "weld", "welding", "joint", "joints", "tie-in", "golden", "root", "hot", "pass", "butt-weld", "smaw", "welder"
        ],
        "CIVIL_EARTHWORKS": [
            "trench", "excavation", "excavator", "dig", "earthwork", "grading", "clearing", "row", "backfill", "soil"
        ],
        "CIVIL_STRUCTURES": [
            "concrete", "raft", "bund", "wall", "casting", "foundation", "reinforcement", "rebar", "survey", "peg"
        ],
        "SPECIAL_CROSSINGS": [
            "hdd", "horizontal", "directional", "drilling", "boring", "river", "crossing", "burhi", "dihing"
        ],
        "TESTING_COMMISSIONING": [
            "hydrotest", "pressure", "testing", "dewatering", "swabbing", "drying", "nitrogen", "purging", "linepack", "preservation"
        ],
        "QUALITY_NDT": [
            "ndt", "radiography", "crawler", "x-ray", "ultrasonic", "spark", "holiday", "coating"
        ],
        "ELECTRICAL_CP": [
            "anode", "groundbed", "cathodic", "cp", "deepwell", "transformer", "cable"
        ],
        "SCADA_AUTOMATION": [
            "scada", "rtu", "solar", "telemetry", "panel", "instrumentation", "plc"
        ],
        "FACILITIES_STATION": [
            "sv-01", "sectional", "terminal", "duliajan", "numaligarh", "pump", "house", "station"
        ],
    }

    async def get_embedding(self, text: str) -> List[float]:
        """
        Generate a deterministic, unit-normalized 768-dimensional embedding vector
        combining domain-aware pipeline engineering concept subspaces with
        cryptographic SHA-256 token hashing for lexical specificity.
        """
        dim = 768
        vector = [0.0] * dim
        tokens = re.findall(r'\b\w+\b', text.lower())
        if not tokens:
            tokens = ["empty"]

        # 1. Concept cluster subspace (dims 0..199)
        for cluster_idx, (cname, kws) in enumerate(self.PIPELINE_CONCEPT_CLUSTERS.items()):
            match_count = sum(1 for t in tokens if any(kw in t or t in kw for kw in kws))
            if match_count > 0:
                weight = min(2.5, 0.8 + 0.5 * match_count)
                start_dim = cluster_idx * 20
                for i in range(20):
                    vector[start_dim + i] += weight * ((i % 3) - 1.0)

        # 2. Token-specific hashing subspace (dims 200..767)
        for token in tokens:
            h = hashlib.sha256(token.encode("utf-8")).digest()
            for b_idx in range(16):
                pos = 200 + ((int.from_bytes(h[b_idx * 2 : b_idx * 2 + 2], "big")) % 568)
                weight = (h[b_idx] - 128) / 128.0
                vector[pos] += weight

        # L2 Normalize the vector
        magnitude = sum(x * x for x in vector) ** 0.5
        if magnitude > 1e-9:
            vector = [x / magnitude for x in vector]
        else:
            vector[0] = 1.0

        return vector
