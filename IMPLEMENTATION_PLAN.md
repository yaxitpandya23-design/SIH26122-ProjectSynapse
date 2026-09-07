# ProjectSynapse: Implementation Plan
**Smart India Hackathon 2026 | Problem ID: SIH26122**
**Domain:** Smart Automation / Infrastructure Project Management  
**Organization:** Oil India Limited (OIL)  
**Solution:** Intelligent Data Capture & Schedule-Linking Layer (Planning-to-Execution Bridge)

---

## 1. Overview & Strategy

ProjectSynapse bridges the critical gap between field execution reports (DPRs, site notes, drone logs) and master enterprise schedules (Primavera P6 / MS Project). 

To ensure a robust, high-impact demonstration within the **3-day SIH hackathon timeframe**, we adopt a **modular monolithic architecture** with:
- **FastAPI** backend with asynchronous I/O and strict Pydantic v2 schemas.
- **PostgreSQL 16 + pgvector** as the single unified data store for relational models and dense vector embeddings.
- **React 19 + Vite + Tailwind CSS** frontend focused on executive S-Curves, split-screen semantic verification, and a streamlined Human-in-the-Loop (HITL) review inbox.
- **Replaceable AI Provider Abstraction** with native support for Google Gemini, OpenAI, Ollama, and a zero-network deterministic MockProvider.
- **Deterministic Schedule & Graph Engine** handling all CPM logic, dependency checks, and quantity math with zero hallucination.

---

## 2. Phased Implementation Roadmap

```
+---------------------------------------------------------------------------------------------------+
|                                  PROJECT SYNAPSE IMPLEMENTATION PHASES                            |
|                                                                                                   |
|  [ Phase 1: Foundation & Data Ingestion ]                                                         |
|    - Monolith scaffold (backend + frontend + docker-compose)                                      |
|    - PostgreSQL + pgvector schema & models                                                        |
|    - Primavera P6 (.xer) & MS Project (.xml) schedule parsers                                     |
|    - Replaceable AI Provider interface (Gemini + Mock)                                             |
|    - Field DPR text/PDF ingestion & structured ProgressEvent extraction                          |
|                                                                                                   |
|  [ Phase 2: Semantic Matching & Confidence Scoring Engine ]                                      |
|    - Schedule activity vectorization & pgvector indexer                                           |
|    - Hybrid retrieval (BM25 sparse keyword + dense cosine similarity with RRF)                    |
|    - Multi-factor confidence scoring engine (Semantic, Spatial, Trade, Quantity, Time)            |
|    - LLM-assisted contextual candidate reranker & natural-language reasoning                      |
|                                                                                                   |
|  [ Phase 3: Deterministic Schedule Graph & Dependency Validator ]                                 |
|    - Directed Acyclic Graph (DAG) construction for schedule activities                           |
|    - CPM predecessor completion validation (Finish-to-Start, Start-to-Start)                      |
|    - Out-of-sequence execution detection & quantity overrun guardrails                            |
|    - Critical path slip and milestone delay forecasting                                           |
|                                                                                                   |
|  [ Phase 4: Human-in-the-Loop Review Inbox & State Sync ]                                         |
|    - Triage state machine (Pending -> Approved, Overridden, Rejected)                             |
|    - Immutable audit trail recording user decisions and reasoning                                 |
|    - Master schedule progress synchronization engine                                              |
|    - Primavera P6 update export generator (CSV / sync payload)                                    |
|                                                                                                   |
|  [ Phase 5: Frontend UI, Analytics Dashboard & Live Benchmark Demo ]                              |
|    - Executive Bridge Dashboard (Planned vs Actual S-Curves, Earned Value)                        |
|    - Interactive Schedule Explorer with WBS and CPM badges                                        |
|    - Core Split-Screen Match Verification & HITL Review Inbox                                     |
|    - End-to-end demo seeding with realistic Oil India pipeline data                               |
+---------------------------------------------------------------------------------------------------+
```

---

## 3. Detailed Work Breakdown & Module Specifications

### Phase 1: Foundation & Data Ingestion
**Objective:** Establish core database, backend skeleton, schedule parsers, and field DPR ingestion.

1. **Repository & Infrastructure Setup**
   - Create directory structure for `/backend`, `/frontend`, and `/sample_data`.
   - Setup `docker-compose.yml` defining PostgreSQL 16 with `pgvector/pgvector:pg16`.
   - Setup Python environment with FastAPI, SQLAlchemy 2.0, Asyncpg, Alembic, Pydantic v2, NetworkX, and PyPDF.
   - Setup React + Vite + Tailwind CSS + Lucide Icons + TanStack Query + Zustand frontend scaffold.

