import React, { useState, useEffect } from 'react';
import { 
  Building2, 
  FileSpreadsheet, 
  FileText, 
  UploadCloud, 
  Activity, 
  Send,
  Sparkles,
  Scale,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Layers,
  Sliders,
  BarChart2,
  Network,
  ShieldAlert,
  ShieldCheck,
  Clock,
  RefreshCw,
  Compass
} from 'lucide-react';
import { apiService } from './api/client';
import { ReviewInboxTab } from './components/ReviewInboxTab';
import { PlanningExecutionBridge } from './components/PlanningExecutionBridge';
import { 
  Project, 
  ScheduleActivity, 
  ProgressEvent, 
  SystemHealth, 
  MatchRunResponse,
  ValidationResult,
  DependencyViolation,
  DependencyGraph
} from './types';

const SAMPLE_DPR_DEFAULT = `Progress Log:
1. Excavator gang dug 620m of pipeline trench to standard 2.2m depth between Ch 08+400 and Ch 09+020.
2. Stringing crew hauled and laid out 48 joints of 16-inch API 5L X-65 pipes along ROW near Ch 07+500.
3. Mainline welding team completed 32 butt-weld joints with full root and hot pass near Ch 04+200.
4. Radiography crew inspected 28 joints using internal X-ray crawler; 27 joints accepted, 1 repair marked.
5. Civil team cast 85 cum of reinforced concrete raft for Valve Station SV-01 bund wall.`;

