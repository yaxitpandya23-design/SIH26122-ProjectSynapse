import axios from 'axios';
import { 
  Project, 
  ScheduleActivity, 
  FieldReport, 
  ProgressEvent, 
  SystemHealth, 
  MatchRunResponse,
  ValidationResult,
  DependencyViolation,
  DependencyGraph,
  ReviewInboxItem,
  ReviewCandidateDetail,
  ReviewAuditLog,
  ReviewMutationResponse,
  DashboardStats
} from '../types';

const api = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

export const apiService = {
  async getHealth(): Promise<SystemHealth> {
    const res = await axios.get<SystemHealth>('/health');
    return res.data;
  },

  async getProjects(): Promise<Project[]> {
    const res = await api.get<Project[]>('/schedules/projects');
    return res.data;
  },

  async createProject(project: {
    name: string;
    code: string;
    client_name?: string;
    target_start_date?: string;
    target_finish_date?: string;
  }): Promise<Project> {
    const res = await api.post<Project>('/schedules/projects', project);
    return res.data;
  },

  async uploadScheduleCsv(projectId: string, file: File, versionLabel = 'Baseline Revision 0') {
    const formData = new FormData();
    formData.append('project_id', projectId);
    formData.append('version_label', versionLabel);
    formData.append('file', file);

    const res = await api.post('/schedules/upload-csv', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return res.data;
  },

  async getProjectActivities(projectId: string, discipline?: string): Promise<ScheduleActivity[]> {
    const params = discipline && discipline !== 'ALL' ? { discipline } : {};
    const res = await api.get<ScheduleActivity[]>(`/schedules/project/${projectId}/activities`, { params });
    return res.data;
  },

  async submitRawReport(data: {
    project_id: string;
    raw_text: string;
    reporter_name?: string;
    report_date?: string;
  }): Promise<FieldReport> {
    const res = await api.post<FieldReport>('/field-reports/raw-text', data);
    return res.data;
  },

  async getFieldReports(projectId?: string): Promise<FieldReport[]> {
    const params = projectId ? { project_id: projectId } : {};
    const res = await api.get<FieldReport[]>('/field-reports', { params });
    return res.data;
  },

  async getProgressEvents(projectId?: string, discipline?: string): Promise<ProgressEvent[]> {
    const params: Record<string, string> = {};
    if (projectId) params.project_id = projectId;
    if (discipline && discipline !== 'ALL') params.discipline = discipline;
    const res = await api.get<ProgressEvent[]>('/field-reports/events/all', { params });
    return res.data;
  },

  async runEventMatching(eventId: string, topK = 5): Promise<MatchRunResponse> {
    const res = await api.post<MatchRunResponse>(`/matching/progress-events/${eventId}?top_k=${topK}`);
    return res.data;
  },

  async getEventCandidates(eventId: string): Promise<MatchRunResponse> {
    const res = await api.get<MatchRunResponse>(`/matching/progress-events/${eventId}/candidates`);
    return res.data;
  },

  async validateCandidate(candidateId: string): Promise<ValidationResult> {
    const res = await api.post<ValidationResult>(`/validation/candidates/${candidateId}`);
    return res.data;
  },

  async validateProgressEvent(progressEventId: string): Promise<ValidationResult[]> {
    const res = await api.post<ValidationResult[]>('/validation/run', { progress_event_id: progressEventId });
    return res.data;
  },

  async getCandidateValidation(candidateId: string): Promise<ValidationResult> {
    const res = await api.get<ValidationResult>(`/validation/candidates/${candidateId}`);
    return res.data;
  },

  async getProjectViolations(projectId?: string, severity?: string): Promise<DependencyViolation[]> {
    const params: Record<string, string> = {};
    if (projectId) params.project_id = projectId;
    if (severity) params.severity = severity;
    const res = await api.get<DependencyViolation[]>('/validation/violations', { params });
    return res.data;
  },

  async getProjectGraph(projectId: string): Promise<DependencyGraph> {
    const res = await api.get<DependencyGraph>(`/validation/projects/${projectId}/graph`);
    return res.data;
  },

  async getReviewInbox(
    projectId?: string,
    statusFilter?: string,
    severityFilter?: string
  ): Promise<ReviewInboxItem[]> {
    const params: Record<string, string> = {};
    if (projectId) params.project_id = projectId;
    if (statusFilter && statusFilter !== 'ALL') params.status_filter = statusFilter;
    if (severityFilter && severityFilter !== 'ALL') params.severity_filter = severityFilter;
    const res = await api.get<ReviewInboxItem[]>('/review/inbox', { params });
    return res.data;
  },

  async getCandidateDetail(candidateId: string): Promise<ReviewCandidateDetail> {
    const res = await api.get<ReviewCandidateDetail>(`/review/candidates/${candidateId}`);
    return res.data;
  },

  async approveCandidate(
    candidateId: string,
    reviewerUser?: string,
    remarks?: string
  ): Promise<ReviewMutationResponse> {
    const res = await api.post<ReviewMutationResponse>(`/review/candidates/${candidateId}/approve`, {
      reviewer_user: reviewerUser || 'Site Planning Engineer',
      remarks,
    });
    return res.data;
  },

  async overrideCandidate(
    candidateId: string,
    overrideReason: string,
    reviewerUser?: string,
    remarks?: string
  ): Promise<ReviewMutationResponse> {
    const res = await api.post<ReviewMutationResponse>(`/review/candidates/${candidateId}/override`, {
      override_reason: overrideReason,
      reviewer_user: reviewerUser || 'Project Director',
      remarks,
    });
    return res.data;
  },

  async rejectCandidate(
    candidateId: string,
    reason: string,
    reviewerUser?: string
  ): Promise<ReviewMutationResponse> {
    const res = await api.post<ReviewMutationResponse>(`/review/candidates/${candidateId}/reject`, {
      reason,
      reviewer_user: reviewerUser || 'Site Planning Engineer',
    });
    return res.data;
  },

  async reassignCandidate(
    candidateId: string,
    targetActivityId: string,
    reason?: string,
    reviewerUser?: string
  ): Promise<ReviewMutationResponse> {
    const res = await api.post<ReviewMutationResponse>(`/review/candidates/${candidateId}/reassign`, {
      target_activity_id: targetActivityId,
      reason,
      reviewer_user: reviewerUser || 'Site Planning Engineer',
    });
    return res.data;
  },

  async editCandidateEvent(
    candidateId: string,
    payload: {
      quantity_reported?: number;
      uom?: string;
      event_date?: string;
      status_claim?: string;
      work_description?: string;
      reason?: string;
    },
    reviewerUser?: string
  ): Promise<ReviewMutationResponse> {
    const res = await api.post<ReviewMutationResponse>(`/review/candidates/${candidateId}/edit`, {
      ...payload,
      reviewer_user: reviewerUser || 'Site Planning Engineer',
    });
    return res.data;
  },

  async getAuditLogs(
    projectId?: string,
    activityId?: string,
    action?: string
  ): Promise<ReviewAuditLog[]> {
    const params: Record<string, string> = {};
    if (projectId) params.project_id = projectId;
    if (activityId) params.activity_id = activityId;
    if (action && action !== 'ALL') params.action = action;
    const res = await api.get<ReviewAuditLog[]>('/review/audit', { params });
    return res.data;
  },

  async getDashboardStats(projectId?: string): Promise<DashboardStats> {
    const params = projectId ? { project_id: projectId } : {};
    const res = await api.get<DashboardStats>('/review/dashboard-stats', { params });
    return res.data;
  },

  // Phase 5 Demo Engine Methods
  async seedDemo(): Promise<any> {
    const res = await api.post('/demo/seed');
    return res.data;
  },

  async resetDemo(): Promise<any> {
    const res = await api.post('/demo/reset');
    return res.data;
  },

  async getDemoStatus(): Promise<any> {
    const res = await api.get('/demo/status');
    return res.data;
  },
};

export const demoApi = {
  seedDemo: apiService.seedDemo,
  resetDemo: apiService.resetDemo,
  getDemoStatus: apiService.getDemoStatus,
};