2. **Database Models & Migrations**
   - Implement SQLAlchemy ORM models:
     - `Project`, `ScheduleVersion`, `ScheduleActivity`, `ActivityDependency`
     - `FieldReport`, `ProgressEvent`, `ActivityMatchCandidate`, `DependencyViolation`, `ReviewAudit`
   - Configure Alembic and generate baseline migration scripts.

3. **Schedule Parsing Engine**
   - Implement `p6_xer_parser.py`: Parses Primavera P6 tabular text tables (`%T ACTVTYPE`, `%T TASK`, `%T TASKPRED`, `%T PROJWBS`). Extracts activity codes, names, planned dates, float, and predecessor links.
   - Implement `msp_xml_parser.py`: Parses MS Project XML schema (`<Task>`, `<PredecessorLink>`, `<WBS>`).
   - Implement `csv_parser.py`: Simple tabular fallback for rapid data loading.

4. **AI Provider Abstraction Layer**
   - Implement `BaseLLMProvider` and `BaseEmbeddingProvider` abstract interfaces.
   - Implement `GeminiProvider` using Google GenAI SDK.
   - Implement `MockProvider` returning pre-computed embeddings and deterministic structured events for reliable offline demonstration.

5. **Field Ingestion & Entity Extractor**
   - Endpoint: `POST /api/v1/field-reports/upload` and `POST /api/v1/field-reports/raw-text`.
   - Parser: Extracts raw text from PDF/TXT, calls LLM to produce normalized `ProgressEvent` schema (work description, discipline, chainage/location, quantity, UOM, status claim).

---

### Phase 2: Semantic Matching & Confidence Scoring Engine
**Objective:** Implement the core innovative planning-to-execution mapping layer.

1. **Schedule Vector Indexing**
   - Concatenate activity metadata: `{WBS Name} > {Activity Name} | Discipline: {Discipline} | Scope: {Scope}`.
   - Generate embeddings using `BaseEmbeddingProvider` and store in `schedule_activities.embedding` column with HNSW vector index in PostgreSQL.

2. **Hybrid Search Pipeline**
   - Combine sparse lexical search (PostgreSQL full-text search / BM25) with dense vector cosine similarity (`<=>` operator in pgvector).
   - Use Reciprocal Rank Fusion (RRF) to merge top-10 candidates.

3. **Multi-Factor Confidence Scoring Engine**
   - Compute explicit weighted score:
     $$\text{Score} = 0.40 \cdot S_{\text{sem}} + 0.20 \cdot S_{\text{trade}} + 0.20 \cdot S_{\text{loc}} + 0.10 \cdot S_{\text{qty}} + 0.10 \cdot S_{\text{time}}$$
   - Generate detailed JSON breakdown (`score_breakdown`) stored with each match candidate.

4. **Contextual LLM Reranking & Reasoning**
   - When top-2 candidate scores are close ($\Delta < 0.15$), prompt LLM to analyze the construction context and generate concise human-readable reasoning explaining why the match is valid.

---

### Phase 3: Deterministic Schedule Graph & Dependency Validator
**Objective:** Guarantee zero hallucinations in construction scheduling rules.

1. **Schedule DAG Construction**
   - Build a directed acyclic graph using `networkx.DiGraph` representing activities as nodes and dependencies (`FS`, `SS`, `FF`, `SF`) as directed edges.

2. **Dependency Violation Rules**
   - **Rule 1 (Predecessor Incomplete):** Flag when an activity is reported as started/in-progress while mandatory Finish-to-Start predecessors have not reached 100%.
   - **Rule 2 (Out-of-Sequence Execution):** Work reported before start milestones have fired.
   - **Rule 3 (Quantity Overrun Guardrail):** Cumulative actual quantity + reported quantity exceeds $110\%$ of baseline planned quantity.
   - **Rule 4 (Milestone Slippage):** Calculate critical path delay and project finish date impact when a critical activity slips.

3. **Validation Endpoints**
   - Endpoint: `GET /api/v1/validation/violations`.
   - Endpoint: `POST /api/v1/validation/verify-event/{event_id}/{activity_id}`.

---