export function App() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>('');
  const [activeTab, setActiveTab] = useState<'bridge' | 'schedule' | 'field' | 'matching' | 'validation' | 'review'>('bridge');

  // Schedule state
  const [activities, setActivities] = useState<ScheduleActivity[]>([]);
  const [selectedDiscipline, setSelectedDiscipline] = useState<string>('ALL');
  const [uploadLoading, setUploadLoading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);

  // Field capture state
  const [rawText, setRawText] = useState(SAMPLE_DPR_DEFAULT);
  const [reporterName, setReporterName] = useState('Er. R. Baruah (Execution Lead)');
  const [reportDate, setReportDate] = useState('2026-10-28');
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const [ingestLoading, setIngestLoading] = useState(false);
  const [ingestMsg, setIngestMsg] = useState<string | null>(null);

  // Phase 2 AI Matching state
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [matchingLoading, setMatchingLoading] = useState(false);
  const [matchResult, setMatchResult] = useState<MatchRunResponse | null>(null);
  const [matchError, setMatchError] = useState<string | null>(null);
  const [scenarioLoading, setScenarioLoading] = useState<string | null>(null);

  // Phase 3 Validation state
  const [candidateValidations, setCandidateValidations] = useState<Record<string, ValidationResult>>({});
  const [validatingCandidateId, setValidatingCandidateId] = useState<string | null>(null);
  const [projectGraph, setProjectGraph] = useState<DependencyGraph | null>(null);
  const [projectViolations, setProjectViolations] = useState<DependencyViolation[]>([]);
  const [violationFilter, setViolationFilter] = useState<string>('ALL');
  const [loadingGraph, setLoadingGraph] = useState(false);
  const [loadingViolations, setLoadingViolations] = useState(false);

  // Initial load
  useEffect(() => {
    checkHealth();
    loadProjects();
  }, []);

  // Fetch activities and events when selected project changes
  useEffect(() => {
    if (selectedProjectId) {
      loadActivities(selectedProjectId, selectedDiscipline);
      loadEvents(selectedProjectId);
      if (activeTab === 'validation') {
        loadGraphAndViolations(selectedProjectId);
      }
    }
  }, [selectedProjectId, selectedDiscipline, activeTab]);

  const checkHealth = async () => {
    try {
      const data = await apiService.getHealth();
      setHealth(data);
    } catch (err) {
      console.error('Healthcheck failed', err);
      setHealth(null);
    }
  };

  const loadProjects = async () => {
    try {
      let list = await apiService.getProjects();
      if (list.length === 0) {
        const defaultProj = await apiService.createProject({
          name: 'Duliajan-Numaligarh 16-inch Crude Oil Pipeline',
          code: 'DNPL-OIL-001',
          client_name: 'Oil India Limited',
          target_start_date: '2026-10-01',
          target_finish_date: '2027-01-05',
        });
        list = [defaultProj];
      }
      setProjects(list);
      if (list.length > 0) {
        setSelectedProjectId(list[0].id);
      }
    } catch (err) {
      console.error('Failed to load projects', err);
    }
  };

  const loadActivities = async (projId: string, disc: string) => {
    try {
      const acts = await apiService.getProjectActivities(projId, disc);
      setActivities(acts);
    } catch (err) {
      console.error('Failed to load activities', err);
      setActivities([]);
    }
  };

  const loadEvents = async (projId: string) => {
    try {
      const evts = await apiService.getProgressEvents(projId);
      setEvents(evts);
      if (evts.length > 0 && !selectedEventId) {
        setSelectedEventId(evts[0].id);
      }
    } catch (err) {
      console.error('Failed to load progress events', err);
      setEvents([]);
    }
  };

  const handleCsvUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !selectedProjectId) return;

    setUploadLoading(true);
    setUploadMsg(null);
    try {
      const res = await apiService.uploadScheduleCsv(selectedProjectId, file);
      setUploadMsg(`Successfully imported ${res.activities_imported} activities.`);
      loadActivities(selectedProjectId, selectedDiscipline);
      if (activeTab === 'validation') {
        loadGraphAndViolations(selectedProjectId);
      }
    } catch (err: any) {
      setUploadMsg(`Upload failed: ${err.response?.data?.detail || err.message}`);
    } finally {
      setUploadLoading(false);
      e.target.value = '';
    }
  };

  const handleFieldSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rawText.trim() || !selectedProjectId) return;

    setIngestLoading(true);
    setIngestMsg(null);
    try {
      const report = await apiService.submitRawReport({
        project_id: selectedProjectId,
        raw_text: rawText,
        reporter_name: reporterName,
        report_date: reportDate,
      });
      setIngestMsg(`Extracted ${report.events?.length || 0} discrete progress events.`);
      await loadEvents(selectedProjectId);
      if (report.events && report.events.length > 0) {
        setSelectedEventId(report.events[0].id);
      }
    } catch (err: any) {
      setIngestMsg(`Submission failed: ${err.response?.data?.detail || err.message}`);
    } finally {
      setIngestLoading(false);
    }
  };

  const runMatching = async (eventId: string) => {
    setMatchingLoading(true);
    setMatchError(null);
    try {
      const res = await apiService.runEventMatching(eventId, 5);
      setMatchResult(res);

      // Concurrently run deterministic validation for candidates
      const validations: Record<string, ValidationResult> = {};
      await Promise.all(
        res.candidates.map(async (cand) => {
          if (cand.candidate_id) {
            try {
              const vRes = await apiService.validateCandidate(cand.candidate_id);
              validations[cand.candidate_id] = vRes;
            } catch (err) {
              console.warn(`Validation failed for candidate ${cand.candidate_id}:`, err);
            }
          }
        })
      );
      setCandidateValidations(validations);
    } catch (err: any) {
      setMatchError(err.response?.data?.detail || err.message || 'Matching failed');
      setMatchResult(null);
    } finally {
      setMatchingLoading(false);
    }
  };

  const validateCandidateAction = async (candidateId: string) => {
    setValidatingCandidateId(candidateId);
    try {
      const vRes = await apiService.validateCandidate(candidateId);
      setCandidateValidations((prev) => ({ ...prev, [candidateId]: vRes }));
    } catch (err: any) {
      console.error('Validation action failed', err);
    } finally {
      setValidatingCandidateId(null);
    }
  };

  const loadGraphAndViolations = async (projId: string) => {
    setLoadingGraph(true);
    setLoadingViolations(true);
    try {
      const graph = await apiService.getProjectGraph(projId);
      setProjectGraph(graph);
    } catch (err) {
      console.error('Failed to load project graph', err);
      setProjectGraph(null);
    } finally {
      setLoadingGraph(false);
    }

    try {
      const viols = await apiService.getProjectViolations(projId);
      setProjectViolations(viols);
    } catch (err) {
      console.error('Failed to load violations', err);
      setProjectViolations([]);
    } finally {
      setLoadingViolations(false);
    }
  };

  const handleQuickMatchFromTable = (eventId: string) => {
    setSelectedEventId(eventId);
    setActiveTab('matching');
    runMatching(eventId);
  };

  // Demo Scenario Launcher
  const handleLaunchScenario = async (scenario: 'A' | 'A2' | 'B' | 'C' | 'D') => {
    if (!selectedProjectId) return;
    setScenarioLoading(scenario);
    setMatchError(null);

    let text = '';
    let repName = 'Er. Baruah (Lead Engineer)';
    let repDate = '2026-11-15';

    if (scenario === 'A') {
      text = 'Spool erection for Line 24 near Pump House completed today at SV-01.';
      repDate = '2026-11-15';
    } else if (scenario === 'A2') {
      text = 'Valve station 01 manifold piping and actuator mounting completed today at SV-01.';
      repDate = '2026-11-15';
    } else if (scenario === 'B') {
      text = 'Pipeline welding completed near the crossing.';
      repDate = '2026-11-05';
    } else if (scenario === 'D') {
      text = 'Mainline trenching gang completed 4500m of trench excavation between Ch 00+000 and Ch 03+500.';
      repDate = '2026-10-18';
    } else {
      text = 'Security gate painting completed.';
      repDate = '2026-11-01';
    }

    try {
      const report = await apiService.submitRawReport({
        project_id: selectedProjectId,
        raw_text: text,
        reporter_name: repName,
        report_date: repDate,
      });

      await loadEvents(selectedProjectId);

      if (report.events && report.events.length > 0) {
        const newEvtId = report.events[0].id;
        setSelectedEventId(newEvtId);
        setActiveTab('matching');
        await runMatching(newEvtId);
      }
    } catch (err: any) {
      setMatchError(`Failed to load scenario ${scenario}: ${err.message}`);
    } finally {
      setScenarioLoading(null);
    }
  };

  const selectedProject = projects.find((p) => p.id === selectedProjectId);
  const activeEvent = events.find((e) => e.id === selectedEventId) || events[0];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Top Navigation Bar */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="h-10 w-10 rounded-lg bg-gradient-to-tr from-emerald-600 to-teal-400 flex items-center justify-center font-bold text-slate-950 text-xl shadow-lg shadow-emerald-900/30">
              Ψ
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-extrabold text-lg tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-emerald-400 to-teal-200">
                  ProjectSynapse
                </span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-800 font-mono">
                  SIH26122
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Oil India Limited · Planning-to-Execution Bridge & AI Semantic Matcher
              </p>
            </div>
          </div>

          {/* Project Selector & System Health */}
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2 bg-slate-800/70 border border-slate-700 px-3 py-1.5 rounded-lg text-xs">
              <Building2 className="w-3.5 h-3.5 text-slate-400" />
              <select
                value={selectedProjectId}
                onChange={(e) => setSelectedProjectId(e.target.value)}
                className="bg-transparent font-medium text-slate-200 focus:outline-none cursor-pointer"
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.id} className="bg-slate-900 text-slate-100">
                    {p.name} ({p.code})
                  </option>
                ))}
              </select>
            </div>

            {/* Health Badge */}
            <div className="flex items-center space-x-1.5 text-xs bg-slate-800/70 border border-slate-700 px-2.5 py-1.5 rounded-lg">
              <span
                className={`w-2 h-2 rounded-full ${
                  health?.status === 'healthy' ? 'bg-emerald-400 animate-pulse' : 'bg-red-400'
                }`}
              />
              <span className="text-slate-300 font-mono">
                {health?.status === 'healthy' ? `API: Online (${health.ai_provider})` : 'API: Offline'}
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 flex-1 w-full space-y-6">
        {/* Project Header Banner & Tabs */}
        <div className="bg-gradient-to-r from-slate-900 via-slate-900 to-emerald-950/40 border border-slate-800 rounded-xl p-5 shadow-sm">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <div className="flex items-center space-x-2">
                <h1 className="text-xl font-bold text-white">
                  {selectedProject ? selectedProject.name : 'Pipeline Project'}
                </h1>
                <span className="text-xs font-mono bg-slate-800 text-slate-300 px-2 py-0.5 rounded border border-slate-700">
                  {selectedProject?.code}
                </span>
              </div>
              <p className="text-sm text-slate-400 mt-1">
                Client: <span className="text-emerald-400 font-medium">Oil India Limited</span> · Phase 5: SIH 2026 Final Product & Planning-to-Execution Bridge
              </p>
            </div>

            {/* Tabs */}
            <div className="flex items-center bg-slate-950 p-1 rounded-lg border border-slate-800 self-start sm:self-auto space-x-1">
              <button
                onClick={() => setActiveTab('bridge')}
                className={`flex items-center space-x-2 px-3.5 py-2 rounded-md text-xs font-medium transition ${
                  activeTab === 'bridge'
                    ? 'bg-emerald-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Compass className="w-3.5 h-3.5 text-teal-300" />
                <span>Execution Bridge</span>
              </button>
              <button
                onClick={() => setActiveTab('schedule')}
                className={`flex items-center space-x-2 px-3.5 py-2 rounded-md text-xs font-medium transition ${
                  activeTab === 'schedule'
                    ? 'bg-emerald-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <FileSpreadsheet className="w-3.5 h-3.5" />
                <span>Master Schedule ({activities.length})</span>
              </button>
              <button
                onClick={() => setActiveTab('field')}
                className={`flex items-center space-x-2 px-3.5 py-2 rounded-md text-xs font-medium transition ${
                  activeTab === 'field'
                    ? 'bg-emerald-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <FileText className="w-3.5 h-3.5" />
                <span>Field Ingestion ({events.length})</span>
              </button>
              <button
                onClick={() => {
                  setActiveTab('matching');
                  if (activeEvent && !matchResult) {
                    runMatching(activeEvent.id);
                  }
                }}
                className={`flex items-center space-x-2 px-3.5 py-2 rounded-md text-xs font-medium transition ${
                  activeTab === 'matching'
                    ? 'bg-emerald-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Sparkles className="w-3.5 h-3.5 text-amber-300" />
                <span>AI Matching Engine</span>
              </button>
              <button
                onClick={() => {
                  setActiveTab('validation');
                  if (selectedProjectId) {
                    loadGraphAndViolations(selectedProjectId);
                  }
                }}
                className={`flex items-center space-x-2 px-3.5 py-2 rounded-md text-xs font-medium transition ${
                  activeTab === 'validation'
                    ? 'bg-emerald-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Network className="w-3.5 h-3.5 text-teal-300" />
                <span>Dependency Validator</span>
              </button>
              <button
                onClick={() => setActiveTab('review')}
                className={`flex items-center space-x-2 px-3.5 py-2 rounded-md text-xs font-medium transition ${
                  activeTab === 'review'
                    ? 'bg-emerald-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-300" />
                <span>Review & Approval</span>
              </button>
            </div>
          </div>
        </div>

        {/* ========================================================================= */}
        {/* TAB 0: PLANNING -> EXECUTION BRIDGE (PHASE 5) */}
        {/* ========================================================================= */}
        {activeTab === 'bridge' && selectedProjectId && (
          <PlanningExecutionBridge
            projectId={selectedProjectId}
            activities={activities}
            onScheduleUpdated={() => {
              if (selectedProjectId) {
                loadActivities(selectedProjectId, selectedDiscipline);
              }
            }}
            onNavigateToTab={(tab) => setActiveTab(tab)}
          />
        )}

        {/* ========================================================================= */}
        {/* TAB 1: MASTER SCHEDULE */}
        {/* ========================================================================= */}
        {activeTab === 'schedule' && (
          <div className="space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-slate-900/60 p-4 rounded-xl border border-slate-800">
              <div className="flex items-center space-x-3">
                <label className="flex items-center space-x-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold px-4 py-2 rounded-lg cursor-pointer transition shadow-sm">
                  <UploadCloud className="w-4 h-4" />
                  <span>{uploadLoading ? 'Importing...' : 'Upload Schedule CSV'}</span>
                  <input
                    type="file"
                    accept=".csv"
                    onChange={handleCsvUpload}
                    disabled={uploadLoading}
                    className="hidden"
                  />
                </label>
                {uploadMsg && (
                  <span className="text-xs text-emerald-400 font-medium">{uploadMsg}</span>
                )}
              </div>

              {/* Discipline Filters */}
              <div className="flex items-center space-x-2">
                <span className="text-xs text-slate-400">Discipline:</span>
                {['ALL', 'CIVIL', 'PIPING', 'MECHANICAL', 'ELECTRICAL'].map((d) => (
                  <button
                    key={d}
                    onClick={() => setSelectedDiscipline(d)}
                    className={`text-xs px-2.5 py-1 rounded-md transition ${
                      selectedDiscipline === d
                        ? 'bg-emerald-950 text-emerald-300 border border-emerald-700 font-semibold'
                        : 'bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-700'
                    }`}
                  >
                    {d}
                  </button>
                ))}
              </div>
            </div>

            {/* Activities Table */}
            <div className="bg-slate-900/80 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-950 text-slate-400 uppercase tracking-wider font-semibold border-b border-slate-800">
                    <tr>
                      <th className="py-3 px-4">Activity Code</th>
                      <th className="py-3 px-4">Name</th>
                      <th className="py-3 px-4">Discipline</th>
                      <th className="py-3 px-4">Location Scope</th>
                      <th className="py-3 px-4">Planned Window</th>
                      <th className="py-3 px-4 text-right">Scope Qty</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-sans">
                    {activities.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="py-8 text-center text-slate-500">
                          No activities found. Upload a schedule CSV or select another discipline.
                        </td>
                      </tr>
                    ) : (
                      activities.map((act) => (
                        <tr key={act.id} className="hover:bg-slate-800/40 transition">
                          <td className="py-3 px-4 font-mono font-bold text-emerald-400">
                            {act.activity_code}
                          </td>
                          <td className="py-3 px-4 font-medium text-slate-100">
                            {act.name}
                            {act.wbs_name && (
                              <span className="block text-[10px] text-slate-400">{act.wbs_name}</span>
                            )}
                          </td>
                          <td className="py-3 px-4">
                            <span className="text-[10px] px-2 py-0.5 rounded-full font-medium bg-slate-800 text-slate-300 border border-slate-700">
                              {act.discipline}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-slate-300 font-mono text-[11px]">
                            {act.location_scope || 'Corridor'}
                          </td>
                          <td className="py-3 px-4 text-slate-400 font-mono text-[11px]">
                            {act.planned_start} → {act.planned_finish}
                          </td>
                          <td className="py-3 px-4 text-right font-mono font-semibold text-slate-200">
                            {act.planned_quantity.toLocaleString()} {act.uom || ''}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 2: FIELD INGESTION */}
        {/* ========================================================================= */}
        {activeTab === 'field' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <div className="lg:col-span-5 bg-slate-900/80 border border-slate-800 rounded-xl p-5 space-y-4 shadow-sm">
              <div className="flex items-center space-x-2 border-b border-slate-800 pb-3">
                <FileText className="w-4 h-4 text-emerald-400" />
                <h2 className="font-semibold text-sm text-slate-100">Daily Progress Report Ingestion</h2>
              </div>

              <form onSubmit={handleFieldSubmit} className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Reporter Name</label>
                    <input
                      type="text"
                      value={reporterName}
                      onChange={(e) => setReporterName(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-100 focus:outline-none focus:border-emerald-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Report Date</label>
                    <input
                      type="date"
                      value={reportDate}
                      onChange={(e) => setReportDate(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-100 focus:outline-none focus:border-emerald-500"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs text-slate-400 mb-1">
                    Unstructured Field Progress Notes
                  </label>
                  <textarea
                    rows={8}
                    value={rawText}
                    onChange={(e) => setRawText(e.target.value)}
                    placeholder="Enter site engineer notes or paste DPR shift logs..."
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg p-3 text-xs text-slate-100 font-mono focus:outline-none focus:border-emerald-500 leading-relaxed"
                  />
                </div>

                <div className="flex items-center justify-between pt-1">
                  <button
                    type="submit"
                    disabled={ingestLoading}
                    className="flex items-center space-x-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-semibold px-4 py-2 rounded-lg transition shadow-sm"
                  >
                    <Send className="w-3.5 h-3.5" />
                    <span>{ingestLoading ? 'Extracting Events...' : 'Extract Progress Events'}</span>
                  </button>
                  {ingestMsg && (
                    <span className="text-xs text-emerald-400 font-medium">{ingestMsg}</span>
                  )}
                </div>
              </form>
            </div>

            <div className="lg:col-span-7 bg-slate-900/80 border border-slate-800 rounded-xl p-5 space-y-4 shadow-sm">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <div className="flex items-center space-x-2">
                  <Activity className="w-4 h-4 text-emerald-400" />
                  <h2 className="font-semibold text-sm text-slate-100">
                    Extracted Progress Events ({events.length})
                  </h2>
                </div>
                <span className="text-xs text-slate-400 font-mono">
                  Normalized Event Candidates
                </span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-950 text-slate-400 uppercase tracking-wider font-semibold border-b border-slate-800">
                    <tr>
                      <th className="py-2.5 px-3">Work Description</th>
                      <th className="py-2.5 px-3">Trade</th>
                      <th className="py-2.5 px-3">Location</th>
                      <th className="py-2.5 px-3">Quantity</th>
                      <th className="py-2.5 px-3 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-sans">
                    {events.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="py-8 text-center text-slate-500">
                          No progress events extracted yet. Submit field notes on the left.
                        </td>
                      </tr>
                    ) : (
                      events.map((evt) => (
                        <tr key={evt.id} className="hover:bg-slate-800/40 transition">
                          <td className="py-2.5 px-3">
                            <div className="font-medium text-slate-100">{evt.work_description}</div>
                            <div className="text-[10px] text-slate-400 font-mono italic truncate max-w-xs">
                              "{evt.raw_text_snippet}"
                            </div>
                          </td>
                          <td className="py-2.5 px-3">
                            <span className="text-[10px] px-2 py-0.5 rounded-full font-medium bg-slate-800 text-slate-300 border border-slate-700">
                              {evt.discipline}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 font-mono text-[11px] text-emerald-400">
                            {evt.location_chainage || '—'}
                          </td>
                          <td className="py-2.5 px-3 font-mono font-semibold text-slate-200">
                            {evt.quantity_reported !== null ? `${evt.quantity_reported} ${evt.uom || ''}` : '—'}
                          </td>
                          <td className="py-2.5 px-3 text-right">
                            <button
                              onClick={() => handleQuickMatchFromTable(evt.id)}
                              className="inline-flex items-center space-x-1 bg-emerald-950 hover:bg-emerald-900 text-emerald-300 border border-emerald-700 text-[11px] font-semibold px-2.5 py-1 rounded transition"
                            >
                              <Sparkles className="w-3 h-3 text-amber-300" />
                              <span>Match ⚡</span>
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 3: AI MATCHING ENGINE (PHASE 2) */}
        {/* ========================================================================= */}
        {activeTab === 'matching' && (
          <div className="space-y-6">
            {/* Quick Demo Scenarios Bar */}
            <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-3">
              <div>
                <span className="text-xs font-semibold text-slate-200 uppercase tracking-wider block">
                  Quick Benchmark Scenarios (OIL Field DPRs & Validation)
                </span>
                <span className="text-xs text-slate-400">
                  Instant evaluation of semantic matching, arbitration, predecessor blocking, and quantity overrun rules.
                </span>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={() => handleLaunchScenario('A')}
                  disabled={scenarioLoading !== null}
                  className="flex items-center space-x-1.5 text-xs bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-700 px-3 py-1.5 rounded-lg transition disabled:opacity-50"
                >
                  <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                  <span className="font-medium">
                    {scenarioLoading === 'A' ? 'Loading...' : 'Scenario A: Review (Spool)'}
                  </span>
                </button>

                <button
                  onClick={() => handleLaunchScenario('A2')}
                  disabled={scenarioLoading !== null}
                  className="flex items-center space-x-1.5 text-xs bg-rose-950/80 hover:bg-rose-900 text-rose-300 border border-rose-700 px-3 py-1.5 rounded-lg transition disabled:opacity-50"
                  title="Matches ACT-5020 with 96% confidence, but ACT-5010 incomplete -> BLOCKED BY DEPENDENCY"
                >
                  <span className="w-2 h-2 rounded-full bg-rose-400 animate-ping"></span>
                  <span className="font-medium">
                    {scenarioLoading === 'A2' ? 'Loading...' : 'Scenario A2: Blocked (Predecessor Incomplete)'}
                  </span>
                </button>

                <button
                  onClick={() => handleLaunchScenario('B')}
                  disabled={scenarioLoading !== null}
                  className="flex items-center space-x-1.5 text-xs bg-amber-950/80 hover:bg-amber-900 text-amber-300 border border-amber-700 px-3 py-1.5 rounded-lg transition disabled:opacity-50"
                >
                  <span className="w-2 h-2 rounded-full bg-amber-400"></span>
                  <span className="font-medium">
                    {scenarioLoading === 'B' ? 'Loading...' : 'Scenario B: Ambiguous (Welding)'}
                  </span>
                </button>

                <button
                  onClick={() => handleLaunchScenario('D')}
                  disabled={scenarioLoading !== null}
                  className="flex items-center space-x-1.5 text-xs bg-purple-950/80 hover:bg-purple-900 text-purple-300 border border-purple-700 px-3 py-1.5 rounded-lg transition disabled:opacity-50"
                  title="Reports 4500m vs 3500m planned -> QUANTITY OVERRUN > 15%"
                >
                  <span className="w-2 h-2 rounded-full bg-purple-400"></span>
                  <span className="font-medium">
                    {scenarioLoading === 'D' ? 'Loading...' : 'Scenario D: Overrun (>15%)'}
                  </span>
                </button>

                <button
                  onClick={() => handleLaunchScenario('C')}
                  disabled={scenarioLoading !== null}
                  className="flex items-center space-x-1.5 text-xs bg-slate-900 hover:bg-slate-800 text-slate-400 border border-slate-700 px-3 py-1.5 rounded-lg transition disabled:opacity-50"
                >
                  <span className="w-2 h-2 rounded-full bg-slate-500"></span>
                  <span className="font-medium">
                    {scenarioLoading === 'C' ? 'Loading...' : 'Scenario C: Unmatched (Gate)'}
                  </span>
                </button>
              </div>
            </div>

            {/* Split Screen Workspace */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              {/* Left Column: Event Selector & Context (4 cols) */}
              <div className="lg:col-span-4 space-y-4">
                <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 space-y-3">
                  <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                    <div className="flex items-center space-x-2">
                      <Layers className="w-4 h-4 text-emerald-400" />
                      <h3 className="text-xs font-semibold text-slate-200 uppercase tracking-wider">
                        Select Field Event ({events.length})
                      </h3>
                    </div>
                  </div>

                  {events.length === 0 ? (
                    <div className="text-center py-6 text-xs text-slate-500">
                      No events available. Ingest a field report or run a quick benchmark above.
                    </div>
                  ) : (
                    <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                      {events.map((evt) => {
                        const isSelected = evt.id === (activeEvent ? activeEvent.id : '');
                        return (
                          <div
                            key={evt.id}
                            onClick={() => {
                              setSelectedEventId(evt.id);
                              runMatching(evt.id);
                            }}
                            className={`p-2.5 rounded-lg border text-xs cursor-pointer transition ${
                              isSelected
                                ? 'bg-emerald-950/50 border-emerald-600 text-slate-100 shadow-sm'
                                : 'bg-slate-950/60 border-slate-800 text-slate-300 hover:border-slate-700'
                            }`}
                          >
                            <div className="flex items-center justify-between">
                              <span className="font-medium text-slate-100 truncate max-w-[180px]">
                                {evt.work_description}
                              </span>
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
                                {evt.discipline}
                              </span>
                            </div>
                            <div className="text-[10px] text-slate-400 mt-1 truncate italic">
                              "{evt.raw_text_snippet}"
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* Selected Event Detail Card */}
                {activeEvent && (
                  <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 space-y-3">
                    <div className="flex items-center space-x-2 border-b border-slate-800 pb-2">
                      <Sliders className="w-4 h-4 text-emerald-400" />
                      <h3 className="text-xs font-semibold text-slate-200 uppercase tracking-wider">
                        Active Event Parameters
                      </h3>
                    </div>

                    <div className="space-y-2 text-xs">
                      <div>
                        <span className="text-slate-400 block text-[11px]">Normalized Operation:</span>
                        <span className="font-medium text-slate-100">{activeEvent.work_description}</span>
                      </div>

                      <div>
                        <span className="text-slate-400 block text-[11px]">Original DPR Snippet:</span>
                        <div className="p-2 rounded bg-slate-950 border border-slate-800 font-mono text-[11px] text-slate-300 italic">
                          "{activeEvent.raw_text_snippet}"
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-2 pt-1 font-mono text-[11px]">
                        <div className="bg-slate-950/70 p-2 rounded border border-slate-800">
                          <span className="text-slate-400 block text-[10px]">Trade / Discipline</span>
                          <span className="font-semibold text-emerald-400">{activeEvent.discipline}</span>
                        </div>
                        <div className="bg-slate-950/70 p-2 rounded border border-slate-800">
                          <span className="text-slate-400 block text-[10px]">Location Chainage</span>
                          <span className="font-semibold text-teal-300">{activeEvent.location_chainage || 'Corridor'}</span>
                        </div>
                        <div className="bg-slate-950/70 p-2 rounded border border-slate-800">
                          <span className="text-slate-400 block text-[10px]">Quantity Claim</span>
                          <span className="font-semibold text-slate-200">
                            {activeEvent.quantity_reported !== null ? `${activeEvent.quantity_reported} ${activeEvent.uom || ''}` : 'Milestone'}
                          </span>
                        </div>
                        <div className="bg-slate-950/70 p-2 rounded border border-slate-800">
                          <span className="text-slate-400 block text-[10px]">Execution Date</span>
                          <span className="font-semibold text-slate-300">{activeEvent.event_date || 'Current'}</span>
                        </div>
                      </div>
                    </div>

                    <button
                      onClick={() => runMatching(activeEvent.id)}
                      disabled={matchingLoading}
                      className="w-full flex items-center justify-center space-x-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-semibold py-2.5 rounded-lg transition shadow-md shadow-emerald-950/40"
                    >
                      <Sparkles className="w-4 h-4 text-amber-300" />
                      <span>{matchingLoading ? 'Calculating Composite Scores...' : 'Run Semantic Match Engine ⚡'}</span>
                    </button>
                  </div>
                )}
              </div>

              {/* Right Column: Ranked Candidates & Explainability (8 cols) */}
              <div className="lg:col-span-8 space-y-4">
                {matchError && (
                  <div className="p-4 rounded-xl bg-rose-950/50 border border-rose-800 text-rose-300 text-xs flex items-center space-x-2">
                    <XCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
                    <span>{matchError}</span>
                  </div>
                )}

                {matchingLoading ? (
                  <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-12 text-center space-y-3">
                    <div className="w-10 h-10 rounded-full border-2 border-emerald-500 border-t-transparent animate-spin mx-auto"></div>
                    <div className="text-sm font-medium text-slate-200">
                      Executing Planning-to-Execution Matching...
                    </div>
                    <p className="text-xs text-slate-400 max-w-md mx-auto">
                      Running hybrid retrieval (BM25 sparse + 768-dim dense cosine via RRF), 5-factor confidence scoring, and close-candidate arbitration.
                    </p>
                  </div>
                ) : !matchResult ? (
                  <div className="bg-slate-900/40 border border-dashed border-slate-800 rounded-xl p-12 text-center space-y-3">
                    <BarChart2 className="w-10 h-10 text-slate-600 mx-auto" />
                    <div className="text-sm font-medium text-slate-300">
                      No Match Run Selected
                    </div>
                    <p className="text-xs text-slate-500 max-w-md mx-auto">
                      Select a progress event on the left or launch a benchmark scenario above to view ranked schedule candidates, confidence gauges, and explainability breakdowns.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {/* Decision Overview Header */}
                    <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-sm space-y-3">
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-3">
                        <div className="flex items-center space-x-3">
                          <span
                            className={`text-xs px-3 py-1 rounded-full font-bold uppercase tracking-wider flex items-center space-x-1.5 ${
                              matchResult.top_decision === 'AUTO_MATCHED'
                                ? 'bg-emerald-950 text-emerald-300 border border-emerald-700'
                                : matchResult.top_decision === 'NEEDS_REVIEW'
                                ? 'bg-amber-950 text-amber-300 border border-amber-700'
                                : 'bg-rose-950 text-rose-300 border border-rose-700'
                            }`}
                          >
                            {matchResult.top_decision === 'AUTO_MATCHED' && <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />}
                            {matchResult.top_decision === 'NEEDS_REVIEW' && <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />}
                            {matchResult.top_decision === 'UNMATCHED' && <XCircle className="w-3.5 h-3.5 text-rose-400" />}
                            <span>{matchResult.top_decision.replace('_', ' ')}</span>
                          </span>

                          <span className="text-xs text-slate-400 font-mono">
                            {matchResult.candidates.length} Candidate Activities Ranked
                          </span>
                        </div>

                        {matchResult.candidates[0] && (
                          <div className="flex items-center space-x-2">
                            <span className="text-xs text-slate-400">Composite Confidence:</span>
                            <span className="text-lg font-bold font-mono text-emerald-400">
                              {(matchResult.candidates[0].confidence_score * 100).toFixed(1)}%
                            </span>
                          </div>
                        )}
                      </div>

                      {/* Close Candidate Arbitration Alert */}
                      {matchResult.arbitration_applied && (
                        <div className="p-3.5 rounded-lg bg-amber-950/40 border border-amber-800/80 flex items-start space-x-3">
                          <Scale className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
                          <div className="text-xs space-y-1">
                            <div className="font-semibold text-amber-200">
                              Close Candidate Arbitration Applied (Margin &lt; 0.15)
                            </div>
                            <div className="text-amber-300/90 leading-relaxed font-sans">
                              {matchResult.arbitration_reasoning || 'Competing activities with close score proximity flagged for human review.'}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Ranked Candidates Cards */}
                    <div className="space-y-3">
                      {matchResult.candidates.map((cand, idx) => {
                        const scorePct = Math.round(cand.confidence_score * 100);
                        const b = cand.score_breakdown;

                        return (
                          <div
                            key={cand.activity_id}
                            className={`p-4 rounded-xl border transition ${
                              idx === 0
                                ? 'bg-slate-900 border-slate-700 shadow-md'
                                : 'bg-slate-900/50 border-slate-800/80 opacity-90'
                            }`}
                          >
                            {/* Card Top Row */}
                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800/80 pb-3">
                              <div className="flex items-start space-x-3">
                                <span className={`text-xs font-mono font-bold px-2 py-1 rounded ${
                                  idx === 0 ? 'bg-emerald-950 text-emerald-300 border border-emerald-700' : 'bg-slate-800 text-slate-400'
                                }`}>
                                  #{cand.ranking}
                                </span>
                                <div>
                                  <div className="flex items-center space-x-2">
                                    <span className="font-mono font-bold text-sm text-emerald-400">
                                      {cand.activity_code}
                                    </span>
                                    <span className="font-semibold text-sm text-slate-100">
                                      {cand.activity_name}
                                    </span>
                                  </div>
                                  <div className="text-[11px] text-slate-400 flex items-center space-x-2 mt-0.5">
                                    <span>WBS: {cand.wbs_name || cand.wbs_code || 'General'}</span>
                                    <span>·</span>
                                    <span>Corridor: {cand.location_scope || 'Corridor'}</span>
                                  </div>
                                </div>
                              </div>

                              <div className="flex items-center space-x-3 self-end sm:self-auto">
                                <div className="text-right">
                                  <div className="text-xs text-slate-400">Confidence Score</div>
                                  <div className="text-base font-bold font-mono text-emerald-400">
                                    {scorePct}%
                                  </div>
                                </div>
                                <span
                                  className={`text-[10px] px-2 py-0.5 rounded font-semibold uppercase ${
                                    cand.decision_status === 'AUTO_MATCHED'
                                      ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                                      : cand.decision_status === 'NEEDS_REVIEW'
                                      ? 'bg-amber-950 text-amber-300 border border-amber-800'
                                      : 'bg-rose-950 text-rose-300 border border-rose-800'
                                  }`}
                                >
                                  {cand.decision_status.replace('_', ' ')}
                                </span>
                              </div>
                            </div>

                            {/* 5-Factor Score Breakdown Progress Bars */}
                            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 pt-3">
                              <div className="bg-slate-950/60 p-2 rounded border border-slate-800/80">
                                <div className="flex justify-between text-[10px] text-slate-400 mb-1">
                                  <span>Semantic (40%)</span>
                                  <span className="font-mono text-slate-200">{(b.semantic * 100).toFixed(0)}%</span>
                                </div>
                                <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                                  <div className="h-full bg-emerald-400 rounded-full" style={{ width: `${b.semantic * 100}%` }}></div>
                                </div>
                              </div>

                              <div className="bg-slate-950/60 p-2 rounded border border-slate-800/80">
                                <div className="flex justify-between text-[10px] text-slate-400 mb-1">
                                  <span>Trade (20%)</span>
                                  <span className="font-mono text-slate-200">{(b.discipline * 100).toFixed(0)}%</span>
                                </div>
                                <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                                  <div className="h-full bg-teal-400 rounded-full" style={{ width: `${b.discipline * 100}%` }}></div>
                                </div>
                              </div>

                              <div className="bg-slate-950/60 p-2 rounded border border-slate-800/80">
                                <div className="flex justify-between text-[10px] text-slate-400 mb-1">
                                  <span>Location (20%)</span>
                                  <span className="font-mono text-slate-200">{(b.location * 100).toFixed(0)}%</span>
                                </div>
                                <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                                  <div className="h-full bg-cyan-400 rounded-full" style={{ width: `${b.location * 100}%` }}></div>
                                </div>
                              </div>

                              <div className="bg-slate-950/60 p-2 rounded border border-slate-800/80">
                                <div className="flex justify-between text-[10px] text-slate-400 mb-1">
                                  <span>Quantity (10%)</span>
                                  <span className="font-mono text-slate-200">{(b.quantity * 100).toFixed(0)}%</span>
                                </div>
                                <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                                  <div className="h-full bg-blue-400 rounded-full" style={{ width: `${b.quantity * 100}%` }}></div>
                                </div>
                              </div>

                              <div className="bg-slate-950/60 p-2 rounded border border-slate-800/80">
                                <div className="flex justify-between text-[10px] text-slate-400 mb-1">
                                  <span>Window (10%)</span>
                                  <span className="font-mono text-slate-200">{(b.temporal * 100).toFixed(0)}%</span>
                                </div>
                                <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                                  <div className="h-full bg-indigo-400 rounded-full" style={{ width: `${b.temporal * 100}%` }}></div>
                                </div>
                              </div>
                            </div>

                            {/* Explainability Evidence & Warnings */}
                            <div className="mt-3 pt-3 border-t border-slate-800/80 space-y-1.5 text-xs">
                              {cand.matching_reasons.length > 0 && (
                                <div className="space-y-1">
                                  {cand.matching_reasons.map((r, i) => (
                                    <div key={i} className="flex items-center space-x-1.5 text-emerald-400 text-[11px]">
                                      <CheckCircle2 className="w-3 h-3 flex-shrink-0" />
                                      <span>{r}</span>
                                    </div>
                                  ))}
                                </div>
                              )}

                              {cand.mismatch_reasons.length > 0 && (
                                <div className="space-y-1">
                                  {cand.mismatch_reasons.map((m, i) => (
                                    <div key={i} className="flex items-center space-x-1.5 text-amber-400 text-[11px]">
                                      <AlertTriangle className="w-3 h-3 flex-shrink-0" />
                                      <span>{m}</span>
                                    </div>
                                  ))}
                                </div>
                              )}

                              {cand.llm_reasoning && (
                                <div className="p-2 rounded bg-slate-950 border border-slate-800 text-[11px] text-slate-300 font-mono">
                                  {cand.llm_reasoning}
                                </div>
                              )}

                              {/* Phase 3 Deterministic Dependency & Schedule Validation */}
                              {cand.candidate_id && candidateValidations[cand.candidate_id] ? (
                                (() => {
                                  const val = candidateValidations[cand.candidate_id!];
                                  const isBlocked = val.final_decision === 'BLOCKED_BY_DEPENDENCY';
                                  const isHard = val.has_hard_violations;
                                  const isSoft = val.has_soft_warnings;

                                  return (
                                    <div className={`mt-3 pt-3 border-t rounded-lg p-3 text-xs ${
                                      isBlocked || isHard
                                        ? 'bg-rose-950/30 border-rose-900/60'
                                        : isSoft
                                        ? 'bg-amber-950/30 border-amber-900/60'
                                        : 'bg-emerald-950/30 border-emerald-900/60'
                                    }`}>
                                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b pb-2 border-slate-800">
                                        <div className="flex items-center space-x-2">
                                          {isBlocked ? (
                                            <ShieldAlert className="w-4 h-4 text-rose-400 flex-shrink-0" />
                                          ) : isHard ? (
                                            <ShieldAlert className="w-4 h-4 text-rose-400 flex-shrink-0" />
                                          ) : isSoft ? (
                                            <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />
                                          ) : (
                                            <ShieldCheck className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                                          )}
                                          <span className="font-semibold text-slate-200 uppercase tracking-wider text-[11px]">
                                            Deterministic Schedule Validation
                                          </span>
                                        </div>

                                        <div className="flex items-center space-x-2">
                                          <span className={`text-[10px] font-bold px-2.5 py-0.5 rounded-full uppercase tracking-wider ${
                                            isBlocked
                                              ? 'bg-rose-900/80 text-rose-200 border border-rose-700'
                                              : isHard
                                              ? 'bg-rose-900/80 text-rose-200 border border-rose-700'
                                              : isSoft
                                              ? 'bg-amber-900/80 text-amber-200 border border-amber-700'
                                              : 'bg-emerald-900/80 text-emerald-200 border border-emerald-700'
                                          }`}>
                                            {val.final_decision.replace(/_/g, ' ')}
                                          </span>
                                        </div>
                                      </div>

                                      {/* 4 Deterministic Rule Check Cards */}
                                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2.5">
                                        {/* Rule 1: Predecessors */}
                                        <div className="bg-slate-950/60 p-2 rounded border border-slate-800 flex items-center space-x-1.5">
                                          {val.violations.some(v => v.violation_type === 'PREDECESSOR_INCOMPLETE') ? (
                                            <XCircle className="w-3.5 h-3.5 text-rose-400 flex-shrink-0" />
                                          ) : (
                                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                                          )}
                                          <div className="text-[10px]">
                                            <span className="block text-slate-400">Predecessors</span>
                                            <span className={`font-mono font-medium ${
                                              val.violations.some(v => v.violation_type === 'PREDECESSOR_INCOMPLETE') ? 'text-rose-300' : 'text-emerald-300'
                                            }`}>
                                              {val.violations.some(v => v.violation_type === 'PREDECESSOR_INCOMPLETE') ? 'Incomplete' : 'Satisfied'}
                                            </span>
                                          </div>
                                        </div>

                                        {/* Rule 2: Chronological Sequence & Lag */}
                                        <div className="bg-slate-950/60 p-2 rounded border border-slate-800 flex items-center space-x-1.5">
                                          {val.violations.some(v => v.violation_type === 'OUT_OF_SEQUENCE') ? (
                                            <XCircle className="w-3.5 h-3.5 text-rose-400 flex-shrink-0" />
                                          ) : (
                                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                                          )}
                                          <div className="text-[10px]">
                                            <span className="block text-slate-400">Sequence & Lag</span>
                                            <span className={`font-mono font-medium ${
                                              val.violations.some(v => v.violation_type === 'OUT_OF_SEQUENCE') ? 'text-rose-300' : 'text-emerald-300'
                                            }`}>
                                              {val.violations.some(v => v.violation_type === 'OUT_OF_SEQUENCE') ? 'Out-of-Order' : 'Valid'}
                                            </span>
                                          </div>
                                        </div>

                                        {/* Rule 3: Quantity & Budget Overrun */}
                                        <div className="bg-slate-950/60 p-2 rounded border border-slate-800 flex items-center space-x-1.5">
                                          {val.violations.some(v => v.violation_type === 'QUANTITY_OVERRUN') ? (
                                            <XCircle className="w-3.5 h-3.5 text-rose-400 flex-shrink-0" />
                                          ) : (
                                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                                          )}
                                          <div className="text-[10px]">
                                            <span className="block text-slate-400">Quantity Overrun</span>
                                            <span className={`font-mono font-medium ${
                                              val.violations.some(v => v.violation_type === 'QUANTITY_OVERRUN') ? 'text-rose-300' : 'text-emerald-300'
                                            }`}>
                                              {val.violations.some(v => v.violation_type === 'QUANTITY_OVERRUN') ? 'Overrun >15%' : 'Within Budget'}
                                            </span>
                                          </div>
                                        </div>

                                        {/* Rule 4: Critical Path Float */}
                                        <div className="bg-slate-950/60 p-2 rounded border border-slate-800 flex items-center space-x-1.5">
                                          <Clock className={`w-3.5 h-3.5 ${val.is_critical_path ? 'text-amber-400' : 'text-teal-400'} flex-shrink-0`} />
                                          <div className="text-[10px]">
                                            <span className="block text-slate-400">Float / Critical</span>
                                            <span className="font-mono font-medium text-slate-200">
                                              {val.is_critical_path ? 'Critical (0 TF)' : `${val.total_float_days}d TF`}
                                            </span>
                                          </div>
                                        </div>
                                      </div>

                                      {/* Violations Details */}
                                      {val.violations.length > 0 && (
                                        <div className="mt-2.5 pt-2 border-t border-slate-800/80 space-y-1.5">
                                          {val.violations.map((violation) => (
                                            <div
                                              key={violation.id}
                                              className={`p-2 rounded border text-[11px] space-y-1 ${
                                                violation.severity === 'HARD_VIOLATION'
                                                  ? 'bg-rose-950/40 border-rose-800 text-rose-200'
                                                  : 'bg-amber-950/40 border-amber-800 text-amber-200'
                                              }`}
                                            >
                                              <div className="flex items-center justify-between">
                                                <span className="font-semibold">{violation.violation_type.replace(/_/g, ' ')}</span>
                                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-black/40 font-mono">
                                                  {violation.severity}
                                                </span>
                                              </div>
                                              <div>{violation.description}</div>
                                              {violation.expected_condition && (
                                                <div className="font-mono text-[10px] text-slate-300">
                                                  <span className="text-slate-400">Expected:</span> {violation.expected_condition}
                                                </div>
                                              )}
                                              {violation.observed_condition && (
                                                <div className="font-mono text-[10px] text-slate-300">
                                                  <span className="text-slate-400">Observed:</span> {violation.observed_condition}
                                                </div>
                                              )}
                                            </div>
                                          ))}
                                        </div>
                                      )}

                                      <div className="mt-2 text-[10px] text-slate-400 italic">
                                        Deterministic Rule Summary: {val.summary_reason}
                                      </div>
                                    </div>
                                  );
                                })()
                              ) : cand.candidate_id ? (
                                <div className="mt-3 pt-3 border-t border-slate-800 flex items-center justify-between">
                                  <span className="text-[11px] text-slate-400">Schedule & Dependency Validation not evaluated</span>
                                  <button
                                    onClick={() => validateCandidateAction(cand.candidate_id!)}
                                    disabled={validatingCandidateId === cand.candidate_id}
                                    className="text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 px-2.5 py-1 rounded border border-slate-700 transition"
                                  >
                                    {validatingCandidateId === cand.candidate_id ? 'Validating...' : 'Validate Schedule Constraints ⚡'}
                                  </button>
                                </div>
                              ) : null}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 4: SCHEDULE DEPENDENCY VALIDATOR & CPM AUDIT */}
        {/* ========================================================================= */}
        {activeTab === 'validation' && (
          <div className="space-y-6">
            {/* Top Overview & Controls */}
            <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-3">
                <div>
                  <div className="flex items-center space-x-2">
                    <Network className="w-5 h-5 text-teal-400" />
                    <h2 className="text-base font-bold text-white">
                      Deterministic Schedule & Dependency Engine
                    </h2>
                  </div>
                  <p className="text-xs text-slate-400 mt-1">
                    CPM Topological DAG analysis, precedence constraints (FS/SS/FF/SF), and strict schedule immutability invariant.
                  </p>
                </div>

                <div className="flex items-center space-x-2">
                  <button
                    onClick={() => selectedProjectId && loadGraphAndViolations(selectedProjectId)}
                    disabled={loadingGraph || loadingViolations}
                    className="flex items-center space-x-1.5 text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 px-3 py-1.5 rounded-lg transition disabled:opacity-50"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${loadingGraph ? 'animate-spin' : ''}`} />
                    <span>Refresh Graph & Violations</span>
                  </button>
                </div>
              </div>

              {/* Metric Summary Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 pt-1">
                <div className="bg-slate-950/70 p-3 rounded-lg border border-slate-800">
                  <span className="text-[11px] text-slate-400 block">Total DAG Activities</span>
                  <span className="text-lg font-bold font-mono text-slate-100">
                    {projectGraph ? projectGraph.nodes.length : activities.length}
                  </span>
                </div>

                <div className="bg-slate-950/70 p-3 rounded-lg border border-slate-800">
                  <span className="text-[11px] text-slate-400 block">Precedence Links (Edges)</span>
                  <span className="text-lg font-bold font-mono text-teal-400">
                    {projectGraph ? projectGraph.edges.length : '—'}
                  </span>
                </div>

                <div className="bg-slate-950/70 p-3 rounded-lg border border-slate-800">
                  <span className="text-[11px] text-slate-400 block">DAG Cycle Status</span>
                  <div className="flex items-center space-x-1.5 mt-0.5">
                    {projectGraph && !projectGraph.has_cycles ? (
                      <>
                        <ShieldCheck className="w-4 h-4 text-emerald-400" />
                        <span className="text-xs font-semibold text-emerald-400">Acyclic Verified</span>
                      </>
                    ) : projectGraph && projectGraph.has_cycles ? (
                      <>
                        <ShieldAlert className="w-4 h-4 text-rose-400" />
                        <span className="text-xs font-semibold text-rose-400">Cycle Detected</span>
                      </>
                    ) : (
                      <span className="text-xs text-slate-500 font-mono">Checking...</span>
                    )}
                  </div>
                </div>

                <div className="bg-slate-950/70 p-3 rounded-lg border border-slate-800">
                  <span className="text-[11px] text-slate-400 block">Project Duration (CPM)</span>
                  <span className="text-lg font-bold font-mono text-emerald-400">
                    {projectGraph ? `${projectGraph.project_duration_days} Days` : '—'}
                  </span>
                </div>

                <div className="bg-slate-950/70 p-3 rounded-lg border border-slate-800">
                  <span className="text-[11px] text-slate-400 block">Critical Path Activities</span>
                  <span className="text-lg font-bold font-mono text-amber-400">
                    {projectGraph ? `${projectGraph.critical_path_activities.length} (0 Float)` : '—'}
                  </span>
                </div>
              </div>
            </div>

            {/* Critical Path Sequence Banner */}
            {projectGraph && projectGraph.critical_path_activities.length > 0 && (
              <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 space-y-2">
                <div className="flex items-center space-x-2 border-b border-slate-800 pb-2">
                  <Clock className="w-4 h-4 text-amber-400" />
                  <h3 className="text-xs font-semibold text-slate-200 uppercase tracking-wider">
                    Calculated Critical Path Sequence (Zero Float Milestone Chain)
                  </h3>
                </div>
                <div className="flex flex-wrap items-center gap-1.5 pt-1">
                  {projectGraph.critical_path_activities.map((code, idx) => (
                    <React.Fragment key={code}>
                      <span className="text-[11px] font-mono px-2 py-1 rounded bg-amber-950/70 text-amber-300 border border-amber-800/80 font-bold">
                        {code}
                      </span>
                      {idx < projectGraph.critical_path_activities.length - 1 && (
                        <span className="text-slate-600 text-xs">→</span>
                      )}
                    </React.Fragment>
                  ))}
                </div>
              </div>
            )}

            {/* Dependency Violations Audit Trail Table */}
            <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
                <div className="flex items-center space-x-2">
                  <ShieldAlert className="w-4 h-4 text-rose-400" />
                  <h3 className="text-xs font-semibold text-slate-200 uppercase tracking-wider">
                    Dependency Violations & Safety Audit Log ({projectViolations.length})
                  </h3>
                </div>

                <div className="flex items-center space-x-2">
                  <span className="text-xs text-slate-400">Filter Severity:</span>
                  <div className="flex bg-slate-950 p-0.5 rounded border border-slate-800 text-[11px]">
                    {['ALL', 'HARD_VIOLATION', 'SOFT_WARNING'].map((f) => (
                      <button
                        key={f}
                        onClick={() => setViolationFilter(f)}
                        className={`px-2.5 py-0.5 rounded transition ${
                          violationFilter === f
                            ? 'bg-slate-800 text-slate-100 font-semibold'
                            : 'text-slate-400 hover:text-slate-200'
                        }`}
                      >
                        {f.replace(/_/g, ' ')}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {loadingViolations ? (
                <div className="text-center py-8 text-xs text-slate-400">Loading violations...</div>
              ) : projectViolations.length === 0 ? (
                <div className="text-center py-8 space-y-1">
                  <ShieldCheck className="w-8 h-8 text-emerald-500 mx-auto" />
                  <div className="text-xs text-slate-300 font-medium">Zero Dependency Violations Logged</div>
                  <div className="text-[11px] text-slate-500">
                    All evaluated claims adhere to predecessor completeness, sequence chronology, and quantity limits.
                  </div>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400 font-mono text-[11px]">
                        <th className="py-2 px-2">Severity</th>
                        <th className="py-2 px-2">Target Activity</th>
                        <th className="py-2 px-2">Predecessor</th>
                        <th className="py-2 px-2">Violation Type</th>
                        <th className="py-2 px-2">Description</th>
                        <th className="py-2 px-2">Expected / Observed</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 font-sans">
                      {projectViolations
                        .filter((v) => violationFilter === 'ALL' || v.severity === violationFilter)
                        .map((v) => (
                          <tr key={v.id} className="hover:bg-slate-800/40">
                            <td className="py-2.5 px-2">
                              <span
                                className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wider font-mono ${
                                  v.severity === 'HARD_VIOLATION'
                                    ? 'bg-rose-950 text-rose-300 border border-rose-800'
                                    : 'bg-amber-950 text-amber-300 border border-amber-800'
                                }`}
                              >
                                {v.severity.replace(/_/g, ' ')}
                              </span>
                            </td>
                            <td className="py-2.5 px-2 font-mono font-semibold text-emerald-400">
                              {v.activity_code || '—'}
                            </td>
                            <td className="py-2.5 px-2 font-mono text-amber-300">
                              {v.predecessor_activity_code || '—'}
                            </td>
                            <td className="py-2.5 px-2 font-mono text-slate-300 text-[11px]">
                              {v.violation_type}
                            </td>
                            <td className="py-2.5 px-2 text-slate-300 max-w-xs">
                              {v.description}
                            </td>
                            <td className="py-2.5 px-2 font-mono text-[10px] text-slate-400">
                              {v.expected_condition && <div><span className="text-slate-500">Exp:</span> {v.expected_condition}</div>}
                              {v.observed_condition && <div><span className="text-slate-500">Obs:</span> {v.observed_condition}</div>}
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 5: REVIEW & APPROVAL INBOX (PHASE 4) */}
        {/* ========================================================================= */}
        {activeTab === 'review' && selectedProjectId && (
          <ReviewInboxTab
            projectId={selectedProjectId}
            activities={activities}
            onScheduleUpdated={() => {
              if (selectedProjectId) {
                loadActivities(selectedProjectId, selectedDiscipline);
              }
            }}
          />
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800/80 bg-slate-950 py-4 mt-auto text-center text-xs text-slate-500">
        ProjectSynapse (SIH26122) · Oil India Limited · Modular Monolith Architecture · Phase 5 (Planning → Execution Bridge & AI Harmonization Engine)
      </footer>
    </div>
  );
}

export default App;
