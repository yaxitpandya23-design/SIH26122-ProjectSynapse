export interface Project {
  id: string;
  name: string;
  code: string;
  client_name: string;
  target_start_date?: string;
  target_finish_date?: string;
  created_at: string;
}

export interface ScheduleActivity {
  id: string;
  activity_code: string;
  name: string;
  discipline: string;
  wbs_code: string;
  wbs_name?: string;
  planned_start?: string;
  planned_finish?: string;
  planned_duration_days: number;
  actual_start?: string;
  actual_finish?: string;
  planned_quantity: number;
  actual_quantity: number;
  uom?: string;
  physical_percent_complete: number;
  is_critical: boolean;
  total_float_days: number;
  location_scope?: string;
  actuals_version?: number;
}

export interface ProgressEvent {
  id: string;
  field_report_id: string;
  work_description: string;
  discipline: string;
  location_chainage?: string;
  quantity_reported?: number;
  uom?: string;
  status_claim: string;
  event_date?: string;
  raw_text_snippet: string;
  created_at: string;
}

export interface FieldReport {
  id: string;
  project_id: string;
  report_date: string;
  reporter_name: string;
  raw_source_text: string;
  source_type: string;
  created_at: string;
  events: ProgressEvent[];
}

export interface SystemHealth {
  status: string;
  app: string;
  environment: string;
  version: string;
  ai_provider: string;
}

export interface ScoreBreakdown {
  semantic: number;
  discipline: number;
  location: number;
  quantity: number;
  temporal: number;
  final: number;
}

export interface MatchCandidate {
  candidate_id?: string;
  activity_id: string;
  activity_code: string;
  activity_name: string;
  discipline: string;
  wbs_code?: string;
  wbs_name?: string;
  location_scope?: string;
  planned_quantity?: number;
  actual_quantity?: number;
  uom?: string;
  confidence_score: number;
  score_breakdown: ScoreBreakdown;
  ranking: number;
  matching_reasons: string[];
  mismatch_reasons: string[];
  decision_status: 'AUTO_MATCHED' | 'NEEDS_REVIEW' | 'UNMATCHED' | 'BLOCKED_BY_DEPENDENCY' | string;
  llm_reasoning?: string | null;
}

export interface MatchRunResponse {
  progress_event_id: string;
  top_decision: 'AUTO_MATCHED' | 'NEEDS_REVIEW' | 'UNMATCHED' | 'BLOCKED_BY_DEPENDENCY' | string;
  arbitration_applied: boolean;
  arbitration_reasoning?: string | null;
  candidates: MatchCandidate[];
}

export interface DependencyViolation {
  id: string;
  project_id?: string;
  progress_event_id: string;
  match_candidate_id?: string;
  activity_id?: string;
  activity_code?: string;
  predecessor_activity_id?: string;
  predecessor_activity_code?: string;
  successor_activity_id?: string;
  successor_activity_code?: string;
  violation_type: string;
  severity: 'HARD_VIOLATION' | 'SOFT_WARNING' | string;
  description: string;
  expected_condition?: string;
  observed_condition?: string;
  detected_at: string;
}

export interface ValidationResult {
  candidate_id: string;
  activity_id: string;
  activity_code: string;
  activity_name: string;
  confidence_score: number;
  semantic_decision: string;
  final_decision: 'AUTO_MATCHED' | 'NEEDS_REVIEW' | 'UNMATCHED' | 'BLOCKED_BY_DEPENDENCY' | string;
  has_hard_violations: boolean;
  has_soft_warnings: boolean;
  violations: DependencyViolation[];
  is_critical_path: boolean;
  total_float_days: number;
  summary_reason: string;
  validated_at: string;
}

export interface GraphNode {
  id: string;
  activity_code: string;
  name: string;
  discipline: string;
  duration_days: number;
  early_start?: string;
  early_finish?: string;
  late_start?: string;
  late_finish?: string;
  total_float_days: number;
  is_critical: boolean;
  status: string;
}

export interface GraphEdge {
  predecessor_id: string;
  successor_id: string;
  predecessor_code: string;
  successor_code: string;
  dependency_type: string;
  lag_days: number;
}

