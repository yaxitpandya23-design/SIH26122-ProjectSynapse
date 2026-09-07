import re
from datetime import date
from typing import Optional, List, Tuple, Dict, Any
from app.modules.semantic_matcher.schemas import ScoreBreakdown


WEIGHT_SEMANTIC = 0.40
WEIGHT_DISCIPLINE = 0.20
WEIGHT_LOCATION = 0.20
WEIGHT_QUANTITY = 0.10
WEIGHT_TEMPORAL = 0.10


def cosine_similarity(v1: Optional[List[float]], v2: Optional[List[float]]) -> float:
    """Compute cosine similarity between two float vectors, strictly bounded in [0.0, 1.0]."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    mag1 = sum(a * a for a in v1) ** 0.5
    mag2 = sum(b * b for b in v2) ** 0.5
    if mag1 < 1e-9 or mag2 < 1e-9:
        return 0.0
    cos = dot / (mag1 * mag2)
    # Clamp to [0.0, 1.0]
    return max(0.0, min(1.0, float(cos)))


def score_discipline(
    event_disc: Optional[str], act_disc: Optional[str]
) -> Tuple[float, List[str], List[str]]:
    """Score discipline / trade compatibility."""
    ed = (event_disc or "GENERAL").strip().upper()
    ad = (act_disc or "GENERAL").strip().upper()
    reasons: List[str] = []
    mismatches: List[str] = []

    if ed == ad:
        if ed == "GENERAL":
            reasons.append("Unspecified / general discipline category")
            return 0.50, reasons, mismatches
        reasons.append(f"Exact discipline match ({ad})")
        return 1.0, reasons, mismatches

    # Cross-compatible trades in pipeline engineering
    compatible_pairs = {
        frozenset(["PIPING", "MECHANICAL"]),
        frozenset(["CIVIL", "GENERAL"]),
        frozenset(["PIPING", "GENERAL"]),
        frozenset(["ELECTRICAL", "INSTRUMENTATION"]),
    }

    if frozenset([ed, ad]) in compatible_pairs:
        reasons.append(f"Compatible trade disciplines ({ed} ↔ {ad})")
        return 0.70, reasons, mismatches

    if ed == "GENERAL" or ad == "GENERAL":
        reasons.append("General trade compatibility")
        return 0.60, reasons, mismatches

    mismatches.append(f"Discipline conflict: field execution is '{ed}' but schedule is '{ad}'")
    return 0.05, reasons, mismatches


def parse_chainage_km(text: Optional[str]) -> Optional[float]:
    """Parse chainage string like 'Ch 04+200' or 'Ch 14.5' into float kilometers (e.g. 4.2)."""
    if not text:
        return None
    m = re.search(r'ch(?:ainage)?\s*(\d+)(?:\+(\d+))?', text.lower())
    if m:
        km = float(m.group(1))
        meters = float(m.group(2) or 0)
        return km + (meters / 1000.0)
    # Direct float km
    m2 = re.search(r'(\d+(?:\.\d+)?)\s*km\b', text.lower())
    if m2:
        return float(m2.group(1))
    return None


def parse_chainage_range_km(text: Optional[str]) -> Optional[Tuple[float, float]]:
    """Parse range like 'Ch 0+000 to Ch 30+000' or 'Ch 14+200 to 14+850'."""
    if not text:
        return None
    matches = list(re.finditer(r'ch(?:ainage)?\s*(\d+)(?:\+(\d+))?', text.lower()))
    if len(matches) >= 2:
        km1 = float(matches[0].group(1)) + float(matches[0].group(2) or 0) / 1000.0
        km2 = float(matches[1].group(1)) + float(matches[1].group(2) or 0) / 1000.0
        return (min(km1, km2), max(km1, km2))
    return None


def score_location(
    event_loc: Optional[str], act_scope: Optional[str]
) -> Tuple[float, List[str], List[str]]:
    """Score spatial and chainage corridor alignment."""
    reasons: List[str] = []
    mismatches: List[str] = []

    if not event_loc or not event_loc.strip():
        # Event has no specific location mentioned; return neutral score
        return 0.75, reasons, mismatches

    if not act_scope or not act_scope.strip():
        # Activity is not spatially localized
        return 0.75, reasons, mismatches

    el_clean = event_loc.upper()
    as_clean = act_scope.upper()

    # 1. Direct facility / node name match (e.g. 'SV-01', 'VALVE STATION', 'BURHI DIHING', 'PUMP HOUSE')
    facility_keywords = ["SV-01", "VALVE STATION", "BURHI DIHING", "PUMP HOUSE", "TERMINAL", "RIVER CROSSING", "CROSSING"]
    for kw in facility_keywords:
        if kw in el_clean and kw in as_clean:
            reasons.append(f"Physical site facility matches planned location ('{kw}')")
            return 0.95, reasons, mismatches

    # 2. Linear Chainage comparison
    act_range = parse_chainage_range_km(act_scope)
    ev_pt = parse_chainage_km(event_loc)
    ev_range = parse_chainage_range_km(event_loc)

    if act_range:
        start_km, end_km = act_range
        if ev_pt is not None:
            if start_km - 0.5 <= ev_pt <= end_km + 0.5:
                reasons.append(f"Reported chainage ({event_loc}) lies within planned corridor ({act_scope})")
                return 1.0, reasons, mismatches
            else:
                mismatches.append(f"Reported chainage ({event_loc}) is outside planned corridor ({act_scope})")
                return 0.15, reasons, mismatches

        if ev_range is not None:
            e_s, e_e = ev_range
            overlap = max(0.0, min(end_km, e_e) - max(start_km, e_s))
            if overlap > 0:
                reasons.append(f"Reported chainage span ({event_loc}) overlaps planned corridor ({act_scope})")
                return 0.95, reasons, mismatches
            else:
                mismatches.append(f"Reported chainage span ({event_loc}) is disjoint from planned corridor ({act_scope})")
                return 0.15, reasons, mismatches

    # Keyword overlap fallback
    tokens_e = set(re.findall(r'\b\w{3,}\b', el_clean))
    tokens_a = set(re.findall(r'\b\w{3,}\b', as_clean))
    common = tokens_e.intersection(tokens_a)
    if common:
        reasons.append(f"Location keywords overlap: {', '.join(common)}")
        return 0.85, reasons, mismatches

    return 0.50, reasons, mismatches


def score_quantity_uom(
    event_qty: Optional[float],
    event_uom: Optional[str],
    planned_qty: Optional[float],
    planned_uom: Optional[str],
) -> Tuple[float, List[str], List[str]]:
    """Score Unit of Measure and numerical quantity compatibility."""
    reasons: List[str] = []
    mismatches: List[str] = []

    eu = (event_uom or "").strip().upper()
    pu = (planned_uom or "").strip().upper()
    eq = event_qty
    pq = planned_qty or 0.0

    if not eu:
        # Event has no UOM
        return 0.70, reasons, mismatches

    if not pu or pu == "UNITS":
        reasons.append(f"Activity has generic units ({pu or 'UNITS'})")
        return 0.75, reasons, mismatches

    # Exact UOM match
    if eu == pu:
        if eq is not None and pq > 0:
            if eq <= pq * 1.1:
                reasons.append(f"Compatible UOM ({eu}) and reported progress ({eq}) within planned scope ({pq})")
                return 1.0, reasons, mismatches
            elif eq <= pq * 1.5:
                mismatches.append(f"Reported quantity ({eq} {eu}) exceeds planned batch ({pq} {pu}) by >10%")
                return 0.70, reasons, mismatches
            else:
                mismatches.append(f"Reported quantity ({eq} {eu}) significantly exceeds planned total ({pq} {pu})")
                return 0.40, reasons, mismatches
        reasons.append(f"Matching unit of measure ({eu})")
        return 0.95, reasons, mismatches

    # Convertible distance units
    if (eu == "KM" and pu == "M") or (eu == "M" and pu == "KM"):
        reasons.append(f"Convertible distance units ({eu} ↔ {pu})")
        return 0.85, reasons, mismatches

    # Incompatible units
    mismatches.append(f"Incompatible unit of measure: field is '{eu}' but schedule is '{pu}'")
    return 0.10, reasons, mismatches


def score_temporal(
    event_date: Optional[date],
    planned_start: Optional[date],
    planned_finish: Optional[date],
) -> Tuple[float, List[str], List[str]]:
    """Score execution date feasibility against planned window."""
    reasons: List[str] = []
    mismatches: List[str] = []

    if not event_date or not planned_start:
        return 0.75, reasons, mismatches

    finish = planned_finish or planned_start

    # Within window (with standard construction grace margins: -7 days to +21 days)
    days_from_start = (event_date - planned_start).days
    days_from_finish = (event_date - finish).days

    if -7 <= days_from_start and days_from_finish <= 21:
        reasons.append(f"Execution date ({event_date}) aligns with planned schedule window ({planned_start} to {finish})")
        return 1.0, reasons, mismatches

    if -21 <= days_from_start and days_from_finish <= 45:
        reasons.append(f"Execution date ({event_date}) is within moderate schedule tolerance of planned window")
        return 0.75, reasons, mismatches

    if days_from_finish > 60:
        mismatches.append(f"Execution date ({event_date}) is {days_from_finish} days past planned completion ({finish})")
        return 0.35, reasons, mismatches

    if days_from_start < -90:
        mismatches.append(f"Execution date ({event_date}) is {abs(days_from_start)} days ahead of planned start ({planned_start})")
        return 0.35, reasons, mismatches

    if days_from_start < -21:
        reasons.append(f"Advance execution window: reported on {event_date}, planned start is {planned_start}")
        return 0.70, reasons, mismatches

    return 0.60, reasons, mismatches


def stem_token(w: str) -> str:
    """Standard English suffix stemmer for pipeline construction vocabulary."""
    w = w.lower()
    for suffix in ["ing", "tion", "ment", "ed", "er", "es", "s"]:
        if w.endswith(suffix):
            w = w[:-len(suffix)]
            break
    if w.endswith("e"):
        w = w[:-1]
    return w


def calculate_confidence_score(
    event_embedding: Optional[List[float]],
    activity_embedding: Optional[List[float]],
    event_discipline: Optional[str],
    activity_discipline: Optional[str],
    event_location: Optional[str],
    activity_location: Optional[str],
    event_qty: Optional[float],
    event_uom: Optional[str],
    planned_qty: Optional[float],
    planned_uom: Optional[str],
    event_date: Optional[date],
    planned_start: Optional[date],
    planned_finish: Optional[date],
    event_text: str = "",
    activity_text: str = "",
) -> Tuple[ScoreBreakdown, List[str], List[str], str]:
    """
    Compute multi-factor confidence score with complete mathematical explainability.
    
    Formula:
    Score = 0.40 * Semantic + 0.20 * Discipline + 0.20 * Location + 0.10 * Quantity + 0.10 * Temporal
    
    Returns:
    (ScoreBreakdown, matching_reasons, mismatch_reasons, decision_status)
    """
    # 1. Semantic Similarity
    raw_cos = cosine_similarity(event_embedding, activity_embedding)

    # Domain lexical overlap with stopword filtering and morphological stemming
    stopwords = {
        "and", "for", "near", "completed", "today", "the", "with", "from",
        "that", "this", "all", "our", "were", "been", "have", "has", "had",
        "line", "at", "to", "in", "of", "on", "by", "is", "a", "an"
    }
    tokens_e = {stem_token(w) for w in re.findall(r'\b\w{3,}\b', event_text.lower()) if w not in stopwords}
    tokens_a = {stem_token(w) for w in re.findall(r'\b\w{3,}\b', activity_text.lower()) if w not in stopwords}
    lexical_overlap = len(tokens_e.intersection(tokens_a)) / max(1, len(tokens_e))

    # Calibrate raw cosine similarity
    if lexical_overlap == 0.0 and raw_cos < 0.40:
        # Zero lexical overlap and weak cosine (unrelated site text)
        s_sem = raw_cos * 0.25
    elif raw_cos >= 0.70:
        s_sem = 0.85 + min(0.15, (raw_cos - 0.70) * 1.5)
    elif raw_cos >= 0.50:
        s_sem = 0.60 + (raw_cos - 0.50) * 1.25
    elif raw_cos >= 0.35:
        s_sem = 0.40 + (raw_cos - 0.35) * 1.33
    else:
        s_sem = raw_cos * 0.80

    # Blend calibrated dense cosine similarity with lexical domain overlap
    s_sem = 0.70 * s_sem + 0.30 * lexical_overlap
    s_sem = max(0.0, min(1.0, float(s_sem)))

    all_reasons: List[str] = []
    all_mismatches: List[str] = []

    if s_sem >= 0.70:
        all_reasons.append(f"High semantic textual alignment ({int(s_sem * 100)}%) with activity description")
    elif s_sem < 0.35:
        all_mismatches.append(f"Low semantic description similarity ({int(s_sem * 100)}%)")

    # 2. Discipline Compatibility
    s_disc, disc_reasons, disc_mismatches = score_discipline(event_discipline, activity_discipline)
    all_reasons.extend(disc_reasons)
    all_mismatches.extend(disc_mismatches)

    # 3. Location / Chainage Alignment
    s_loc, loc_reasons, loc_mismatches = score_location(event_location, activity_location)
    all_reasons.extend(loc_reasons)
    all_mismatches.extend(loc_mismatches)

    # 4. Quantity & UOM
    s_qty, qty_reasons, qty_mismatches = score_quantity_uom(event_qty, event_uom, planned_qty, planned_uom)
    all_reasons.extend(qty_reasons)
    all_mismatches.extend(qty_mismatches)

    # 5. Temporal Alignment
    s_time, time_reasons, time_mismatches = score_temporal(event_date, planned_start, planned_finish)
    all_reasons.extend(time_reasons)
    all_mismatches.extend(time_mismatches)

    # Weighted Composite Score
    final_score = (
        WEIGHT_SEMANTIC * s_sem
        + WEIGHT_DISCIPLINE * s_disc
        + WEIGHT_LOCATION * s_loc
        + WEIGHT_QUANTITY * s_qty
        + WEIGHT_TEMPORAL * s_time
    )

    # Domain Gating & Semantic Primacy Rules:
    # 1. Zero/Low Semantic Floor:
    # If semantic similarity is low (< 0.30) or lexical overlap is zero with weak cosine (< 0.40),
    # the activity description has no genuine correlation with the field execution.
    # We strictly cap the final score to 0.48, ensuring an UNMATCHED classification.
    if s_sem < 0.30 or (lexical_overlap == 0.0 and raw_cos < 0.40):
        final_score = min(final_score, 0.48)
        if not any("Low semantic" in m for m in all_mismatches):
            all_mismatches.append(f"Low semantic description similarity ({int(s_sem * 100)}%)")

    # 2. Semantic Primacy Rule (Anti-False-Auto-Match):
    # An activity cannot be AUTO_MATCHED (>= 0.85) based purely on high location, discipline, or temporal scores
    # if the scope description match is only partial or ambiguous (s_sem < 0.78).
    # Cap final score to 0.78 (NEEDS_REVIEW) and document the scope disparity reason.
    elif s_sem < 0.78:
        if final_score > 0.78:
            final_score = 0.78
            all_mismatches.append(
                f"Semantic alignment ({int(s_sem * 100)}%) reflects partial scope or component activity; "
                f"flagged for human review to prevent false milestone auto-completion"
            )

    final_score = round(max(0.0, min(1.0, final_score)), 4)

    breakdown = ScoreBreakdown(
        semantic=round(s_sem, 4),
        discipline=round(s_disc, 4),
        location=round(s_loc, 4),
        quantity=round(s_qty, 4),
        temporal=round(s_time, 4),
        final=final_score,
    )

    # Decision Thresholds
    if final_score >= 0.85:
        decision_status = "AUTO_MATCHED"
    elif final_score >= 0.50:
        decision_status = "NEEDS_REVIEW"
    else:
        decision_status = "UNMATCHED"

    return breakdown, all_reasons, all_mismatches, decision_status
