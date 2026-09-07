import React, { useState, useEffect } from 'react';
import {
  Sparkles,
  ShieldCheck,
  ShieldAlert,
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
  ArrowRight,
  UserCheck,
  Sliders,
  FileSpreadsheet,
  FileText,
  CornerUpRight,
  Lock,
  Check,
  Ban,
  ExternalLink
} from 'lucide-react';
import { apiService, demoApi } from '../api/client';
import {
  ScheduleActivity,
  ReviewInboxItem,
  ReviewCandidateDetail,
  DemoStatus
} from '../types';

interface PlanningExecutionBridgeProps {
  projectId: string;
  activities: ScheduleActivity[];
  onScheduleUpdated: () => void;
  onNavigateToTab?: (tab: 'schedule' | 'field' | 'matching' | 'validation' | 'review') => void;
}

export const PlanningExecutionBridge: React.FC<PlanningExecutionBridgeProps> = ({
  projectId,
  activities,
  onScheduleUpdated,
  onNavigateToTab,
}) => {
  const [demoStatus, setDemoStatus] = useState<DemoStatus | null>(null);
  const [loadingDemo, setLoadingDemo] = useState(false);
  const [seedMessage, setSeedMessage] = useState<string | null>(null);

  // Candidates & Selection
  const [candidates, setCandidates] = useState<ReviewInboxItem[]>([]);
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);
  const [candidateDetail, setCandidateDetail] = useState<ReviewCandidateDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // Active Demo Scenario
  const [activeScenarioId, setActiveScenarioId] = useState<string>('SCENARIO-1');

  // Action Modals
  const [showOverrideModal, setShowOverrideModal] = useState(false);
  const [overrideReason, setOverrideReason] = useState('');
  const [showReassignModal, setShowReassignModal] = useState(false);
  const [targetActivityId, setTargetActivityId] = useState('');
  const [reassignReason, setReassignReason] = useState('');
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [actionLoading, setActionLoading] = useState(false);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    loadDemoStatus();
    loadCandidates();
  }, [projectId]);

  useEffect(() => {
    if (selectedCandidateId) {
      loadCandidateDetail(selectedCandidateId);
    }
  }, [selectedCandidateId]);

  const loadDemoStatus = async () => {
    try {
      const status = await demoApi.getDemoStatus();
      setDemoStatus(status);
    } catch (err) {
      console.error('Failed to load demo status', err);
    }
  };

  const loadCandidates = async () => {
    try {
      const items = await apiService.getReviewInbox(projectId);
      setCandidates(items);
      if (items.length > 0 && !selectedCandidateId) {
        // Default to candidate matching Scenario 1 (ACT-1010) or first
        const s1 = items.find((i) => i.activity_code === 'ACT-1010') || items[0];
        setSelectedCandidateId(s1.candidate_id);
      }
    } catch (err) {
      console.error('Failed to load review inbox items', err);
    }
  };

  const loadCandidateDetail = async (id: string) => {
    setLoadingDetail(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const detail = await apiService.getCandidateDetail(id);
      setCandidateDetail(detail);
    } catch (err) {
      console.error('Failed to load candidate detail', err);
    } finally {
      setLoadingDetail(false);
    }
  };

  const handleSeedDemo = async () => {
    setLoadingDemo(true);
    setSeedMessage(null);
    try {
      await demoApi.seedDemo();
      setSeedMessage(`Seeded: 20 Activities, 25 Dependencies, 5 DPRs, 6 Events.`);
      await loadDemoStatus();
      await loadCandidates();
      onScheduleUpdated();
    } catch (err: any) {
      setSeedMessage(`Seed failed: ${err.response?.data?.detail || err.message}`);
    } finally {
      setLoadingDemo(false);
    }
  };

  const handleResetDemo = async () => {
    setLoadingDemo(true);
    setSeedMessage(null);
    try {
      await demoApi.resetDemo();
      setSeedMessage(`Demo reset to pristine unmutated baseline.`);
      await loadDemoStatus();
      await loadCandidates();
      setSelectedCandidateId(null);
      setCandidateDetail(null);
      onScheduleUpdated();
    } catch (err: any) {
      setSeedMessage(`Reset failed: ${err.response?.data?.detail || err.message}`);
    } finally {
      setLoadingDemo(false);
    }
  };

  const handleSelectScenario = (scenId: string) => {
    setActiveScenarioId(scenId);
    if (!candidates || candidates.length === 0) return;

    let target: ReviewInboxItem | undefined;
    if (scenId === 'SCENARIO-1') {
      target = candidates.find((c) => c.activity_code === 'ACT-1010');
    } else if (scenId === 'SCENARIO-2') {
      target = candidates.find((c) => c.activity_code === 'ACT-2030' || (c.work_description || '').toLowerCase().includes('river') || (c.raw_text_snippet || '').toLowerCase().includes('river'));
    } else if (scenId === 'SCENARIO-3') {
      target = candidates.find((c) => c.activity_code === 'ACT-5020');
    } else if (scenId === 'SCENARIO-4') {
      target = candidates.find((c) => c.confidence_score < 0.50 || (c.work_description || '').toLowerCase().includes('security gate') || (c.raw_text_snippet || '').toLowerCase().includes('security gate'));
    } else if (scenId === 'SCENARIO-5') {
      target = candidates.find((c) => c.activity_code === 'ACT-1030' || (c.work_description || '').toLowerCase().includes('trench') || (c.raw_text_snippet || '').toLowerCase().includes('trench'));
    }

    if (target) {
      setSelectedCandidateId(target.candidate_id);
    }
  };

  // Approval Handler
  const handleApprove = async () => {
    if (!selectedCandidateId) return;
    setActionLoading(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const res = await apiService.approveCandidate(
        selectedCandidateId,
        'Site Planning Lead',
        'Verified via Bridge Interface.'
      );
      setActionSuccess(`Approved! Mutated actuals for ${res.activity_code}: Qty=${res.new_values?.actual_quantity}, %=${res.new_values?.physical_percent_complete}%`);
      await loadCandidates();
      await loadCandidateDetail(selectedCandidateId);
      onScheduleUpdated();
    } catch (err: any) {
      setActionError(err.response?.data?.detail || err.message);
    } finally {
      setActionLoading(false);
    }
  };

  // Override Handler
  const handleOverride = async () => {
    if (!selectedCandidateId || overrideReason.trim().length < 5) return;
    setActionLoading(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const res = await apiService.overrideCandidate(
        selectedCandidateId,
        overrideReason,
        'Project Director',
        'Authorized executive override applied.'
      );
      setActionSuccess(`Overridden! Mutated actuals for ${res.activity_code}: Qty=${res.new_values?.actual_quantity}`);
      setShowOverrideModal(false);
      setOverrideReason('');
      await loadCandidates();
      await loadCandidateDetail(selectedCandidateId);
      onScheduleUpdated();
    } catch (err: any) {
      setActionError(err.response?.data?.detail || err.message);
    } finally {
      setActionLoading(false);
    }
  };

  // Reassign Handler
  const handleReassign = async () => {
    if (!selectedCandidateId || !targetActivityId) return;
    setActionLoading(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const res = await apiService.reassignCandidate(
        selectedCandidateId,
        targetActivityId,
        reassignReason || 'Reassigned in Bridge Interface.',
        'Lead Pipeline Engineer'
      );
      setActionSuccess(`Candidate successfully reassigned to ${res.activity_code}! Fresh validation evaluated. Schedule actuals remain 100% unmutated.`);
      setShowReassignModal(false);
      setTargetActivityId('');
      setReassignReason('');
      await loadCandidates();
      await loadCandidateDetail(selectedCandidateId);
      onScheduleUpdated();
    } catch (err: any) {
      setActionError(err.response?.data?.detail || err.message);
    } finally {
      setActionLoading(false);
    }
  };

  // Reject Handler
  const handleReject = async () => {
    if (!selectedCandidateId || !rejectReason.trim()) return;
    setActionLoading(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      await apiService.rejectCandidate(
        selectedCandidateId,
        rejectReason,
        'Lead Construction Manager'
      );
      setActionSuccess(`Candidate REJECTED. Logged in audit trail. Zero schedule actuals modified.`);
      setShowRejectModal(false);
      setRejectReason('');
      await loadCandidates();
      await loadCandidateDetail(selectedCandidateId);
      onScheduleUpdated();
    } catch (err: any) {
      setActionError(err.response?.data?.detail || err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const activeActivity = activities.find((a) => a.id === candidateDetail?.activity_id);

  return (
    <div className="space-y-6">
      {/* ========================================================================= */}
      {/* 1. TOP DEMO CONTROLS & SCENARIO LAUNCHER BAR */}
      {/* ========================================================================= */}
      <div className="bg-gradient-to-r from-slate-900 via-slate-900/90 to-emerald-950/50 border border-slate-800 rounded-xl p-5 shadow-lg">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-4 border-b border-slate-800/80">
          <div>
            <div className="flex items-center space-x-2">
              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-900/80 text-emerald-300 border border-emerald-700">
                SIH 2026 Problem Statement SIH26122
              </span>
              <span className="text-xs text-slate-400 font-mono">Oil India Limited</span>
              {demoStatus?.is_seeded && (
                <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800 font-mono">
                  Demo Active ({demoStatus.activities_count} Acts · {demoStatus.events_count} Evts)
                </span>
              )}
            </div>
            <h2 className="text-xl font-extrabold text-white mt-1 flex items-center space-x-2">
              <span>Planning → Execution Bridge</span>
              <span className="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono font-normal">
                4-Stage Safe Pipeline
              </span>
            </h2>
            <p className="text-xs text-slate-400 mt-0.5 max-w-3xl">
              Harmonizing raw unstructured field execution with deterministic Primavera/MS Project schedule actuals.
              Strict architectural invariant: <strong className="text-amber-300">AI interprets field reality</strong>,{' '}
              <strong className="text-teal-300">Deterministic CPM rules validate it</strong>, and{' '}
              <strong className="text-emerald-300">Human Authority approves it</strong>.
            </p>
          </div>

          {/* Quick Seed / Reset Controls & Navigation */}
          <div className="flex items-center space-x-3 shrink-0">
            {onNavigateToTab && (
              <button
                onClick={() => onNavigateToTab('review')}
                className="flex items-center space-x-1 px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800/60 hover:bg-slate-700 text-slate-300 text-xs font-medium transition"
              >
                <span>Review Inbox</span>
                <ExternalLink className="w-3 h-3 text-emerald-400" />
              </button>
            )}
            <button
              onClick={handleResetDemo}
              disabled={loadingDemo}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800/80 hover:bg-slate-700 text-slate-300 text-xs font-semibold transition"
              title="Reset demo candidates to pristine unapproved state"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loadingDemo ? 'animate-spin' : ''}`} />
              <span>Reset Demo</span>
            </button>
            <button
              onClick={handleSeedDemo}
              disabled={loadingDemo}
              className="flex items-center space-x-1.5 px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition shadow-sm"
              title="Deterministically seed the 20-activity Oil India pipeline demo dataset"
            >
              <Sparkles className="w-3.5 h-3.5 text-amber-300" />
              <span>{loadingDemo ? 'Seeding...' : 'Seed Demo Data'}</span>
            </button>
          </div>
        </div>

        {seedMessage && (
          <div className="mt-3 text-xs px-3 py-1.5 rounded bg-emerald-950/60 border border-emerald-800 text-emerald-300 font-mono">
            {seedMessage}
          </div>
        )}

        {/* 5 Scenario Selector Cards */}
        <div className="mt-4">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-2">
            Select an SIH Demo Scenario to Inspect Through the Bridge:
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2.5">
            {[
              {
                id: 'SCENARIO-1',
                badge: 'Scenario 1',
                title: 'High-Confidence Clean Match',
                code: 'ACT-1010',
                desc: 'Topographical survey, ≥0.85 score. Clean 1-click approval mutates actuals.',
                color: 'border-emerald-700/60 hover:border-emerald-500 bg-emerald-950/20',
                activeColor: 'ring-2 ring-emerald-400 border-emerald-500 bg-emerald-950/50',
              },
              {
                id: 'SCENARIO-2',
                badge: 'Scenario 2',
                title: 'Ambiguous Scope Reassignment',
                code: 'ACT-2030 → ACT-3010',
                desc: 'River crossing welding. Engineer reassigns scope with 0 schedule mutation.',
                color: 'border-amber-700/60 hover:border-amber-500 bg-amber-950/20',
                activeColor: 'ring-2 ring-amber-400 border-amber-500 bg-amber-950/50',
              },
              {
                id: 'SCENARIO-3',
                badge: 'Scenario 3',
                title: 'Dependency Blocker & Override',
                code: 'ACT-5020',
                desc: 'Manifold piping blocked by raft curing. Mandatory rationale override.',
                color: 'border-red-700/60 hover:border-red-500 bg-red-950/20',
                activeColor: 'ring-2 ring-red-400 border-red-500 bg-red-950/50',
              },
              {
                id: 'SCENARIO-4',
                badge: 'Scenario 4',
                title: 'Out-of-Scope Safe Rejection',
                code: 'UNMATCHED (<0.50)',
                desc: 'Security gate painting. Blocked from schedule; engineer rejection logged.',
                color: 'border-slate-700 hover:border-slate-500 bg-slate-900/40',
                activeColor: 'ring-2 ring-slate-400 border-slate-500 bg-slate-800/60',
              },
              {
                id: 'SCENARIO-5',
                badge: 'Scenario 5',
                title: 'Multi-Event DPR Discretization',
                code: 'ACT-1030 + ACT-2010',
                desc: 'Trenching 450m & stringing 25 joints parsed into distinct audited actuals.',
                color: 'border-teal-700/60 hover:border-teal-500 bg-teal-950/20',
                activeColor: 'ring-2 ring-teal-400 border-teal-500 bg-teal-950/50',
              },
            ].map((scen) => {
              const isSelected = activeScenarioId === scen.id;
              return (
                <button
                  key={scen.id}
                  onClick={() => handleSelectScenario(scen.id)}
                  className={`p-3 rounded-lg border text-left transition flex flex-col justify-between ${
                    isSelected ? scen.activeColor : scen.color
                  }`}
                >
                  <div>
                    <div className="flex items-center justify-between text-[11px] font-mono mb-1">
                      <span className="font-bold text-slate-300">{scen.badge}</span>
                      <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-400">
                        {scen.code}
                      </span>
                    </div>
                    <div className="text-xs font-bold text-slate-100">{scen.title}</div>
                    <p className="text-[11px] text-slate-400 mt-1 line-clamp-2 leading-snug">
                      {scen.desc}
                    </p>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Action Notification Banners */}
      {actionSuccess && (
        <div className="flex items-center space-x-2 p-3 rounded-lg bg-emerald-950/80 border border-emerald-600 text-emerald-200 text-xs">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          <span className="font-medium">{actionSuccess}</span>
        </div>
      )}
      {actionError && (
        <div className="flex items-center space-x-2 p-3 rounded-lg bg-red-950/80 border border-red-700 text-red-200 text-xs">
          <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
          <span className="font-medium">{actionError}</span>
        </div>
      )}

      {/* Candidate Selector Pill Bar if candidates loaded */}
      {candidates.length > 0 && (
        <div className="flex items-center space-x-2 overflow-x-auto pb-1 text-xs">
          <span className="text-slate-400 font-mono text-[11px] shrink-0">Candidates ({candidates.length}):</span>
          {candidates.map((c) => {
            const isSel = c.candidate_id === selectedCandidateId;
            let statusBadge = 'bg-slate-800 text-slate-300 border-slate-700';
            if (c.status === 'APPLIED') statusBadge = 'bg-emerald-900/60 text-emerald-300 border-emerald-600';
            else if (c.status === 'BLOCKED_BY_DEPENDENCY') statusBadge = 'bg-red-950 text-red-300 border-red-800';
            else if (c.status === 'AUTO_MATCHED') statusBadge = 'bg-blue-950 text-blue-300 border-blue-800';
            else if (c.status === 'REJECTED') statusBadge = 'bg-slate-900 text-slate-500 border-slate-800 line-through';

            return (
              <button
                key={c.candidate_id}
                onClick={() => setSelectedCandidateId(c.candidate_id)}
                className={`px-3 py-1 rounded-md border font-mono text-xs flex items-center space-x-1.5 shrink-0 transition ${
                  isSel
                    ? 'bg-slate-100 text-slate-950 font-bold border-white'
                    : 'bg-slate-900 text-slate-300 hover:border-slate-600'
                }`}
              >
                <span>{c.activity_code}</span>
                <span className={`text-[10px] px-1 py-0.2 rounded border ${statusBadge}`}>
                  {c.status === 'BLOCKED_BY_DEPENDENCY' ? 'BLOCKED' : c.status}
                </span>
                <span className="text-[10px] opacity-70">
                  {(c.confidence_score * 100).toFixed(0)}%
                </span>
              </button>
            );
          })}
        </div>
      )}

      {/* ========================================================================= */}
      {/* 2. THE 4-STAGE ARCHITECTURAL PIPELINE VISUALIZATION */}
      {/* ========================================================================= */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* ---------------- STAGE 1: FIELD REALITY ---------------- */}
        <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4 flex flex-col justify-between shadow-sm relative overflow-hidden">
          <div className="absolute top-0 right-0 px-2 py-0.5 bg-blue-950 text-blue-300 border-b border-l border-blue-800 rounded-bl text-[10px] font-mono">
            STAGE 1
          </div>
          <div>
            <div className="flex items-center space-x-2 mb-2">
              <FileText className="w-4 h-4 text-blue-400" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                Field Reality (DPR)
              </h3>
            </div>

            {loadingDetail ? (
              <div className="text-xs text-slate-500 py-6 text-center">Loading context...</div>
            ) : candidateDetail ? (
              <div className="space-y-2.5 text-xs">
                <div className="bg-slate-950 p-2.5 rounded border border-slate-800 font-mono text-[11px] text-slate-300 leading-relaxed italic">
                  "{candidateDetail.raw_text_snippet}"
                </div>
                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  <div>
                    <span className="text-slate-500">Reported By:</span>
                    <div className="font-semibold text-slate-200 truncate">
                      {candidateDetail.reporter_name || 'Site Engineer'}
                    </div>
                  </div>
                  <div>
                    <span className="text-slate-500">Event Date:</span>
                    <div className="font-mono text-slate-200">
                      {candidateDetail.event_date || '2026-10-05'}
                    </div>
                  </div>
                  <div>
                    <span className="text-slate-500">Claimed Qty:</span>
                    <div className="font-mono font-bold text-amber-300">
                      {candidateDetail.quantity_reported !== undefined && candidateDetail.quantity_reported !== null
                        ? `${candidateDetail.quantity_reported} ${candidateDetail.uom || ''}`
                        : 'Unspecified'}
                    </div>
                  </div>
                  <div>
                    <span className="text-slate-500">Status Claim:</span>
                    <div className="font-mono text-emerald-400 font-semibold">
                      {candidateDetail.status_claim || 'IN_PROGRESS'}
                    </div>
                  </div>
                </div>
                <div>
                  <span className="text-slate-500 text-[10px]">Location Claim:</span>
                  <div className="font-mono text-[11px] text-slate-300 bg-slate-900 px-2 py-0.5 rounded border border-slate-800 truncate">
                    {candidateDetail.location_chainage || 'General alignment'}
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-xs text-slate-500 py-6 text-center">No candidate selected</div>
            )}
          </div>
          <div className="mt-3 pt-2 border-t border-slate-800/80 flex items-center justify-between text-[10px] text-slate-500 font-mono">
            <span>Atomic Event Extracted</span>
            <ArrowRight className="w-3 h-3 text-slate-400" />
          </div>
        </div>

        {/* ---------------- STAGE 2: AI SEMANTIC INTERPRETATION ---------------- */}
        <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4 flex flex-col justify-between shadow-sm relative overflow-hidden">
          <div className="absolute top-0 right-0 px-2 py-0.5 bg-amber-950 text-amber-300 border-b border-l border-amber-800 rounded-bl text-[10px] font-mono">
            STAGE 2
          </div>
          <div>
            <div className="flex items-center space-x-2 mb-2">
              <Sparkles className="w-4 h-4 text-amber-400" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                AI Semantic Match
              </h3>
            </div>

            {loadingDetail ? (
              <div className="text-xs text-slate-500 py-6 text-center">Scoring...</div>
            ) : candidateDetail ? (
              <div className="space-y-2.5 text-xs">
                {/* Matched Target Activity */}
                <div className="bg-slate-950 p-2 rounded border border-slate-800">
                  <div className="flex items-center justify-between font-mono text-[11px]">
                    <span className="font-bold text-emerald-400">{candidateDetail.activity_code}</span>
                    <span className="text-slate-500">{candidateDetail.discipline}</span>
                  </div>
                  <div className="font-medium text-slate-200 truncate mt-0.5">
                    {candidateDetail.activity_name}
                  </div>
                </div>

                {/* Score Gauge */}
                <div>
                  <div className="flex items-center justify-between text-[11px] mb-1">
                    <span className="text-slate-400">Multi-Factor Score:</span>
                    <span className="font-mono font-bold text-amber-300 text-sm">
                      {(candidateDetail.confidence_score * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
                    <div
                      className={`h-full transition-all duration-500 ${
                        candidateDetail.confidence_score >= 0.85
                          ? 'bg-emerald-500'
                          : candidateDetail.confidence_score >= 0.50
                          ? 'bg-amber-500'
                          : 'bg-red-500'
                      }`}
                      style={{ width: `${Math.min(100, candidateDetail.confidence_score * 100)}%` }}
                    />
                  </div>
                </div>

                {/* Breakdown Chips */}
                {candidateDetail.score_breakdown && (
                  <div className="grid grid-cols-3 gap-1 font-mono text-[10px] text-center">
                    <div className="bg-slate-950 p-1 rounded border border-slate-800">
                      <div className="text-slate-500">Sem (40%)</div>
                      <div className="text-slate-200">{(candidateDetail.score_breakdown.semantic * 100).toFixed(0)}%</div>
                    </div>
                    <div className="bg-slate-950 p-1 rounded border border-slate-800">
                      <div className="text-slate-500">Disc (20%)</div>
                      <div className="text-slate-200">{(candidateDetail.score_breakdown.discipline * 100).toFixed(0)}%</div>
                    </div>
                    <div className="bg-slate-950 p-1 rounded border border-slate-800">
                      <div className="text-slate-500">Loc (20%)</div>
                      <div className="text-slate-200">{(candidateDetail.score_breakdown.location * 100).toFixed(0)}%</div>
                    </div>
                  </div>
                )}

                {/* Arbitration indicator */}
                {candidateDetail.llm_reasoning && (
                  <div className="text-[10px] text-amber-300/90 bg-amber-950/30 border border-amber-900/50 p-1.5 rounded italic">
                    LLM Arbitration: {candidateDetail.llm_reasoning.slice(0, 80)}...
                  </div>
                )}
              </div>
            ) : null}
          </div>
          <div className="mt-3 pt-2 border-t border-slate-800/80 flex items-center justify-between text-[10px] text-slate-500 font-mono">
            <span>RRF + Dense + Sparse</span>
            <ArrowRight className="w-3 h-3 text-slate-400" />
          </div>
        </div>

        {/* ---------------- STAGE 3: DETERMINISTIC CONSTRAINT GATE ---------------- */}
        <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4 flex flex-col justify-between shadow-sm relative overflow-hidden">
          <div className="absolute top-0 right-0 px-2 py-0.5 bg-teal-950 text-teal-300 border-b border-l border-teal-800 rounded-bl text-[10px] font-mono">
            STAGE 3
          </div>
          <div>
            <div className="flex items-center space-x-2 mb-2">
              <ShieldAlert className="w-4 h-4 text-teal-400" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                Deterministic Constraint Gate
              </h3>
            </div>

            {loadingDetail ? (
              <div className="text-xs text-slate-500 py-6 text-center">Checking CPM graph...</div>
            ) : candidateDetail ? (
              <div className="space-y-2.5 text-xs">
                {/* Gate Status Pill */}
                <div className="flex items-center justify-between">
                  <span className="text-slate-400 text-[11px]">Validation Status:</span>
                  <span
                    className={`px-2 py-0.5 rounded text-[11px] font-mono font-bold border ${
                      candidateDetail.status === 'BLOCKED_BY_DEPENDENCY'
                        ? 'bg-red-950 text-red-400 border-red-700'
                        : candidateDetail.has_hard_violations
                        ? 'bg-red-950 text-red-400 border-red-700'
                        : candidateDetail.status === 'UNMATCHED'
                        ? 'bg-slate-800 text-slate-400 border-slate-700'
                        : 'bg-emerald-950 text-emerald-400 border-emerald-700'
                    }`}
                  >
                    {candidateDetail.status === 'BLOCKED_BY_DEPENDENCY'
                      ? 'HARD BLOCKER'
                      : candidateDetail.status === 'UNMATCHED'
                      ? 'OUT-OF-SCOPE'
                      : 'PASSED'}
                  </span>
                </div>

                {/* 4 Deterministic Rule Checks */}
                <div className="space-y-1 text-[11px] font-mono">
                  <div className="flex items-center justify-between bg-slate-950 px-2 py-1 rounded border border-slate-800">
                    <span className="text-slate-400">Predecessors (FS/SS):</span>
                    <span
                      className={
                        candidateDetail.validation_checks?.predecessor === 'PASSED'
                          ? 'text-emerald-400'
                          : 'text-red-400 font-bold'
                      }
                    >
                      {candidateDetail.validation_checks?.predecessor || 'PASSED'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between bg-slate-950 px-2 py-1 rounded border border-slate-800">
                    <span className="text-slate-400">Sequence / Calendar:</span>
                    <span
                      className={
                        candidateDetail.validation_checks?.sequence === 'PASSED'
                          ? 'text-emerald-400'
                          : 'text-amber-400'
                      }
                    >
                      {candidateDetail.validation_checks?.sequence || 'PASSED'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between bg-slate-950 px-2 py-1 rounded border border-slate-800">
                    <span className="text-slate-400">Quantity Threshold:</span>
                    <span
                      className={
                        candidateDetail.validation_checks?.quantity === 'PASSED'
                          ? 'text-emerald-400'
                          : 'text-red-400'
                      }
                    >
                      {candidateDetail.validation_checks?.quantity || 'PASSED'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between bg-slate-950 px-2 py-1 rounded border border-slate-800">
                    <span className="text-slate-400">Critical Path Impact:</span>
                    <span className="text-emerald-400 font-mono">
                      {candidateDetail.is_critical ? 'CRITICAL (0 Float)' : 'FLOAT OK'}
                    </span>
                  </div>
                </div>

                {/* Violations snippet */}
                {candidateDetail.violations && candidateDetail.violations.length > 0 && (
                  <div className="bg-red-950/40 border border-red-800/80 p-1.5 rounded text-[10px] text-red-300">
                    <div className="font-bold flex items-center space-x-1">
                      <AlertTriangle className="w-3 h-3 text-red-400" />
                      <span>{candidateDetail.violations.length} Hard Violation(s)</span>
                    </div>
                    <div className="truncate mt-0.5">{candidateDetail.violations[0].description}</div>
                  </div>
                )}
              </div>
            ) : null}
          </div>
          <div className="mt-3 pt-2 border-t border-slate-800/80 flex items-center justify-between text-[10px] text-slate-500 font-mono">
            <span>CPM Topology Verified</span>
            <ArrowRight className="w-3 h-3 text-slate-400" />
          </div>
        </div>

        {/* ---------------- STAGE 4: HUMAN AUTHORITY & SAFE MUTATION ---------------- */}
        <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4 flex flex-col justify-between shadow-sm relative overflow-hidden">
          <div className="absolute top-0 right-0 px-2 py-0.5 bg-emerald-950 text-emerald-300 border-b border-l border-emerald-800 rounded-bl text-[10px] font-mono">
            STAGE 4
          </div>
          <div>
            <div className="flex items-center space-x-2 mb-2">
              <UserCheck className="w-4 h-4 text-emerald-400" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                Human Authority & Mutation
              </h3>
            </div>

            {loadingDetail ? (
              <div className="text-xs text-slate-500 py-6 text-center">Checking authority state...</div>
            ) : candidateDetail ? (
              <div className="space-y-2 text-xs">
                {/* Current Candidate Status */}
                <div className="bg-slate-950 p-2 rounded border border-slate-800 flex items-center justify-between">
                  <span className="text-slate-400 text-[11px]">Schedule Status:</span>
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-mono font-bold ${
                      candidateDetail.is_applied
                        ? 'bg-emerald-600 text-white'
                        : candidateDetail.status === 'BLOCKED_BY_DEPENDENCY'
                        ? 'bg-red-950 text-red-300 border border-red-700'
                        : candidateDetail.status === 'REJECTED'
                        ? 'bg-slate-800 text-slate-400'
                        : 'bg-amber-950 text-amber-300 border border-amber-700'
                    }`}
                  >
                    {candidateDetail.is_applied ? 'APPLIED TO SCHEDULE' : candidateDetail.status}
                  </span>
                </div>

                {/* Optimistic Concurrency Control */}
                <div className="text-[10px] font-mono text-slate-500 flex items-center justify-between px-1">
                  <span>OCC Activity Version:</span>
                  <span className="text-slate-300">v{candidateDetail.validated_activity_version || 1}</span>
                </div>

                {/* Action Buttons */}
                {!candidateDetail.is_applied && candidateDetail.status !== 'REJECTED' ? (
                  <div className="space-y-1.5 pt-1">
                    {/* Approve Button */}
                    <button
                      onClick={handleApprove}
                      disabled={!candidateDetail.can_approve || actionLoading}
                      className={`w-full py-1.5 px-2 rounded font-semibold text-xs flex items-center justify-center space-x-1 transition ${
                        candidateDetail.can_approve && !actionLoading
                          ? 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-sm'
                          : 'bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700'
                      }`}
                    >
                      <Check className="w-3.5 h-3.5" />
                      <span>Approve & Mutate Actuals</span>
                    </button>

                    {/* Override Button (if blocked) */}
                    {candidateDetail.can_override && (
                      <button
                        onClick={() => setShowOverrideModal(true)}
                        disabled={actionLoading}
                        className="w-full py-1.5 px-2 rounded font-semibold text-xs flex items-center justify-center space-x-1 bg-amber-600 hover:bg-amber-500 text-slate-950 transition shadow-sm"
                      >
                        <ShieldAlert className="w-3.5 h-3.5" />
                        <span>Justified Override (Dir. Authority)</span>
                      </button>
                    )}

                    {/* Reassign & Reject row */}
                    <div className="grid grid-cols-2 gap-1.5">
                      <button
                        onClick={() => setShowReassignModal(true)}
                        disabled={actionLoading}
                        className="py-1 px-1.5 rounded font-medium text-[11px] bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition"
                      >
                        Reassign Activity
                      </button>
                      <button
                        onClick={() => setShowRejectModal(true)}
                        disabled={actionLoading}
                        className="py-1 px-1.5 rounded font-medium text-[11px] bg-red-950/60 hover:bg-red-900/80 text-red-300 border border-red-800 transition"
                      >
                        Reject Match
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="bg-emerald-950/40 border border-emerald-800 p-2 rounded text-[11px] text-emerald-300 text-center font-mono">
                    {candidateDetail.is_applied ? '✓ Transaction Committed to Actuals' : 'Candidate Rejected (Zero Mutation)'}
                  </div>
                )}
              </div>
            ) : null}
          </div>
          <div className="mt-3 pt-2 border-t border-slate-800/80 flex items-center justify-between text-[10px] text-slate-500 font-mono">
            <span>ScheduleUpdateService Lock</span>
            <Lock className="w-3 h-3 text-emerald-400" />
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 3. TRI-STATE COMPARISON: PLANNED BASELINE vs FIELD REALITY vs VERIFIED ACTUAL */}
      {/* ========================================================================= */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-5 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
          <div>
            <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center space-x-2">
              <Sliders className="w-4 h-4 text-emerald-400" />
              <span>Bridge Tri-State Harmonization Matrix</span>
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Strict Invariant: Planned Baseline is NEVER modified by AI or approvals. Only Actuals mutate.
            </p>
          </div>
          {activeActivity && (
            <div className="text-xs font-mono px-3 py-1 rounded bg-slate-950 border border-slate-800 text-slate-300">
              Activity: <span className="text-emerald-400 font-bold">{activeActivity.activity_code}</span> · {activeActivity.discipline}
            </div>
          )}
        </div>

        {activeActivity && candidateDetail ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs font-mono">
            {/* COLUMN 1: PLANNED BASELINE */}
            <div className="bg-slate-950 p-4 rounded-lg border border-slate-800/80 space-y-3">
              <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                <span className="font-bold text-slate-300 flex items-center space-x-1.5">
                  <FileSpreadsheet className="w-3.5 h-3.5 text-blue-400" />
                  <span>1. Planned Baseline</span>
                </span>
                <span className="text-[10px] px-1.5 py-0.2 rounded bg-blue-950 text-blue-300 border border-blue-800">
                  IMMUTABLE
                </span>
              </div>
              <div className="space-y-1.5 text-[11px]">
                <div className="flex justify-between">
                  <span className="text-slate-500">Planned Start:</span>
                  <span className="text-slate-200">{activeActivity.planned_start || '—'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Planned Finish:</span>
                  <span className="text-slate-200">{activeActivity.planned_finish || '—'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Planned Duration:</span>
                  <span className="text-slate-200">{activeActivity.planned_duration_days} days</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Planned Scope Qty:</span>
                  <span className="text-blue-400 font-bold">
                    {activeActivity.planned_quantity} {activeActivity.uom || ''}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Critical Path / Float:</span>
                  <span className={activeActivity.is_critical ? 'text-red-400' : 'text-slate-300'}>
                    {activeActivity.is_critical ? 'CRITICAL (0 Days)' : `${activeActivity.total_float_days} Days Float`}
                  </span>
                </div>
              </div>
            </div>

            {/* COLUMN 2: FIELD REPORTED REALITY */}
            <div className="bg-slate-950 p-4 rounded-lg border border-slate-800/80 space-y-3">
              <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                <span className="font-bold text-slate-300 flex items-center space-x-1.5">
                  <FileText className="w-3.5 h-3.5 text-amber-400" />
                  <span>2. Field Reality Claim</span>
                </span>
                <span className="text-[10px] px-1.5 py-0.2 rounded bg-amber-950 text-amber-300 border border-amber-800">
                  UNVERIFIED CLAIM
                </span>
              </div>
              <div className="space-y-1.5 text-[11px]">
                <div className="flex justify-between">
                  <span className="text-slate-500">Execution Date:</span>
                  <span className="text-slate-200">{candidateDetail.event_date || '—'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Claimed Quantity:</span>
                  <span className="text-amber-400 font-bold">
                    {candidateDetail.quantity_reported !== undefined && candidateDetail.quantity_reported !== null
                      ? `${candidateDetail.quantity_reported} ${candidateDetail.uom || ''}`
                      : 'None specified'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Claimed Status:</span>
                  <span className="text-slate-200">{candidateDetail.status_claim}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Chainage / Site:</span>
                  <span className="text-slate-300 truncate max-w-[120px]">
                    {candidateDetail.location_chainage || 'Corridor'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Match Confidence:</span>
                  <span className="text-amber-300 font-bold">
                    {(candidateDetail.confidence_score * 100).toFixed(1)}%
                  </span>
                </div>
              </div>
            </div>

            {/* COLUMN 3: VERIFIED ACTUAL */}
            <div className={`p-4 rounded-lg border space-y-3 ${
              candidateDetail.is_applied
                ? 'bg-emerald-950/20 border-emerald-700/80'
                : 'bg-slate-950 border-slate-800/80'
            }`}>
              <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                <span className="font-bold text-slate-300 flex items-center space-x-1.5">
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                  <span>3. Verified Schedule Actual</span>
                </span>
                <span
                  className={`text-[10px] px-1.5 py-0.2 rounded font-mono ${
                    candidateDetail.is_applied
                      ? 'bg-emerald-950 text-emerald-300 border border-emerald-700'
                      : 'bg-slate-800 text-slate-400'
                  }`}
                >
                  {candidateDetail.is_applied ? 'MUTATED & AUDITED' : 'ZERO MUTATION'}
                </span>
              </div>
              <div className="space-y-1.5 text-[11px]">
                <div className="flex justify-between">
                  <span className="text-slate-500">Actual Start:</span>
                  <span className="text-emerald-400 font-bold">
                    {activeActivity.actual_start || 'Not Started'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Actual Finish:</span>
                  <span className="text-emerald-400 font-bold">
                    {activeActivity.actual_finish || '—'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Cumulative Actual Qty:</span>
                  <span className="text-emerald-400 font-bold">
                    {activeActivity.actual_quantity} {activeActivity.uom || ''}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Physical Progress:</span>
                  <span className="text-emerald-400 font-bold text-sm">
                    {activeActivity.physical_percent_complete}%
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Version / Integrity:</span>
                  <span className="text-slate-400">
                    Version #{activeActivity.actuals_version || 1}
                  </span>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="text-xs text-slate-500 py-6 text-center">
            Select a candidate above to view the Tri-State Harmonization Matrix.
          </div>
        )}
      </div>

      {/* ========================================================================= */}
      {/* 4. MODALS: OVERRIDE, REASSIGN, REJECT */}
      {/* ========================================================================= */}
      {/* Override Modal */}
      {showOverrideModal && candidateDetail && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-lg w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center space-x-2 text-amber-400">
              <ShieldAlert className="w-5 h-5" />
              <h3 className="font-bold text-base text-white">
                Authorized Override for {candidateDetail.activity_code}
              </h3>
            </div>
            <p className="text-xs text-slate-300">
              This candidate violates deterministic schedule/predecessor rules. Under Project Director authority,
              you may apply progress provided an explicit engineering justification is recorded in the permanent audit trail.
            </p>
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">
                Mandatory Override Rationale (minimum 5 characters):
              </label>
              <textarea
                rows={3}
                value={overrideReason}
                onChange={(e) => setOverrideReason(e.target.value)}
                placeholder="e.g. Predecessor civil raft curing verified by laboratory rebound hammer testing per OIL directive."
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-xs text-slate-100 focus:outline-none focus:border-amber-500 font-sans"
              />
            </div>
            <div className="flex justify-end space-x-2 pt-2">
              <button
                onClick={() => {
                  setShowOverrideModal(false);
                  setOverrideReason('');
                }}
                className="px-3 py-1.5 rounded-lg border border-slate-700 text-slate-300 text-xs hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                onClick={handleOverride}
                disabled={overrideReason.trim().length < 5 || actionLoading}
                className="px-4 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-slate-950 text-xs font-bold transition disabled:opacity-50"
              >
                {actionLoading ? 'Applying...' : 'Confirm Override & Mutate'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reassign Modal */}
      {showReassignModal && candidateDetail && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-lg w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center space-x-2 text-teal-400">
              <CornerUpRight className="w-5 h-5" />
              <h3 className="font-bold text-base text-white">
                Reassign Progress Event Scope
              </h3>
            </div>
            <p className="text-xs text-slate-300">
              Reassignment triggers fresh deterministic validation against the target activity.
              <strong className="text-emerald-400"> Zero schedule actuals will be mutated</strong> until authorized approval.
            </p>
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">
                Select Target Schedule Activity:
              </label>
              <select
                value={targetActivityId}
                onChange={(e) => setTargetActivityId(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-xs text-slate-100 focus:outline-none focus:border-teal-500 font-mono"
              >
                <option value="">-- Choose Schedule Activity --</option>
                {activities.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.activity_code} — {a.name} ({a.discipline})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">
                Engineering Rationale for Reassignment:
              </label>
              <input
                type="text"
                value={reassignReason}
                onChange={(e) => setReassignReason(e.target.value)}
                placeholder="e.g. Corrected scope from mainline welding to HDD river crossing section."
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-xs text-slate-100 focus:outline-none focus:border-teal-500 font-sans"
              />
            </div>
            <div className="flex justify-end space-x-2 pt-2">
              <button
                onClick={() => {
                  setShowReassignModal(false);
                  setTargetActivityId('');
                  setReassignReason('');
                }}
                className="px-3 py-1.5 rounded-lg border border-slate-700 text-slate-300 text-xs hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                onClick={handleReassign}
                disabled={!targetActivityId || actionLoading}
                className="px-4 py-1.5 rounded-lg bg-teal-600 hover:bg-teal-500 text-white text-xs font-bold transition disabled:opacity-50"
              >
                {actionLoading ? 'Reassigning...' : 'Confirm Reassignment'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reject Modal */}
      {showRejectModal && candidateDetail && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-lg w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center space-x-2 text-red-400">
              <Ban className="w-5 h-5" />
              <h3 className="font-bold text-base text-white">
                Reject Match Candidate
              </h3>
            </div>
            <p className="text-xs text-slate-300">
              Mark this candidate as rejected. Zero schedule actuals will be modified.
              A permanent audit record will be logged.
            </p>
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">
                Rejection Reason:
              </label>
              <textarea
                rows={3}
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="e.g. Civil maintenance work not part of capital pipeline baseline scope."
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-xs text-slate-100 focus:outline-none focus:border-red-500 font-sans"
              />
            </div>
            <div className="flex justify-end space-x-2 pt-2">
              <button
                onClick={() => {
                  setShowRejectModal(false);
                  setRejectReason('');
                }}
                className="px-3 py-1.5 rounded-lg border border-slate-700 text-slate-300 text-xs hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                onClick={handleReject}
                disabled={!rejectReason.trim() || actionLoading}
                className="px-4 py-1.5 rounded-lg bg-red-600 hover:bg-red-500 text-white text-xs font-bold transition disabled:opacity-50"
              >
                {actionLoading ? 'Rejecting...' : 'Confirm Rejection'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