export interface DependencyGraph {
  project_id: string;
  schedule_version_id: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  has_cycles: boolean;
  cycles: string[][];
  topological_order: string[];
  critical_path_activities: string[];
  project_duration_days: number;
}

export interface ReviewInboxItem {
  candidate_id: string;
  progress_event_id: string;
  project_id?: string;
  report_date?: string;
  reporter_name?: string;
  raw_text_snippet?: string;
  work_description: string;
  discipline: string;
  location_chainage?: string;
  quantity_reported?: number;
  uom?: string;
  status_claim: string;
  activity_id: string;
  activity_code: string;
  activity_name: string;
  activity_discipline: string;
  planned_quantity: number;
  actual_quantity: number;
  confidence_score: number;
  status: string;
  has_hard_violations: boolean;
  has_soft_warnings: boolean;
  violations_count: number;
  is_critical: boolean;
  total_float_days: number;
  validation_checks: {
    predecessor: string;
    sequence: string;
    quantity: string;
    critical_path: string;
  };
  blocker_reasons: string[];
  can_approve: boolean;
  can_override: boolean;
  is_applied: boolean;
  validated_activity_version?: number;
}

export interface ReviewCandidateDetail {
  candidate_id: string;
  progress_event_id: string;
  project_id?: string;
  report_date?: string;
  reporter_name?: string;
  raw_text_snippet?: string;
  raw_source_text?: string;
  work_description: string;
  discipline: string;
  location_chainage?: string;
  quantity_reported?: number;
  uom?: string;
  status_claim: string;
  event_date?: string;
  activity_id: string;
  activity_code: string;
  activity_name: string;
  activity_discipline: string;
  planned_quantity: number;
  actual_quantity: number;
  activity_uom?: string;
  confidence_score: number;
  score_breakdown: Record<string, any>;
  status: string;
  has_hard_violations: boolean;
  has_soft_warnings: boolean;
  violations_count: number;
  is_critical: boolean;
  total_float_days: number;
  validation_checks: {
    predecessor: string;
    sequence: string;
    quantity: string;
    critical_path: string;
  };
  blocker_reasons: string[];
  can_approve: boolean;
  can_override: boolean;
  is_applied: boolean;
  is_stale: boolean;
  llm_reasoning?: string;
  violations: DependencyViolation[];
  previous_actuals: {
    actual_quantity: number;
    actual_start?: string;
    actual_finish?: string;
    physical_percent_complete: number;
  };
  validated_activity_version?: number;
}

export interface ReviewAuditLog {
  id: string;
  project_id?: string;
  match_candidate_id?: string;
  progress_event_id?: string;
  activity_id?: string;
  activity_code?: string;
  action: string;
  decision: string;
  reviewer_user: string;
  review_timestamp: string;
  remarks?: string;
  is_override: boolean;
  override_reason?: string;
  previous_values: Record<string, any>;
  new_values: Record<string, any>;
}

export interface ReviewMutationResponse {
  status: string;
  message: string;
  candidate_id: string;
  activity_code: string;
  action: string;
  audit_id?: string;
  previous_values?: Record<string, any>;
  new_values?: Record<string, any>;
}

export interface DashboardStats {
  total_reports: number;
  total_events: number;
  auto_matched: number;
  needs_review: number;
  blocked_by_dependency: number;
  applied: number;
  rejected: number;
  total_mutations: number;
  unresolved_violations: number;
  last_update?: {
    activity_code?: string;
    action?: string;
    actor?: string;
    timestamp?: string;
    is_override?: boolean;
  } | null;
}

export interface DemoScenarioInfo {
  scenario_id: string;
  title: string;
  reporter_name: string;
  report_date: string;
  raw_text: string;
  expected_code?: string | null;
  description: string;
}

export interface DemoStatus {
  is_seeded: boolean;
  project_id?: string;
  project_code?: string;
  project_name?: string;
  activities_count: number;
  dependencies_count: number;
  reports_count: number;
  events_count: number;
  candidates_count: number;
  scenarios: DemoScenarioInfo[];
}

export interface DemoSeedResponse {
  status: string;
  message: string;
  project_id: string;
  project_code: string;
  project_name: string;
  activities_count: number;
  dependencies_count: number;
  reports_count: number;
  events_count: number;
  candidates_count: number;
  scenarios_seeded: number;
}
