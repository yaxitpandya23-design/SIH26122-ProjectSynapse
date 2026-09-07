import React, { useState, useEffect } from 'react';
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ShieldAlert,
  ShieldCheck,
  RefreshCw,
  Eye,
  Edit3,
  CornerUpRight,
  Ban,
  FileCheck,
  History,
  Sparkles
} from 'lucide-react';
import { apiService } from '../api/client';
import {
  ReviewInboxItem,
  ReviewCandidateDetail,
  ReviewAuditLog,
  DashboardStats,
  ScheduleActivity
} from '../types';

interface ReviewInboxTabProps {
  projectId: string;
  activities: ScheduleActivity[];
  onScheduleUpdated: () => void;
}

export const ReviewInboxTab: React.FC<ReviewInboxTabProps> = ({
  projectId,
  activities,
  onScheduleUpdated,
}) => {
  // Inbox state
  const [inboxItems, setInboxItems] = useState<ReviewInboxItem[]>([]);
  const [loadingInbox, setLoadingInbox] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [severityFilter, setSeverityFilter] = useState<string>('ALL');

  // Stats & Audit state
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [auditLogs, setAuditLogs] = useState<ReviewAuditLog[]>([]);
  const [loadingAudits, setLoadingAudits] = useState(false);
  const [auditActionFilter, setAuditActionFilter] = useState<string>('ALL');

  // Candidate 360 Detail Modal
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);
  const [candidateDetail, setCandidateDetail] = useState<ReviewCandidateDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // Modals state
  const [overrideTarget, setOverrideTarget] = useState<ReviewInboxItem | null>(null);
  const [overrideReason, setOverrideReason] = useState('');
  const [overrideRemarks, setOverrideRemarks] = useState('');

  const [rejectTarget, setRejectTarget] = useState<ReviewInboxItem | null>(null);
  const [rejectReason, setRejectReason] = useState('');

  const [reassignTarget, setReassignTarget] = useState<ReviewInboxItem | null>(null);
  const [reassignActId, setReassignActId] = useState('');
  const [reassignReason, setReassignReason] = useState('');

  const [editTarget, setEditTarget] = useState<ReviewInboxItem | null>(null);
  const [editQty, setEditQty] = useState('');
  const [editUom, setEditUom] = useState('');
  const [editStatusClaim, setEditStatusClaim] = useState('');
  const [editReason, setEditReason] = useState('');

  const [actionLoading, setActionLoading] = useState(false);
  const [feedbackMsg, setFeedbackMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Demo loading
  const [demoRunning, setDemoRunning] = useState<string | null>(null);

  useEffect(() => {
    if (projectId) {
      loadData();
    }
  }, [projectId, statusFilter, severityFilter, auditActionFilter]);

  const loadData = async () => {
    setLoadingInbox(true);
    setLoadingAudits(true);
    try {
      const [items, statsData, audits] = await Promise.all([
        apiService.getReviewInbox(projectId, statusFilter, severityFilter),
        apiService.getDashboardStats(projectId),
        apiService.getAuditLogs(projectId, undefined, auditActionFilter),
      ]);
      setInboxItems(items);
      setStats(statsData);
      setAuditLogs(audits);
    } catch (err: any) {
      console.error('Error loading review inbox data:', err);
      showFeedback('error', err.response?.data?.detail || 'Failed to load review data.');
    } finally {
      setLoadingInbox(false);
      setLoadingAudits(false);
    }
  };

  const showFeedback = (type: 'success' | 'error', text: string) => {
    setFeedbackMsg({ type, text });
    setTimeout(() => setFeedbackMsg(null), 6000);
  };

  const handleOpenDetail = async (candidateId: string) => {
    setSelectedCandidateId(candidateId);
    setLoadingDetail(true);
    try {
      const detail = await apiService.getCandidateDetail(candidateId);
      setCandidateDetail(detail);
    } catch (err: any) {
      showFeedback('error', err.response?.data?.detail || 'Failed to load candidate detail.');
    } finally {
      setLoadingDetail(false);
    }
  };

  // 1. APPROVE & APPLY
  const handleApprove = async (item: ReviewInboxItem) => {
    if (!item.can_approve) return;
    setActionLoading(true);
    try {
      const res = await apiService.approveCandidate(
        item.candidate_id,
        'Site Planning Engineer',
        'Standard approval verified against daily site sheets.'
      );
      showFeedback('success', `Approved and applied progress to [${res.activity_code}]! Status: ${res.status}`);
      await loadData();
      onScheduleUpdated();
    } catch (err: any) {
      showFeedback('error', err.response?.data?.detail || 'Approval failed.');
    } finally {
      setActionLoading(false);
    }
  };

  // 2. OVERRIDE & APPLY
  const handleOverrideSubmit = async () => {
    if (!overrideTarget) return;
    if (overrideReason.trim().length < 5) {
      showFeedback('error', 'Override justification must be at least 5 characters.');
      return;
    }
    setActionLoading(true);
    try {
      const res = await apiService.overrideCandidate(
        overrideTarget.candidate_id,
        overrideReason.trim(),
        'Project Director',
        overrideRemarks.trim() || undefined
      );
      showFeedback('success', `Override successful! Applied progress to [${res.activity_code}] with audit justification.`);
      setOverrideTarget(null);
      setOverrideReason('');
      setOverrideRemarks('');
      await loadData();
      onScheduleUpdated();
    } catch (err: any) {
      showFeedback('error', err.response?.data?.detail || 'Override failed.');
    } finally {
      setActionLoading(false);
    }
  };

  // 3. REJECT
  const handleRejectSubmit = async () => {
    if (!rejectTarget) return;
    if (rejectReason.trim().length < 3) {
      showFeedback('error', 'Rejection reason must be at least 3 characters.');
      return;
    }
    setActionLoading(true);
    try {
      await apiService.rejectCandidate(
        rejectTarget.candidate_id,
        rejectReason.trim(),
        'Site Planning Engineer'
      );
      showFeedback('success', `Candidate rejected. Zero schedule actuals modified.`);
      setRejectTarget(null);
      setRejectReason('');
      await loadData();
    } catch (err: any) {
      showFeedback('error', err.response?.data?.detail || 'Rejection failed.');
    } finally {
      setActionLoading(false);
    }
  };

  // 4. REASSIGN
  const handleReassignSubmit = async () => {
    if (!reassignTarget || !reassignActId) return;
    setActionLoading(true);
    try {
      const res = await apiService.reassignCandidate(
        reassignTarget.candidate_id,
        reassignActId,
        reassignReason.trim() || undefined,
        'Site Planning Engineer'
      );
      showFeedback('success', `Reassigned to [${res.activity_code}]! Triggered fresh deterministic validation.`);
      setReassignTarget(null);
      setReassignActId('');
      setReassignReason('');
      await loadData();
    } catch (err: any) {
      showFeedback('error', err.response?.data?.detail || 'Reassignment failed.');
    } finally {
      setActionLoading(false);
    }
  };

  // 5. EDIT PROGRESS EVENT
  const handleEditSubmit = async () => {
    if (!editTarget) return;
    setActionLoading(true);
    try {
      const payload: any = {
        reason: editReason.trim() || 'Engineer edited event progress parameters.',
      };
      if (editQty) payload.quantity_reported = parseFloat(editQty);
      if (editUom) payload.uom = editUom;
      if (editStatusClaim) payload.status_claim = editStatusClaim;

      const res = await apiService.editCandidateEvent(
        editTarget.candidate_id,
        payload,
        'Site Planning Engineer'
      );
      showFeedback('success', `Progress event updated! Re-validated against [${res.activity_code}].`);
      setEditTarget(null);
      setEditQty('');
      setEditUom('');
      setEditStatusClaim('');
      setEditReason('');
      await loadData();
    } catch (err: any) {
      showFeedback('error', err.response?.data?.detail || 'Edit failed.');
    } finally {
      setActionLoading(false);
    }
  };

  // QUICK DEMO LAUNCHERS
  const runDemoScenario = async (scenario: 'clean' | 'blocked' | 'unmatched' | 'ambiguous') => {
    if (!projectId) return;
    setDemoRunning(scenario);
    try {
      let text = '';
      let repName = 'Er. R. Baruah (Site Lead)';
      let repDate = '2026-10-25';

      if (scenario === 'clean') {
        text = 'Completed topographical survey and peg marking for 5 km along section 10+000 to 15+000.';
      } else if (scenario === 'blocked') {
        text = 'Valve station 01 manifold piping and actuator mounting completed today at SV-01.';
      } else if (scenario === 'unmatched') {
        text = 'Security gate painting and boundary fence whitewashing completed.';
      } else {
        text = 'Pipeline welding completed near the river crossing section.';
      }

      // 1. Ingest DPR
      const report = await apiService.submitRawReport({
        project_id: projectId,
        raw_text: text,
        reporter_name: repName,
        report_date: repDate,
      });

      if (report.events && report.events.length > 0) {
        const eventId = report.events[0].id;
        // 2. Match
        const matchRes = await apiService.runEventMatching(eventId, 2);
        if (matchRes.candidates && matchRes.candidates.length > 0) {
          const candId = matchRes.candidates[0].candidate_id;
          if (candId) {
            // 3. Validate
            await apiService.validateCandidate(candId);
          }
        }
      }

      showFeedback('success', `Demo Scenario [${scenario.toUpperCase()}] ingested, matched, and validated!`);
      await loadData();
    } catch (err: any) {
      showFeedback('error', err.response?.data?.detail || `Demo ${scenario} failed.`);
    } finally {
      setDemoRunning(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Toast Notification */}
      {feedbackMsg && (
        <div
          className={`fixed bottom-6 right-6 z-50 px-4 py-3 rounded-lg shadow-lg border flex items-center space-x-2 text-sm font-medium transition-all ${
            feedbackMsg.type === 'success'
              ? 'bg-emerald-950/90 border-emerald-500/80 text-emerald-200'
              : 'bg-rose-950/90 border-rose-500/80 text-rose-200'
          }`}
        >
          {feedbackMsg.type === 'success' ? (
            <CheckCircle2 className="w-5 h-5 text-emerald-400" />
          ) : (
            <AlertTriangle className="w-5 h-5 text-rose-400" />
          )}
          <span>{feedbackMsg.text}</span>
        </div>
      )}

      {/* Top Banner & Quick Scenarios */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center space-x-2">
              <ShieldCheck className="w-5 h-5 text-emerald-400" />
              <h2 className="text-lg font-bold text-white">Human-in-the-Loop Review & Approval Inbox</h2>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Deterministic gatekeeper layer. Schedule actuals are updated <span className="text-amber-300 font-semibold">only upon explicit human authorization</span>.
              Baseline planned parameters remain strictly immutable.
            </p>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={loadData}
              disabled={loadingInbox}
              className="flex items-center space-x-1.5 px-3 py-2 rounded-lg bg-slate-800 text-slate-200 text-xs font-medium hover:bg-slate-700 transition"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loadingInbox ? 'animate-spin' : ''}`} />
              <span>Refresh Queue</span>
            </button>
          </div>
        </div>

        {/* Demo Triggers */}
        <div className="pt-2 border-t border-slate-800 flex flex-wrap items-center gap-2">
          <span className="text-xs text-slate-400 font-medium flex items-center space-x-1 mr-1">
            <Sparkles className="w-3.5 h-3.5 text-amber-400" />
            <span>SIH Scenarios:</span>
          </span>
          <button
            onClick={() => runDemoScenario('clean')}
            disabled={demoRunning !== null}
            className="px-2.5 py-1 text-xs rounded bg-emerald-950 text-emerald-300 border border-emerald-800 hover:bg-emerald-900 transition flex items-center space-x-1"
          >
            {demoRunning === 'clean' && <RefreshCw className="w-3 h-3 animate-spin" />}
            <span>1. Survey (Clean Approval)</span>
          </button>
          <button
            onClick={() => runDemoScenario('blocked')}
            disabled={demoRunning !== null}
            className="px-2.5 py-1 text-xs rounded bg-amber-950 text-amber-300 border border-amber-800 hover:bg-amber-900 transition flex items-center space-x-1"
          >
            {demoRunning === 'blocked' && <RefreshCw className="w-3 h-3 animate-spin" />}
            <span>2. Actuator Piping (Hard Blocker)</span>
          </button>
          <button
            onClick={() => runDemoScenario('unmatched')}
            disabled={demoRunning !== null}
            className="px-2.5 py-1 text-xs rounded bg-rose-950 text-rose-300 border border-rose-800 hover:bg-rose-900 transition flex items-center space-x-1"
          >
            {demoRunning === 'unmatched' && <RefreshCw className="w-3 h-3 animate-spin" />}
            <span>3. Gate Painting (Rejection)</span>
          </button>
          <button
            onClick={() => runDemoScenario('ambiguous')}
            disabled={demoRunning !== null}
            className="px-2.5 py-1 text-xs rounded bg-indigo-950 text-indigo-300 border border-indigo-800 hover:bg-indigo-900 transition flex items-center space-x-1"
          >
            {demoRunning === 'ambiguous' && <RefreshCw className="w-3 h-3 animate-spin" />}
            <span>4. Ambiguous Weld (Reassign)</span>
          </button>
        </div>
      </div>

      {/* KPI Dashboard Cards */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
          <div className="bg-slate-900 border border-slate-800 rounded-lg p-3">
            <div className="text-[11px] text-slate-400 font-medium">Field Reports</div>
            <div className="text-xl font-bold text-white mt-1">{stats.total_reports}</div>
            <div className="text-[10px] text-slate-500 mt-0.5">{stats.total_events} events parsed</div>
          </div>
          <div className="bg-slate-900 border border-slate-800 rounded-lg p-3">
            <div className="text-[11px] text-slate-400 font-medium">Auto-Matched</div>
            <div className="text-xl font-bold text-emerald-400 mt-1">{stats.auto_matched}</div>
            <div className="text-[10px] text-slate-500 mt-0.5">High confidence &ge; 85%</div>
          </div>
          <div className="bg-slate-900 border border-slate-800 rounded-lg p-3">
            <div className="text-[11px] text-slate-400 font-medium">Needs Review</div>
            <div className="text-xl font-bold text-amber-400 mt-1">{stats.needs_review}</div>
            <div className="text-[10px] text-slate-500 mt-0.5">Pending approval</div>
          </div>
          <div className="bg-slate-900 border border-slate-800 rounded-lg p-3">
            <div className="text-[11px] text-slate-400 font-medium">Blocked by CPM</div>
            <div className="text-xl font-bold text-rose-400 mt-1">{stats.blocked_by_dependency}</div>
            <div className="text-[10px] text-slate-500 mt-0.5">Predecessors unready</div>
          </div>
          <div className="bg-slate-900 border border-slate-800 rounded-lg p-3">
            <div className="text-[11px] text-slate-400 font-medium">Mutated Actuals</div>
            <div className="text-xl font-bold text-teal-400 mt-1">{stats.applied}</div>
            <div className="text-[10px] text-slate-500 mt-0.5">Committed to schedule</div>
          </div>
          <div className="bg-slate-900 border border-slate-800 rounded-lg p-3">
            <div className="text-[11px] text-slate-400 font-medium">Rejected</div>
            <div className="text-xl font-bold text-slate-400 mt-1">{stats.rejected}</div>
            <div className="text-[10px] text-slate-500 mt-0.5">Zero mutation</div>
          </div>
          <div className="bg-slate-900 border border-slate-800 rounded-lg p-3">
            <div className="text-[11px] text-slate-400 font-medium">Hard Violations</div>
            <div className="text-xl font-bold text-rose-500 mt-1">{stats.unresolved_violations}</div>
            <div className="text-[10px] text-slate-500 mt-0.5">Unresolved blockers</div>
          </div>
        </div>
      )}

      {/* Main Review Section */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
        {/* Filters Header */}
        <div className="p-4 border-b border-slate-800 bg-slate-950/60 flex flex-col md:flex-row md:items-center justify-between gap-3">
          {/* Status Tabs */}
          <div className="flex flex-wrap items-center gap-1.5">
            {[
              { id: 'ALL', label: 'All Candidates' },
              { id: 'NEEDS_REVIEW', label: 'Needs Review' },
              { id: 'BLOCKED_BY_DEPENDENCY', label: 'Blocked by Dependency' },
              { id: 'AUTO_MATCHED', label: 'Auto-Matched' },
              { id: 'APPLIED', label: 'Applied (Approved)' },
              { id: 'REJECTED', label: 'Rejected' },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setStatusFilter(tab.id)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${
                  statusFilter === tab.id
                    ? 'bg-emerald-600 text-white shadow-sm'
                    : 'bg-slate-800/80 text-slate-300 hover:bg-slate-800 hover:text-white'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Severity Filter */}
          <div className="flex items-center space-x-2">
            <span className="text-xs text-slate-400">Severity:</span>
            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
              className="bg-slate-800 border border-slate-700 rounded-lg px-2.5 py-1 text-xs text-slate-200 focus:outline-none"
            >
              <option value="ALL">All Severities</option>
              <option value="HARD_VIOLATION">Hard Violations Only</option>
              <option value="SOFT_WARNING">Soft Warnings Only</option>
            </select>
          </div>
        </div>

        {/* Candidate Cards List */}
        <div className="p-4 space-y-4">
          {loadingInbox ? (
            <div className="text-center py-12 text-slate-400 text-xs">
              <RefreshCw className="w-6 h-6 animate-spin mx-auto text-emerald-400 mb-2" />
              Loading review queue candidates...
            </div>
          ) : inboxItems.length === 0 ? (
            <div className="text-center py-12 space-y-2">
              <ShieldCheck className="w-10 h-10 text-emerald-400 mx-auto" />
              <div className="text-sm font-semibold text-slate-200">No candidates in queue</div>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                All field progress events have either been approved, resolved, or no matches match the current filter.
              </p>
            </div>
          ) : (
            inboxItems.map((item) => (
              <div
                key={item.candidate_id}
                className={`border rounded-xl p-4 transition ${
                  item.is_applied
                    ? 'bg-slate-950/40 border-slate-800 opacity-80'
                    : item.status === 'REJECTED'
                    ? 'bg-rose-950/10 border-rose-950/50 opacity-75'
                    : item.has_hard_violations
                    ? 'bg-rose-950/20 border-rose-800/80 shadow-rose-950/30 shadow-md'
                    : 'bg-slate-900 border-slate-800 hover:border-slate-700'
                }`}
              >
                {/* Card Top: Activity Info & Status Badges */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800/80">
                  <div className="space-y-1">
                    <div className="flex items-center space-x-2">
                      <span className="font-mono font-bold text-sm text-emerald-400">{item.activity_code}</span>
                      <span className="text-slate-500">·</span>
                      <span className="font-semibold text-slate-100 text-sm">{item.activity_name}</span>
                      {item.is_critical && (
                        <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-800 font-mono">
                          CRITICAL PATH
                        </span>
                      )}
                    </div>
                    <div className="flex items-center space-x-3 text-xs text-slate-400">
                      <span>Discipline: <strong className="text-slate-300">{item.activity_discipline}</strong></span>
                      <span>Planned Qty: <strong className="text-slate-300">{item.planned_quantity} {item.uom || ''}</strong></span>
                      <span>Current Actual: <strong className="text-slate-300">{item.actual_quantity}</strong></span>
                    </div>
                  </div>

                  <div className="flex items-center space-x-2 self-start sm:self-auto">
                    {/* Confidence Score Pill */}
                    <div className="flex items-center space-x-1.5 px-2.5 py-1 rounded-full bg-slate-800 border border-slate-700 text-xs font-mono">
                      <span className="text-slate-400">Match:</span>
                      <strong
                        className={
                          item.confidence_score >= 0.85
                            ? 'text-emerald-400'
                            : item.confidence_score >= 0.60
                            ? 'text-amber-400'
                            : 'text-rose-400'
                        }
                      >
                        {(item.confidence_score * 100).toFixed(1)}%
                      </strong>
                    </div>

                    {/* Status Badge */}
                    <span
                      className={`text-xs font-mono font-bold px-2.5 py-1 rounded-lg border ${
                        item.is_applied
                          ? 'bg-teal-950 text-teal-300 border-teal-800'
                          : item.status === 'REJECTED'
                          ? 'bg-slate-800 text-slate-400 border-slate-700'
                          : item.status === 'BLOCKED_BY_DEPENDENCY' || item.has_hard_violations
                          ? 'bg-rose-950 text-rose-300 border-rose-800 animate-pulse'
                          : item.status === 'AUTO_MATCHED'
                          ? 'bg-emerald-950 text-emerald-300 border-emerald-800'
                          : 'bg-amber-950 text-amber-300 border-amber-800'
                      }`}
                    >
                      {item.is_applied ? 'APPLIED' : item.has_hard_violations ? 'BLOCKED' : item.status}
                    </span>
                  </div>
                </div>

                {/* Card Middle: Field Report Context & Discrete Checks */}
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 py-3">
                  {/* Field Evidence Context */}
                  <div className="lg:col-span-7 bg-slate-950/50 rounded-lg p-3 border border-slate-800/60 space-y-2">
                    <div className="flex items-center justify-between text-[11px] text-slate-400">
                      <span>Reporter: <strong className="text-slate-300">{item.reporter_name || 'Site Engineer'}</strong></span>
                      <span>Date: <strong className="text-slate-300 font-mono">{item.report_date || 'Today'}</strong></span>
                    </div>
                    <p className="text-xs text-slate-200 italic bg-slate-900/60 p-2 rounded border border-slate-800">
                      "{item.work_description}"
                    </p>
                    <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-400 font-mono">
                      <span>Reported Qty: <strong className="text-amber-300">{item.quantity_reported !== undefined ? item.quantity_reported : 'None'} {item.uom || ''}</strong></span>
                      <span>Status Claim: <strong className="text-emerald-400">{item.status_claim}</strong></span>
                      {item.location_chainage && <span>Location: <strong className="text-slate-300">{item.location_chainage}</strong></span>}
                    </div>
                  </div>

                  {/* Discrete Validation Check Indicators */}
                  <div className="lg:col-span-5 bg-slate-950/50 rounded-lg p-3 border border-slate-800/60 flex flex-col justify-between space-y-2">
                    <div className="text-[11px] font-semibold text-slate-300 uppercase tracking-wider font-mono">
                      Deterministic Schedule Checks
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      {/* Predecessors */}
                      <div className="flex items-center space-x-1.5">
                        {item.validation_checks.predecessor === 'PASS' ? (
                          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                        ) : (
                          <XCircle className="w-4 h-4 text-rose-400 shrink-0" />
                        )}
                        <span className="text-slate-300 text-[11px]">Predecessors</span>
                      </div>

                      {/* Sequence */}
                      <div className="flex items-center space-x-1.5">
                        {item.validation_checks.sequence === 'PASS' ? (
                          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                        ) : (
                          <XCircle className="w-4 h-4 text-rose-400 shrink-0" />
                        )}
                        <span className="text-slate-300 text-[11px]">Chronology</span>
                      </div>

                      {/* Quantity Overrun */}
                      <div className="flex items-center space-x-1.5">
                        {item.validation_checks.quantity === 'PASS' ? (
                          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                        ) : item.validation_checks.quantity === 'WARNING' ? (
                          <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
                        ) : (
                          <XCircle className="w-4 h-4 text-rose-400 shrink-0" />
                        )}
                        <span className="text-slate-300 text-[11px]">Quantity Limits</span>
                      </div>

                      {/* Float / Critical Path */}
                      <div className="flex items-center space-x-1.5">
                        {item.validation_checks.critical_path === 'PASS' ? (
                          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                        ) : (
                          <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
                        )}
                        <span className="text-slate-300 text-[11px]">CPM Float ({item.total_float_days}d)</span>
                      </div>
                    </div>

                    <button
                      onClick={() => handleOpenDetail(item.candidate_id)}
                      className="text-xs text-sky-400 hover:text-sky-300 font-medium flex items-center space-x-1 self-start pt-1"
                    >
                      <Eye className="w-3.5 h-3.5" />
                      <span>360° Context Inspection</span>
                    </button>
                  </div>
                </div>

                {/* Hard Blocker Alert Box */}
                {item.has_hard_violations && item.blocker_reasons.length > 0 && (
                  <div className="mt-2 bg-rose-950/40 border border-rose-800/80 rounded-lg p-3 flex items-start space-x-2 text-xs text-rose-200">
                    <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                    <div className="space-y-1">
                      <div className="font-bold font-mono text-[11px] text-rose-300 uppercase">
                        Schedule Blocker Enforced: Standard Approval Prohibited
                      </div>
                      <ul className="list-disc list-inside space-y-0.5 text-rose-200">
                        {item.blocker_reasons.map((r, i) => (
                          <li key={i}>{r}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )}

                {/* Card Actions Footer */}
                <div className="mt-3 pt-3 border-t border-slate-800/80 flex flex-wrap items-center justify-between gap-2">
                  <div className="text-[11px] text-slate-500 font-mono">
                    Candidate ID: {item.candidate_id.substring(0, 8)}...
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    {/* Reassign Button */}
                    {!item.is_applied && item.status !== 'REJECTED' && (
                      <button
                        onClick={() => {
                          setReassignTarget(item);
                          setReassignActId(item.activity_id);
                          setReassignReason('');
                        }}
                        disabled={actionLoading}
                        className="px-2.5 py-1.5 rounded-lg bg-indigo-950/80 hover:bg-indigo-900 text-indigo-200 border border-indigo-800 text-xs font-medium flex items-center space-x-1 transition"
                      >
                        <CornerUpRight className="w-3.5 h-3.5" />
                        <span>Reassign</span>
                      </button>
                    )}

                    {/* Edit Event Data Button */}
                    {!item.is_applied && item.status !== 'REJECTED' && (
                      <button
                        onClick={() => {
                          setEditTarget(item);
                          setEditQty(item.quantity_reported ? String(item.quantity_reported) : '');
                          setEditUom(item.uom || '');
                          setEditStatusClaim(item.status_claim);
                          setEditReason('');
                        }}
                        disabled={actionLoading}
                        className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-medium flex items-center space-x-1 transition"
                      >
                        <Edit3 className="w-3.5 h-3.5" />
                        <span>Edit Claim</span>
                      </button>
                    )}

                    {/* Reject Button */}
                    {!item.is_applied && item.status !== 'REJECTED' && (
                      <button
                        onClick={() => {
                          setRejectTarget(item);
                          setRejectReason('');
                        }}
                        disabled={actionLoading}
                        className="px-2.5 py-1.5 rounded-lg bg-rose-950/80 hover:bg-rose-900 text-rose-200 border border-rose-800 text-xs font-medium flex items-center space-x-1 transition"
                      >
                        <Ban className="w-3.5 h-3.5" />
                        <span>Reject</span>
                      </button>
                    )}

                    {/* Override & Apply Button (Visible if has hard violations) */}
                    {item.can_override && (
                      <button
                        onClick={() => {
                          setOverrideTarget(item);
                          setOverrideReason('');
                          setOverrideRemarks('');
                        }}
                        disabled={actionLoading}
                        className="px-3.5 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-slate-950 font-bold text-xs flex items-center space-x-1.5 transition shadow-sm"
                      >
                        <ShieldAlert className="w-3.5 h-3.5" />
                        <span>Override & Apply</span>
                      </button>
                    )}

                    {/* Standard Approve & Apply Button */}
                    {item.can_approve && (
                      <button
                        onClick={() => handleApprove(item)}
                        disabled={actionLoading}
                        className="px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs flex items-center space-x-1.5 transition shadow-sm"
                      >
                        <FileCheck className="w-3.5 h-3.5" />
                        <span>Approve & Apply</span>
                      </button>
                    )}

                    {/* Disabled Approve Indicator if Blocked */}
                    {!item.can_approve && !item.can_override && !item.is_applied && item.status !== 'REJECTED' && (
                      <span className="text-[11px] text-slate-500 italic">Approval locked by dependency check</span>
                    )}

                    {/* Applied Badge */}
                    {item.is_applied && (
                      <span className="flex items-center space-x-1 text-xs text-teal-400 font-semibold px-2 py-1 bg-teal-950/60 rounded border border-teal-800">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span>Actuals Mutated & Verified</span>
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Immutable Review & Mutation Audit Trail Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm space-y-3 p-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
          <div className="flex items-center space-x-2">
            <History className="w-4 h-4 text-emerald-400" />
            <h3 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
              Immutable Review & Mutation Audit Trail
            </h3>
          </div>

          <div className="flex items-center space-x-2">
            <span className="text-xs text-slate-400">Action:</span>
            <select
              value={auditActionFilter}
              onChange={(e) => setAuditActionFilter(e.target.value)}
              className="bg-slate-800 border border-slate-700 rounded-lg px-2.5 py-1 text-xs text-slate-200 focus:outline-none"
            >
              <option value="ALL">All Actions</option>
              <option value="APPROVED">APPROVED</option>
              <option value="OVERRIDDEN">OVERRIDDEN</option>
              <option value="REJECTED">REJECTED</option>
              <option value="REASSIGNED">REASSIGNED</option>
              <option value="EDITED">EDITED</option>
            </select>
          </div>
        </div>

        {loadingAudits ? (
          <div className="text-center py-6 text-xs text-slate-400">Loading audit records...</div>
        ) : auditLogs.length === 0 ? (
          <div className="text-center py-6 text-xs text-slate-500">No review or mutation audits recorded yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400 font-mono text-[11px]">
                  <th className="py-2 px-2">Timestamp</th>
                  <th className="py-2 px-2">Action</th>
                  <th className="py-2 px-2">Actor</th>
                  <th className="py-2 px-2">Activity Code</th>
                  <th className="py-2 px-2">Override?</th>
                  <th className="py-2 px-2">Remarks / Justification</th>
                  <th className="py-2 px-2">Mutated Values (Diff)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-sans">
                {auditLogs.map((log) => (
                  <tr key={log.id} className="hover:bg-slate-800/40">
                    <td className="py-2.5 px-2 font-mono text-[11px] text-slate-400">
                      {new Date(log.review_timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    </td>
                    <td className="py-2.5 px-2">
                      <span
                        className={`text-[10px] font-bold px-2 py-0.5 rounded font-mono ${
                          log.action === 'APPROVED'
                            ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                            : log.action === 'OVERRIDDEN'
                            ? 'bg-amber-950 text-amber-300 border border-amber-800'
                            : log.action === 'REJECTED'
                            ? 'bg-rose-950 text-rose-300 border border-rose-800'
                            : 'bg-indigo-950 text-indigo-300 border border-indigo-800'
                        }`}
                      >
                        {log.action}
                      </span>
                    </td>
                    <td className="py-2.5 px-2 font-medium text-slate-200">{log.reviewer_user}</td>
                    <td className="py-2.5 px-2 font-mono font-semibold text-emerald-400">{log.activity_code || '—'}</td>
                    <td className="py-2.5 px-2">
                      {log.is_override ? (
                        <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-800 font-mono">
                          OVERRIDE
                        </span>
                      ) : (
                        <span className="text-slate-500 font-mono text-[10px]">NO</span>
                      )}
                    </td>
                    <td className="py-2.5 px-2 max-w-xs text-slate-300 truncate">
                      {log.is_override && log.override_reason ? (
                        <span className="text-amber-200"><strong>Reason:</strong> {log.override_reason}</span>
                      ) : (
                        log.remarks || '—'
                      )}
                    </td>
                    <td className="py-2.5 px-2 font-mono text-[10px] text-slate-400">
                      {log.new_values && Object.keys(log.new_values).length > 0 ? (
                        <span className="text-teal-300">
                          {Object.entries(log.new_values)
                            .filter(([k]) => ['actual_quantity', 'actual_start', 'actual_finish', 'physical_percent_complete'].includes(k))
                            .map(([k, v]) => `${k.replace('actual_', '')}:${v}`)
                            .join(', ')}
                        </span>
                      ) : (
                        <span className="text-slate-500">None</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* MODAL: OVERRIDE & APPLY */}
      {overrideTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-amber-600/60 rounded-xl max-w-lg w-full p-5 space-y-4 shadow-2xl">
            <div className="flex items-center space-x-2 text-amber-400">
              <ShieldAlert className="w-5 h-5" />
              <h3 className="text-base font-bold text-white">Override Schedule Dependency Blocker</h3>
            </div>
            <p className="text-xs text-slate-300">
              Activity <strong className="text-emerald-400 font-mono">[{overrideTarget.activity_code}]</strong> has unresolved hard dependency violations.
              Overriding will force actual progress into the schedule.
            </p>

            <div className="bg-rose-950/30 border border-rose-800/80 rounded-lg p-3 text-xs text-rose-200 space-y-1">
              <div className="font-bold text-rose-300">Active Schedule Blockers:</div>
              <ul className="list-disc list-inside space-y-0.5">
                {overrideTarget.blocker_reasons.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-200">
                Mandatory Override Justification <span className="text-rose-400">*</span> (min 5 chars)
              </label>
              <textarea
                value={overrideReason}
                onChange={(e) => setOverrideReason(e.target.value)}
                placeholder="e.g., Predecessor civil curing verified offline via non-destructive core testing."
                rows={3}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-amber-500 font-sans"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-300">Additional Remarks (Optional)</label>
              <input
                type="text"
                value={overrideRemarks}
                onChange={(e) => setOverrideRemarks(e.target.value)}
                placeholder="e.g., Authorized per Project Director instructions."
                className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none"
              />
            </div>

            <div className="flex items-center justify-end space-x-2 pt-2 border-t border-slate-800">
              <button
                onClick={() => setOverrideTarget(null)}
                className="px-3 py-1.5 rounded-lg bg-slate-800 text-slate-300 text-xs font-medium hover:bg-slate-700 transition"
              >
                Cancel
              </button>
              <button
                onClick={handleOverrideSubmit}
                disabled={actionLoading || overrideReason.trim().length < 5}
                className="px-4 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-slate-950 font-bold text-xs transition"
              >
                Confirm Override & Apply
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL: REJECT */}
      {rejectTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-rose-800/80 rounded-xl max-w-md w-full p-5 space-y-4 shadow-2xl">
            <div className="flex items-center space-x-2 text-rose-400">
              <Ban className="w-5 h-5" />
              <h3 className="text-base font-bold text-white">Reject Candidate</h3>
            </div>
            <p className="text-xs text-slate-300">
              Rejecting will mark the candidate as REJECTED. <strong className="text-emerald-300">Zero schedule actuals will be modified.</strong>
            </p>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-200">
                Reason for Rejection <span className="text-rose-400">*</span>
              </label>
              <textarea
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="e.g., Duplicate report entry / Scope belongs to vendor outside baseline schedule."
                rows={3}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-rose-500"
              />
            </div>

            <div className="flex items-center justify-end space-x-2 pt-2 border-t border-slate-800">
              <button
                onClick={() => setRejectTarget(null)}
                className="px-3 py-1.5 rounded-lg bg-slate-800 text-slate-300 text-xs font-medium hover:bg-slate-700 transition"
              >
                Cancel
              </button>
              <button
                onClick={handleRejectSubmit}
                disabled={actionLoading || rejectReason.trim().length < 3}
                className="px-4 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 disabled:opacity-50 text-white font-bold text-xs transition"
              >
                Confirm Rejection
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL: REASSIGN */}
      {reassignTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-indigo-700/80 rounded-xl max-w-lg w-full p-5 space-y-4 shadow-2xl">
            <div className="flex items-center space-x-2 text-indigo-400">
              <CornerUpRight className="w-5 h-5" />
              <h3 className="text-base font-bold text-white">Reassign Candidate to Activity</h3>
            </div>
            <p className="text-xs text-slate-300">
              Reassignment triggers <strong className="text-amber-300">fresh deterministic validation</strong> against the newly selected activity.
              Zero schedule actuals will be modified until subsequent approval.
            </p>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-200">Select Target Activity</label>
              <select
                value={reassignActId}
                onChange={(e) => setReassignActId(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-xs text-slate-100 focus:outline-none focus:border-indigo-500"
              >
                {activities.map((act) => (
                  <option key={act.id} value={act.id}>
                    {act.activity_code} — {act.name} ({act.discipline})
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-300">Reassignment Justification</label>
              <input
                type="text"
                value={reassignReason}
                onChange={(e) => setReassignReason(e.target.value)}
                placeholder="e.g., Work statement corresponds to mainline tie-in rather than standard welding."
                className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none"
              />
            </div>

            <div className="flex items-center justify-end space-x-2 pt-2 border-t border-slate-800">
              <button
                onClick={() => setReassignTarget(null)}
                className="px-3 py-1.5 rounded-lg bg-slate-800 text-slate-300 text-xs font-medium hover:bg-slate-700 transition"
              >
                Cancel
              </button>
              <button
                onClick={handleReassignSubmit}
                disabled={actionLoading || !reassignActId}
                className="px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-bold text-xs transition"
              >
                Confirm Reassignment
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL: EDIT EVENT DATA */}
      {editTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-md w-full p-5 space-y-4 shadow-2xl">
            <div className="flex items-center space-x-2 text-slate-200">
              <Edit3 className="w-5 h-5 text-emerald-400" />
              <h3 className="text-base font-bold text-white">Edit Reported Progress Claim</h3>
            </div>
            <p className="text-xs text-slate-300">
              Adjusts extracted parameters. Triggers immediate fresh validation without modifying baseline schedule.
            </p>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300">Quantity</label>
                <input
                  type="number"
                  step="any"
                  value={editQty}
                  onChange={(e) => setEditQty(e.target.value)}
                  placeholder="e.g., 5.0"
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-xs text-slate-100 focus:outline-none"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300">UOM</label>
                <input
                  type="text"
                  value={editUom}
                  onChange={(e) => setEditUom(e.target.value)}
                  placeholder="e.g., KM, M, JOINTS"
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-xs text-slate-100 focus:outline-none"
                />
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-300">Status Claim</label>
              <select
                value={editStatusClaim}
                onChange={(e) => setEditStatusClaim(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-xs text-slate-100 focus:outline-none"
              >
                <option value="STARTED">STARTED</option>
                <option value="IN_PROGRESS">IN_PROGRESS</option>
                <option value="COMPLETED">COMPLETED</option>
                <option value="MILESTONE_COMPLETED">MILESTONE_COMPLETED</option>
              </select>
            </div>

            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-300">Adjustment Justification</label>
              <input
                type="text"
                value={editReason}
                onChange={(e) => setEditReason(e.target.value)}
                placeholder="e.g., Field surveyor clarified exclusion of swamp section."
                className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-xs text-slate-100 focus:outline-none"
              />
            </div>

            <div className="flex items-center justify-end space-x-2 pt-2 border-t border-slate-800">
              <button
                onClick={() => setEditTarget(null)}
                className="px-3 py-1.5 rounded-lg bg-slate-800 text-slate-300 text-xs font-medium hover:bg-slate-700 transition"
              >
                Cancel
              </button>
              <button
                onClick={handleEditSubmit}
                disabled={actionLoading}
                className="px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-bold text-xs transition"
              >
                Save & Re-Validate
              </button>
            </div>
          </div>
        </div>
      )}

      {/* DRAWER / MODAL: CANDIDATE 360 DETAIL */}
      {selectedCandidateId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/85 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-3xl w-full max-h-[90vh] overflow-y-auto p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center space-x-2">
                <Eye className="w-5 h-5 text-sky-400" />
                <h3 className="text-base font-bold text-white">360° Candidate Context Inspection</h3>
              </div>
              <button
                onClick={() => {
                  setSelectedCandidateId(null);
                  setCandidateDetail(null);
                }}
                className="text-slate-400 hover:text-white text-xs font-mono px-2 py-1 bg-slate-800 rounded"
              >
                ESC / Close
              </button>
            </div>

            {loadingDetail || !candidateDetail ? (
              <div className="text-center py-12 text-slate-400 text-xs">
                <RefreshCw className="w-6 h-6 animate-spin mx-auto text-sky-400 mb-2" />
                Loading candidate context...
              </div>
            ) : (
              <>
                {/* Side-by-side comparison */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                  {/* Left: Field DPR Evidence */}
                  <div className="bg-slate-950/60 p-3.5 rounded-lg border border-slate-800 space-y-2">
                    <div className="font-bold font-mono text-emerald-400 uppercase tracking-wider text-[11px]">
                      1. Field Daily Progress Report
                    </div>
                <div className="text-slate-300">
                  <span className="text-slate-500">Reporter:</span> {candidateDetail.reporter_name}
                </div>
                <div className="text-slate-300">
                  <span className="text-slate-500">Date:</span> {candidateDetail.report_date}
                </div>
                <div className="bg-slate-900 p-2 rounded text-slate-200 italic border border-slate-800">
                  "{candidateDetail.work_description}"
                </div>
                <div className="grid grid-cols-2 gap-2 pt-1 font-mono text-[11px]">
                  <div>Discipline: <strong className="text-slate-200">{candidateDetail.discipline}</strong></div>
                  <div>Status: <strong className="text-emerald-400">{candidateDetail.status_claim}</strong></div>
                  <div>Reported Qty: <strong className="text-amber-300">{candidateDetail.quantity_reported ?? '—'} {candidateDetail.uom}</strong></div>
                  <div>Location: <strong className="text-slate-200">{candidateDetail.location_chainage ?? '—'}</strong></div>
                </div>
              </div>

              {/* Right: Master Schedule Target */}
              <div className="bg-slate-950/60 p-3.5 rounded-lg border border-slate-800 space-y-2">
                <div className="font-bold font-mono text-sky-400 uppercase tracking-wider text-[11px]">
                  2. Master Schedule Activity
                </div>
                <div className="text-slate-300">
                  <span className="text-slate-500">Code:</span> <strong className="text-emerald-400 font-mono">{candidateDetail.activity_code}</strong>
                </div>
                <div className="text-slate-300">
                  <span className="text-slate-500">Name:</span> {candidateDetail.activity_name}
                </div>
                <div className="grid grid-cols-2 gap-2 pt-1 font-mono text-[11px]">
                  <div>Planned Qty: <strong className="text-slate-200">{candidateDetail.planned_quantity} {candidateDetail.activity_uom}</strong></div>
                  <div>Actual Qty: <strong className="text-teal-300">{candidateDetail.actual_quantity}</strong></div>
                  <div>Discipline: <strong className="text-slate-200">{candidateDetail.activity_discipline}</strong></div>
                  <div>Critical Path: <strong className={candidateDetail.is_critical ? 'text-rose-400' : 'text-slate-400'}>{candidateDetail.is_critical ? 'YES' : 'NO'}</strong></div>
                  <div>Total Float: <strong className="text-slate-200">{candidateDetail.total_float_days} days</strong></div>
                </div>
              </div>
            </div>

            {/* Score Breakdown */}
            {candidateDetail.score_breakdown && (
              <div className="bg-slate-950/60 p-3.5 rounded-lg border border-slate-800 space-y-2 text-xs">
                <div className="font-bold font-mono text-amber-400 uppercase tracking-wider text-[11px]">
                  3. Multi-Factor Confidence Breakdown
                </div>
                <div className="grid grid-cols-5 gap-2 text-center font-mono">
                  <div className="bg-slate-900 p-2 rounded border border-slate-800">
                    <div className="text-[10px] text-slate-500">Semantic</div>
                    <div className="text-sm font-bold text-slate-200">{((candidateDetail.score_breakdown.semantic || 0) * 100).toFixed(0)}%</div>
                  </div>
                  <div className="bg-slate-900 p-2 rounded border border-slate-800">
                    <div className="text-[10px] text-slate-500">Discipline</div>
                    <div className="text-sm font-bold text-slate-200">{((candidateDetail.score_breakdown.discipline || 0) * 100).toFixed(0)}%</div>
                  </div>
                  <div className="bg-slate-900 p-2 rounded border border-slate-800">
                    <div className="text-[10px] text-slate-500">Location</div>
                    <div className="text-sm font-bold text-slate-200">{((candidateDetail.score_breakdown.location || 0) * 100).toFixed(0)}%</div>
                  </div>
                  <div className="bg-slate-900 p-2 rounded border border-slate-800">
                    <div className="text-[10px] text-slate-500">Quantity/UOM</div>
                    <div className="text-sm font-bold text-slate-200">{((candidateDetail.score_breakdown.quantity || 0) * 100).toFixed(0)}%</div>
                  </div>
                  <div className="bg-slate-900 p-2 rounded border border-slate-800">
                    <div className="text-[10px] text-slate-500">Temporal</div>
                    <div className="text-sm font-bold text-slate-200">{((candidateDetail.score_breakdown.temporal || 0) * 100).toFixed(0)}%</div>
                  </div>
                </div>
              </div>
            )}

            {/* Violations Detail */}
            {candidateDetail.violations && candidateDetail.violations.length > 0 && (
              <div className="bg-rose-950/30 p-3.5 rounded-lg border border-rose-800/80 space-y-2 text-xs">
                <div className="font-bold font-mono text-rose-300 uppercase tracking-wider text-[11px]">
                  4. Active Schedule Violations ({candidateDetail.violations.length})
                </div>
                <div className="space-y-1.5">
                  {candidateDetail.violations.map((v, i) => (
                    <div key={i} className="flex items-start space-x-2 text-rose-200">
                      <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                      <div>
                        <strong>[{v.severity}] {v.violation_type}:</strong> {v.description}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
              </>
            )}

            <div className="flex justify-end pt-2 border-t border-slate-800">
              <button
                onClick={() => {
                  setSelectedCandidateId(null);
                  setCandidateDetail(null);
                }}
                className="px-4 py-1.5 rounded-lg bg-slate-800 text-slate-200 text-xs font-semibold hover:bg-slate-700 transition"
              >
                Close Inspection
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