### Phase 4: Human-in-the-Loop Review Inbox & Schedule State Sync
**Objective:** Provide a transparent, audited triage workflow for engineers.

1. **Triage Lifecycle Management**
   - High confidence ($\ge 0.85$) + No violations $\rightarrow$ Eligible for `AUTO_APPROVED`.
   - Medium confidence ($0.50 \le \text{Score} < 0.85$) or Dependency Violation $\rightarrow$ Routed to `PENDING_REVIEW`.
   - Low confidence ($< 0.50$) $\rightarrow$ Routed to `UNMATCHED`.

2. **HITL Review Endpoints**
   - `GET /api/v1/reviews/inbox` (filter by project, status, confidence range).
   - `POST /api/v1/reviews/{id}/approve`
   - `POST /api/v1/reviews/{id}/override` (reassign to a different activity code).
   - `POST /api/v1/reviews/{id}/reject` (dismiss with reason).

3. **Schedule Synchronization & P6 Export**
   - Updating approved events rolls up progress into `schedule_activities.actual_quantity` and `schedule_activities.physical_percent_complete`.
   - Endpoint: `GET /api/v1/analytics/export/p6-sync` outputs a clean CSV/JSON formatted for direct re-import into Primavera P6.

---

### Phase 5: Frontend UI, Analytics & Hackathon Polish
**Objective:** Deliver an intuitive, visually stunning user experience.

1. **Executive Bridge Dashboard**
   - S-Curve visualization: Cumulative Planned % vs. Actual Verified % over time.
   - Summary metric cards: Total Ingested Events, Auto-Matched %, Pending Review Count, Critical Path Slippage.

2. **Schedule Explorer & Gantt View**
   - Interactive hierarchical WBS table.
   - Visual badges for Critical Path, Predecessors, and Physical % Complete.

3. **Field Capture & Ingestion Screen**
   - Drag-and-drop DPR upload with live progress bar.
   - Raw text quick-paste box with immediate extraction feedback.

4. **Split-Screen Match Verification & HITL Review Inbox (Flagship UI)**
   - Left pane: Extracted Progress Event with provenance snippet.
   - Right pane: Top-3 candidate cards with overall confidence gauge, sub-score badges, dependency warning alerts, and 1-click Approve / Reassign / Reject buttons.

5. **Sample Datasets & Live Demo Script**
   - Realistic Oil India pipeline schedule (50 activities spanning ROW clearing, trenching, stringing, welding, NDT, lowering, backfilling, hydrotesting).
   - 10 realistic DPR logs showcasing varied scenarios: high confidence exact match, colloquial phrasing match, dependency violation catch, and quantity overrun warning.

---

## 4. Verification & Testing Matrix

| Component | Test Method | Target Metric |
|---|---|---|
| **P6 XER Parser** | Unit tests on synthetic `.xer` files | 100% extraction of tasks, dates, dependencies |
| **LLM Event Extractor** | Evaluation against 20 DPR sentences | $\ge 95\%$ valid JSON schema conformity |
| **Semantic Matcher** | Benchmark dataset of 25 field reports | $\ge 85\%$ Top-1 precision, $\ge 95\%$ Top-3 recall |
| **Confidence Engine** | Mathematical unit tests for all feature weights | Output strictly bounded in $[0.0, 1.0]$ |
| **Dependency Validator** | Graph DAG unit tests on known violation scenarios | 100% detection of incomplete predecessors |
| **Review Inbox Workflow** | End-to-end integration tests (Ingest $\rightarrow$ Match $\rightarrow$ Review $\rightarrow$ Sync) | Zero orphan records, complete audit logs |

---

## 5. Development Order Summary

1. **Step 1:** Monolith skeleton & docker-compose environment setup.
2. **Step 2:** Database models, migrations, and P6/MSP parsers.
3. **Step 3:** AI Provider abstraction (Gemini + Mock) & DPR event extractor.
4. **Step 4:** pgvector indexing, hybrid retrieval, and multi-factor confidence scoring.
5. **Step 5:** Deterministic DAG schedule dependency validator.
6. **Step 6:** HITL review inbox endpoints and schedule synchronization logic.
7. **Step 7:** React frontend (Executive Dashboard, Split-Screen Matcher, Review Inbox).
8. **Step 8:** Seed benchmark Oil India data and conduct end-to-end demo dry run.

---

*Document Author: ProjectSynapse Lead Software Architect*  
*Version: 1.0.0 | Status: Ready for Step-by-Step Implementation*
