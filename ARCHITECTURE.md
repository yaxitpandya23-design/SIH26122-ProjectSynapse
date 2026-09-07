# ProjectSynapse: Architecture Specification
**Smart India Hackathon 2026 | Problem ID: SIH26122**
**Domain:** Smart Automation / Infrastructure Project Management
**Organization:** Oil India Limited (OIL)
**Solution:** Intelligent Data Capture & Schedule-Linking Layer (Planning-to-Execution Bridge)

---

## Executive Summary & System Mission

Large-scale infrastructure projects—such as oil and gas pipeline construction, well-pad development, gathering stations, and refinery expansions—suffer from a persistent disconnect between **Project Planning** (maintained in Oracle Primavera P6 or Microsoft Project) and **Field Execution** (communicated via Daily Progress Reports [DPRs], site inspection memos, shift logs, and field chat updates).

ProjectSynapse is an intelligent, high-precision middleware layer that automatically ingests unstructured field execution data, transforms it into normalized **Progress Events**, semantically maps these events to Work Breakdown Structure (WBS) **Schedule Activities**, validates updates against deterministic CPM (Critical Path Method) schedule dependencies, and provides a Human-in-the-Loop (HITL) review workspace before synchronizing verified progress back to enterprise project management baselines.

```
+---------------------------------------------------------------------------------------------------+
|                                      PROJECT SYNAPSE CORE LOOP                                    |
|                                                                                                   |
|  [ Field DPRs, Site Memos, WhatsApp/Chat Logs, PDFs ]                                             |
|                             |                                                                     |
|                             v                                                                     |
|            +----------------------------------+                                                   |
|            |  AI Event Extraction & Parsing   |  (LLM: Structured JSON Extraction)                |
|            +----------------------------------+                                                   |
|                             |                                                                     |
|                             v                                                                     |
|            +----------------------------------+                                                   |
|            |     Normalized Progress Event    |                                                   |
|            +----------------------------------+                                                   |
|                             |                                                                     |
|                             v                                                                     |
|     +-----------------------------------------------+                                             |
|     |  Hybrid Semantic Matcher (BM25 + Dense Vector)|  <--- [ Master Schedule: Primavera P6 / MSP] |
|     +-----------------------------------------------+                                             |
|                             |                                                                     |
|                             v                                                                     |
|     +-----------------------------------------------+                                             |
|     |     Multi-Factor Confidence Scoring Engine    |  (Semantic, Spatial, Trade, Quantity, Time)|
|     +-----------------------------------------------+                                             |
|                             |                                                                     |
|                             v                                                                     |
|     +-----------------------------------------------+                                             |
|     |   Deterministic Dependency Graph Validator    |  (DAG CPM check, Out-of-Sequence, Overrun)  |
|     +-----------------------------------------------+                                             |
|                             |                                                                     |
|              +--------------+--------------+                                                      |
|              |                             |                                                      |
|   Confidence >= 0.85 & Valid    Confidence < 0.85 OR Dependency Flag                              |
|              |                             |                                                      |
|              v                             v                                                      |
|     [ Auto-Sync Ready ]           [ Human-in-the-Loop Review Queue ]                              |
|              |                             |                                                      |
|              +--------------+--------------+                                                      |
|                             | (Engineer Approved)                                                 |
|                             v                                                                     |
|     [ Schedule State Sync & Variance Analytics (S-Curves, Milestone Slippage, P6 Export) ]         |
+---------------------------------------------------------------------------------------------------+
```

---

## 1. Recommended Repository Structure

ProjectSynapse is organized as a clean **Modular Monolith**. This eliminates microservice networking overhead, guarantees atomic database transactions across schedule entities and match events, simplifies local setup during a 3-day hackathon, and enables fast judge evaluation.

```
SIH26122-ProjectSynapse/
├── ARCHITECTURE.md                  # Detailed system architecture document
├── IMPLEMENTATION_PLAN.md           # Implementation phasing and execution roadmap
├── PROJECT_SPEC.md                  # Problem statement reference
├── docker-compose.yml               # Local PostgreSQL + pgvector + app stack
├── .env.example                     # Environment configuration template
│
├── backend/                         # Python FastAPI Modular Monolith
│   ├── Dockerfile
│   ├── pyproject.toml / requirements.txt
│   ├── alembic/                     # Database migrations
│   │   └── versions/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                  # FastAPI application entrypoint & middleware
│   │   ├── core/                    # Cross-cutting foundational utilities
│   │   │   ├── config.py            # Pydantic Settings (DB, AI keys, thresholds)
│   │   │   ├── database.py          # SQLAlchemy 2.0 async engine & sessionmaker
│   │   │   ├── logging.py           # Structured JSON logger
│   │   │   └── security.py          # CORS, API-key authentication
│   │   ├── ai/                      # Replaceable AI / LLM Provider Abstraction
│   │   │   ├── base.py              # Abstract interfaces: BaseLLMProvider, BaseEmbeddingProvider
│   │   │   ├── factory.py           # Dynamic provider factory (Gemini, OpenAI, Ollama, Mock)
│   │   │   ├── gemini_provider.py   # Google Gemini implementation
│   │   │   ├── openai_provider.py   # OpenAI implementation
│   │   │   ├── ollama_provider.py   # Local offline Ollama implementation
│   │   │   └── mock_provider.py     # Deterministic mock provider (guaranteed offline demo)
│   │   ├── modules/                 # Domain Modules
│   │   │   ├── schedules/           # Schedule parsing & WBS management
│   │   │   │   ├── models.py        # Schedule, Activity, Dependency ORM models
│   │   │   │   ├── schemas.py       # Pydantic DTOs for activities & WBS
│   │   │   │   ├── parsers/         # Parsers for Primavera P6 (.xer), MS Project (.xml), CSV
│   │   │   │   │   ├── p6_xer_parser.py
│   │   │   │   │   ├── msp_xml_parser.py
│   │   │   │   │   └── csv_parser.py
│   │   │   │   ├── router.py        # /api/v1/schedules endpoints
│   │   │   │   └── service.py       # Schedule ingestion & query business logic
│   │   │   ├── field_capture/       # Unstructured DPR & field log ingestion
│   │   │   │   ├── models.py        # FieldReport, ProgressEvent ORM models
│   │   │   │   ├── schemas.py       # ProgressEvent Pydantic schemas
│   │   │   │   ├── extractor.py     # LLM-guided structured entity extraction
│   │   │   │   ├── router.py        # /api/v1/field-reports endpoints
│   │   │   │   └── service.py       # Field ingestion orchestration
│   │   │   ├── semantic_matcher/    # The Core Innovation: Semantic Activity Mapping
│   │   │   │   ├── models.py        # ActivityMatchCandidate ORM models
│   │   │   │   ├── schemas.py       # Match request & result schemas
│   │   │   │   ├── indexer.py       # Schedule embedding generator & vector indexer
│   │   │   │   ├── hybrid_search.py # BM25 + pgvector cosine similarity fusion
│   │   │   │   ├── reranker.py      # LLM contextual reranker & reasoning generator
│   │   │   │   ├── router.py        # /api/v1/matching endpoints
│   │   │   │   └── service.py       # Match pipeline orchestrator
│   │   │   ├── scoring/             # Multi-factor confidence scoring
│   │   │   │   ├── engine.py        # Weighted multi-attribute scoring algorithms
│   │   │   │   └── criteria.py      # Semantic, trade, spatial, quantity, temporal rules
│   │   │   ├── dependency_validator/# Deterministic Graph & CPM Constraints
│   │   │   │   ├── graph.py         # NetworkX / Custom DAG representation
│   │   │   │   ├── validator.py     # Predecessor, out-of-sequence, overrun checks
│   │   │   │   ├── models.py        # ValidationViolation ORM models
│   │   │   │   ├── router.py        # /api/v1/validation endpoints
│   │   │   │   └── service.py       # Dependency rule verification engine
│   │   │   ├── review_inbox/        # Human-in-the-Loop review & triage
│   │   │   │   ├── models.py        # ReviewDecision, AuditLog models
│   │   │   │   ├── schemas.py       # Review action request/response schemas
│   │   │   │   ├── router.py        # /api/v1/reviews endpoints
│   │   │   │   └── service.py       # Triage lifecycle (approve, reassign, reject)
│   │   │   └── analytics/           # S-Curves, Earned Value, variance, P6 export
│   │   │       ├── curves.py        # Planned vs Actual physical S-curve generator
│   │   │       ├── variance.py      # Schedule variance & milestone slip calculator
│   │   │       ├── exporter.py      # Sync export generator (updated P6/CSV/JSON)
│   │   │       └── router.py        # /api/v1/analytics endpoints
│   │   └── tests/                   # Backend automated test suite
│   │       ├── test_parsers.py      # P6/MSP parser verification
│   │       ├── test_extractor.py    # Unstructured event extraction tests
│   │       ├── test_matcher.py      # Semantic matching precision benchmarks
│   │       ├── test_scoring.py      # Confidence engine boundary tests
│   │       ├── test_validator.py    # Dependency constraint violation tests
│   │       └── test_e2e_pipeline.py # End-to-end ingest-to-sync flow
│
├── frontend/                        # React 19 + Vite + Tailwind CSS SPA
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── api/                     # Axios/Fetch typed client with React Query
│   │   │   ├── client.ts
│   │   │   ├── schedules.ts
│   │   │   ├── fieldCapture.ts
│   │   │   ├── matching.ts
│   │   │   ├── review.ts
│   │   │   └── analytics.ts
│   │   ├── components/              # Reusable UI component library (shadcn/Radix)
│   │   │   ├── ui/                  # Buttons, Badges, Modals, Tables, Tabs, Drawers
│   │   │   ├── layout/              # Navbar, Sidebar, PageContainer
│   │   │   ├── ConfidenceBadge.tsx  # Color-coded confidence score pill
│   │   │   └── ViolationAlert.tsx   # Visual dependency warning cards
│   │   ├── features/                # Domain-specific UI features
│   │   │   ├── dashboard/           # Executive overview, S-Curves, KPI cards
│   │   │   ├── schedule/            # Schedule Gantt viewer & WBS hierarchical table
│   │   │   ├── capture/             # DPR uploader, text paste, extracted event preview
│   │   │   ├── matching/            # The Core Split-Screen Match Verification UI
│   │   │   ├── review/              # HITL Review Inbox, triage filters, 1-click actions
│   │   │   └── analytics/           # Earned value charts, delay forecast, P6 export modal
│   │   ├── stores/                  # Lightweight Zustand state stores
│   │   │   ├── projectStore.ts
│   │   │   └── reviewStore.ts
│   │   └── types/                   # TypeScript interfaces matching backend DTOs
│
└── sample_data/                     # Benchmark Data for Hackathon Evaluation
    ├── schedules/
    │   ├── oil_india_pipeline_project.xer   # Real-world styled P6 schedule
    │   ├── wellpad_construction.xml         # MS Project XML schedule
    │   └── civil_foundation_wbs.csv         # Tabular baseline schedule
    ├── field_reports/
    │   ├── dpr_day14_stringing_trenching.txt # Unstructured site daily log
    │   ├── dpr_day15_hydrotest_crossing.pdf  # PDF field report
    │   └── whatsapp_site_updates.json        # Informal field chat transcripts
    └── benchmarks/
        └── ground_truth_matches.json         # Benchmark pairs for precision testing
```

---

## 2. Frontend Architecture

The frontend is a modern single-page application (SPA) optimized for fast site-engineer workflows, responsive split-screen comparison, and clear visual auditing.

### Key Architectural Principles:
1. **Separation of Concerns:** Component presentation is decoupled from server state via TanStack Query (React Query).
2. **Domain-Driven Directory Layout:** Features are encapsulated (`features/matching`, `features/review`, `features/schedule`), keeping logic, components, and local hooks co-located.
3. **Optimistic Updates:** Triage actions (Approve, Reassign, Reject) update the UI immediately with rollback safety.
4. **Visual Trust Indicators:** Matches explicitly display score component breakdowns (Semantic, Spatial, Trade, Quantity, Schedule Plausibility) and deterministic violation pills.

### Primary UI Workspaces:
- **Executive Bridge Dashboard:** Displays the physical S-Curve (Planned % vs. Actual Verified %), Earned Value metrics, milestone slippage radar, and progress velocity.
- **Master Schedule Explorer:** Interactive WBS tree and timeline view displaying activity IDs, critical path flags, planned durations, and dependencies.
- **Field Capture Hub:** Multi-modal ingestion screen supporting drag-and-drop DPR upload (PDF/TXT), raw text paste, and instant visualization of parsed Progress Events.
- **Semantic Match & Verification Workspace (Flagship Screen):** Side-by-side inspection view:
  - *Left Column:* Extracted field event (raw text, detected chainage/location, discipline, reported volume).
  - *Right Column:* Top 3 candidate schedule activities with match confidence gauge, trade compatibility badge, and detailed AI rationale.
- **Human-in-the-Loop Review Inbox:** High-efficiency triage queue for medium/low confidence matches or flagged dependency violations. Equipped with 1-click batch approvals, override search modal, and audit reasoning notes.

---

## 3. Backend Architecture

The backend is built as a high-performance **Modular Monolith** using **Python 3.11+** and **FastAPI**.

```
+---------------------------------------------------------------------------------------------------+
|                                  FASTAPI APPLICATION GATEWAY                                      |
|                       [ CORS | OpenAPI / Docs | Error Handlers | Auth ]                            |
+---------------------------------------------------------------------------------------------------+
                                                |
                   +----------------------------+----------------------------+
                   |                            |                            |
                   v                            v                            v
          [ Schedule Router ]          [ Field Report Router ]       [ Matching & Review Router ]
                   |                            |                            |
                   v                            v                            v
          [ Schedule Service ]         [ Ingestion Service ]         [ Matching Pipeline Service ]
                   |                            |                            |
         +---------+---------+                  |                   +--------+--------+
         |                   |                  v                   |                 |
    (P6 Parser)         (MSP Parser)     (LLM Extractor)     (BM25 Search)     (pgvector Dense)
         |                   |                  |                   |                 |
         +---------+---------+                  |                   +--------+--------+
                   |                            |                            |
                   v                            v                            v
    +-----------------------------------------------------------------------------------------------+
    |                                 DOMAIN BUSINESS CORE LOGIC                                    |
    |  - Multi-Factor Confidence Scorer (Mathematical heuristic combination)                        |
    |  - Deterministic Dependency Validator (NetworkX DAG CPM graph evaluation)                    |
    |  - HITL Review Lifecycle Manager (Pending -> Approved / Rejected -> Audit Log)               |
    +-----------------------------------------------------------------------------------------------+
                                                |
                                                v
    +-----------------------------------------------------------------------------------------------+
    |                                DATA ACCESS LAYER (SQLAlchemy 2.0 Async)                       |
    |                  [ PostgreSQL 16 + pgvector Extension for unified storage ]                   |
    +-----------------------------------------------------------------------------------------------+
```

### Deterministic vs. AI Separation of Responsibilities:
A fundamental architectural tenet of ProjectSynapse is: **Never use probabilistic LLMs for operations that deterministic algorithms execute with 100% mathematical certainty.**

| Capability | Execution Engine | Rationale |
|---|---|---|
| DPR Entity & Event Extraction | **AI / LLM** | Unstructured human language, abbreviations, typos, and varying formats require semantic comprehension. |
| Text Vector Embeddings | **AI / Embedding Model** | High-dimensional semantic representation of activities and field descriptions. |
| Borderline Candidate Arbitration | **AI / LLM Reasoner** | Synthesizing contextual nuances between close matches when heuristics are inconclusive. |
| Schedule File Ingestion (XER/XML) | **Deterministic Parser** | Exact schema standards; 100% deterministic parsing required. |
| Topological Dependency Checking | **Deterministic DAG (NetworkX)** | CPM math, predecessor completion, and lag calculations must have zero hallucination. |
| Confidence Score Calculation | **Deterministic Formula** | Multi-factor weighted arithmetic with explicit weights and verifiable breakdown. |
| Quantity Overrun Verification | **Deterministic Math** | Comparing reported cumulative quantities against baseline limits. |
| State Transitions & Audit Trails | **Deterministic DB Transactions** | ACID compliance, transactional integrity, and tamper-proof logging. |

---

## 4. Database Architecture (PostgreSQL + pgvector)

We utilize **PostgreSQL 16** with the **pgvector** extension. This eliminates the need to run, configure, and synchronize a separate vector database (e.g. Pinecone, Milvus, Qdrant) during the 3-day hackathon.

### Entity Relationship Diagram (ERD):

```
+-------------------+             +-----------------------+             +------------------------+
|     projects      | 1 ------- * |   schedule_versions   | 1 ------- * |  schedule_activities   |
+-------------------+             +-----------------------+             +------------------------+
| id (PK)           |             | id (PK)               |             | id (PK)                |
| name              |             | project_id (FK)       |             | schedule_version_id(FK)|
| code              |             | version_label         |             | activity_code          |
| client_name       |             | is_active_baseline    |             | name                   |
| target_start_date |             | imported_at           |             | discipline             |
| target_finish_date|             +-----------------------+             | wbs_code               |
+-------------------+                                                   | planned_start          |
                                                                        | planned_finish         |
                                                                        | planned_quantity       |
+-------------------+             +-----------------------+             | uom                    |
|   field_reports   | 1 ------- * |    progress_events    |             | is_critical (bool)     |
+-------------------+             +-----------------------+             | embedding (vector)     |
| id (PK)           |             | id (PK)               |             +------------------------+
| project_id (FK)   |             | field_report_id (FK)  |                         |
| report_date       |             | work_description      |                         | 1
| reporter_name     |             | discipline            |                         |
| raw_source_text   |             | location_chainage     |                         | *
| source_type       |             | quantity_reported     |             +------------------------+
+-------------------+             | uom                   |             | activity_dependencies  |
                                  | event_date            |             +------------------------+
                                  | embedding (vector)    |             | id (PK)                |
                                  +-----------------------+             | predecessor_id (FK)    |
                                              |                         | successor_id (FK)      |
                                              | 1                       | dependency_type (FS..) |
                                              |                         | lag_days               |
                                              v *                       +------------------------+
                                  +-----------------------+
                                  |   match_candidates    |
                                  +-----------------------+
                                  | id (PK)               |
                                  | progress_event_id(FK) |
                                  | activity_id (FK)      |
                                  | confidence_score      |
                                  | score_breakdown (JSON)|
                                  | status (PENDING..)    |
                                  | llm_reasoning         |
                                  +-----------------------+
                                              |
                                              v 1
                                  +-----------------------+
                                  |    review_audits      |
                                  +-----------------------+
                                  | id (PK)               |
                                  | match_candidate_id(FK)|
                                  | decision (APPROVE..)  |
                                  | reviewer_user         |
                                  | review_timestamp      |
                                  | remarks               |
                                  +-----------------------+
```

### Table Definitions:

1. **`projects`**: Top-level project entities (e.g., "Duliajan-Numaligarh Crude Pipeline Section 3").
2. **`schedule_versions`**: Manages baseline vs. working schedules. Tracks imports from XER or XML.
3. **`schedule_activities`**: Master task list. Includes planned dates, float, WBS, quantities, and precomputed semantic embeddings.
4. **`activity_dependencies`**: Predecessor-successor relationships (Finish-to-Start, Start-to-Start, etc.) and lag values.
5. **`field_reports`**: Master DPR header tracking submission date, author, source document, and full raw payload.
6. **`progress_events`**: Atomic physical execution events extracted from DPRs by AI.
7. **`activity_match_candidates`**: Evaluated matches linking `progress_events` to `schedule_activities`, storing confidence scores and review status (`PENDING_REVIEW`, `AUTO_APPROVED`, `MANUALLY_APPROVED`, `REASSIGNED`, `REJECTED`).
8. **`dependency_violations`**: Stores rule infractions flagged by the deterministic validator.
9. **`review_audits`**: Complete tamper-evident audit history of all human actions.

---

## 5. AI/ML Architecture & Replaceable Provider

ProjectSynapse abstracts all AI model interactions behind unified base classes. This guarantees zero lock-in and protects the project during the hackathon against API rate limits or lack of internet connectivity.

```
                  +-----------------------------------+
                  |        <<Abstract Interface>>     |
                  |          BaseLLMProvider          |
                  +-----------------------------------+
                  | + extract_events(text)            |
                  | + rerank_and_reason(event, cand)  |
                  +-----------------------------------+
                                    ^
        +---------------------------+---------------------------+
        |                           |                           |
+-------------------+       +-------------------+       +-------------------+
|  GeminiProvider   |       |  OpenAIProvider   |       |   MockProvider    |
| (Google Gemini)   |       | (GPT-4o / mini)   |       | (Offline Testing) |
+-------------------+       +-------------------+       +-------------------+
```

### Supported Providers:
1. **Google Gemini (`GeminiProvider`):** Default high-speed cloud provider using `gemini-1.5-flash` for high-throughput event extraction and `text-embedding-004` for semantic vectors.
2. **OpenAI (`OpenAIProvider`):** Alternate cloud provider using `gpt-4o-mini` and `text-embedding-3-small`.
3. **Ollama (`OllamaProvider`):** Local offline LLM provider (running Llama 3.2 / Mistral + Nomic-Embed) for air-gapped infrastructure operations.
4. **Deterministic Mock (`MockProvider`):** Returns deterministic, pre-calculated embeddings and realistic structured event extractions without network calls. **Guarantees that the application never crashes during live judge demonstrations even if external APIs fail.**

---

## 6. API Structure (FastAPI REST Endpoints)

All endpoints return standard JSON responses and enforce validation using Pydantic v2.

### Endpoints Overview:

#### 1. Projects & Schedules
- `POST /api/v1/projects` — Create project profile.
- `POST /api/v1/schedules/upload` — Ingest Primavera P6 (`.xer`), MS Project (`.xml`), or `.csv`.
- `GET /api/v1/schedules/{id}/activities` — Query activities with optional filtering by discipline, WBS, or critical path.
- `GET /api/v1/schedules/{id}/network-graph` — Retrieve nodes and dependency edges for Gantt / DAG visualization.

#### 2. Field Data Ingestion
- `POST /api/v1/field-reports/upload` — Upload DPR documents (PDF/TXT/DOCX).
- `POST /api/v1/field-reports/raw-text` — Submit unstructured raw text / site notes.
- `GET /api/v1/field-reports` — List ingested field reports.
- `GET /api/v1/progress-events` — List parsed atomic progress events.

#### 3. Semantic Activity Matching
- `POST /api/v1/matching/process-event/{event_id}` — Execute matching engine for a specific progress event.
- `POST /api/v1/matching/batch-process` — Run matching across all pending progress events.
- `GET /api/v1/matching/candidates/{event_id}` — Retrieve top-K matched activities with score breakdown and reasoning.

#### 4. Human-in-the-Loop Review
- `GET /api/v1/reviews/inbox` — Retrieve triage inbox items (filtered by status: `PENDING`, `FLAGGED`, `AUTO_APPROVED`).
- `POST /api/v1/reviews/{candidate_id}/approve` — Approve suggested match.
- `POST /api/v1/reviews/{candidate_id}/override` — Remap event to a different user-selected activity.
- `POST /api/v1/reviews/{candidate_id}/reject` — Reject candidate as invalid or duplicate.

#### 5. Validation & Dependency Check
- `GET /api/v1/validation/violations` — List detected schedule violations (predecessor incomplete, out-of-sequence, overrun).
- `POST /api/v1/validation/verify-event/{event_id}/{activity_id}` — Perform real-time dependency checks prior to approval.

#### 6. Analytics & Schedule Export
- `GET /api/v1/analytics/s-curve` — Retrieve Planned vs. Actual physical progress S-curve data.
- `GET /api/v1/analytics/variance-report` — Summary of milestone slippages and critical path impacts.
- `GET /api/v1/analytics/export/p6-sync` — Generate update payload / CSV to synchronize progress back into Primavera P6.

---

## 7. Data Flow (End-to-End Lifecycle)

```
[Site DPR: "Welding of 450m completed between Ch 24+100 and Ch 24+550"]
                           |
                           v  (Step 1: Ingestion)
               POST /api/v1/field-reports
                           |
                           v  (Step 2: AI Event Extraction)
               ProgressEvent {
                 work_description: "Pipeline welding completed",
                 discipline: "PIPING",
                 chainage_start: 24.10, chainage_end: 24.55,
                 quantity: 450, uom: "M"
               }
                           |
                           v  (Step 3: Vectorization & Hybrid Retrieval)
               BM25 Keyword Search + pgvector Cosine Distance
               -> Candidates:
                  1. ACT-2040: "Mainline Pipeline Welding Ch 20-30km"
                  2. ACT-1020: "Trench Excavation Ch 20-30km"
                  3. ACT-3010: "Hydrostatic Testing Ch 20-30km"
                           |
                           v  (Step 4: Confidence Scoring Engine)
               Scores:
                  ACT-2040 -> 0.92 (High semantic + discipline + chainage match)
                  ACT-1020 -> 0.45 (Discipline mismatch: Piping vs Civil)
                  ACT-3010 -> 0.38 (Activity type mismatch: Testing vs Welding)
                           |
                           v  (Step 5: Deterministic Dependency Validator)
               Check ACT-2040 Predecessors:
               - Predecessor: ACT-2030 (Pipe Stringing & Bending) -> 100% COMPLETE [PASS]
               - Predecessor: ACT-1020 (Trench Excavation) -> 90% COMPLETE [PASS]
               - Quantity Check: 450m added to 1200m <= 10000m planned [PASS]
                           |
                           v  (Step 6: Triage Routing)
               Confidence 0.92 >= 0.85 AND Zero Violations
               -> Route: AUTO_APPROVED (with 1-click review confirmation)
                           |
                           v  (Step 7: Schedule State Synchronization)
               Activity ACT-2040 Actual Quantity updated -> S-Curve recalculated
```

---

## 8. Progress-Event Schema

Extracted by the AI entity extractor from raw field text, formatted as a strongly validated Pydantic model:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ProgressEvent",
  "type": "object",
  "required": [
    "event_id",
    "report_id",
    "event_date",
    "work_description",
    "discipline",
    "status_claim"
  ],
  "properties": {
    "event_id": { "type": "string", "format": "uuid" },
    "report_id": { "type": "string", "format": "uuid" },
    "event_date": { "type": "string", "format": "date" },
    "work_description": { 
      "type": "string",
      "description": "Normalized summary of physical work executed" 
    },
    "discipline": { 
      "type": "string", 
      "enum": ["CIVIL", "PIPING", "MECHANICAL", "ELECTRICAL", "INSTRUMENTATION", "SAFETY", "GENERAL"]
    },
    "location_details": {
      "type": "object",
      "properties": {
        "site_id": { "type": "string" },
        "chainage_start_km": { "type": "number" },
        "chainage_end_km": { "type": "number" },
        "section_name": { "type": "string" }
      }
    },
    "quantity_reported": { "type": "number" },
    "unit_of_measure": { "type": "string" },
    "status_claim": { 
      "type": "string", 
      "enum": ["STARTED", "IN_PROGRESS", "MILESTONE_COMPLETED", "SUSPENDED"] 
    },
    "crew_equipment_notes": { "type": "string" },
    "raw_text_snippet": { 
      "type": "string",
      "description": "Exact verbatim excerpt from DPR providing provenance"
    }
  }
}
```

---

## 9. Schedule-Activity Schema

Standardized model compatible with Oracle Primavera P6 XER and MS Project XML exports:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ScheduleActivity",
  "type": "object",
  "required": [
    "activity_id",
    "activity_code",
    "name",
    "wbs_code",
    "discipline",
    "planned_start",
    "planned_finish"
  ],
  "properties": {
    "activity_id": { "type": "string", "format": "uuid" },
    "activity_code": { "type": "string", "example": "ACT-ENG-1040" },
    "wbs_code": { "type": "string", "example": "1.2.4.1" },
    "wbs_name": { "type": "string", "example": "Pipeline Trenching & Lowering" },
    "name": { "type": "string", "example": "Mainline Trench Excavation Section A" },
    "discipline": { 
      "type": "string",
      "enum": ["CIVIL", "PIPING", "MECHANICAL", "ELECTRICAL", "INSTRUMENTATION", "GENERAL"]
    },
    "planned_start": { "type": "string", "format": "date" },
    "planned_finish": { "type": "string", "format": "date" },
    "planned_duration_days": { "type": "integer" },
    "actual_start": { "type": ["string", "null"], "format": "date" },
    "actual_finish": { "type": ["string", "null"], "format": "date" },
    "planned_quantity": { "type": "number" },
    "actual_quantity": { "type": "number" },
    "unit_of_measure": { "type": "string" },
    "physical_percent_complete": { "type": "number", "minimum": 0, "maximum": 100 },
    "is_critical": { "type": "boolean" },
    "total_float_days": { "type": "integer" },
    "location_scope": {
      "type": "object",
      "properties": {
        "chainage_start_km": { "type": "number" },
        "chainage_end_km": { "type": "number" }
      }
    },
    "predecessors": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "predecessor_code": { "type": "string" },
          "type": { "type": "string", "enum": ["FS", "SS", "FF", "SF"] },
          "lag_days": { "type": "integer" }
        }
      }
    }
  }
}
```

---

## 10. Activity Matching Architecture (The Core Innovation)

The core challenge in infrastructure progress tracking is **semantic vocabulary mismatch**:
- Master Schedule says: *`ACT-3020: HDD Crossing Installation - Burhi Dihing River (Piping/Civil)`*
- Field DPR says: *`Drilling rig bored 180m pilot hole across river bed today; bentonite slurry mixed.`*

A simple keyword query fails because neither "HDD" nor "Crossing" might appear in the DPR report. ProjectSynapse solves this through a **4-Stage Hybrid Matching Pipeline**:

```
+---------------------------------------------------------------------------------------------------+
|                                 4-STAGE HYBRID MATCHING PIPELINE                                  |
|                                                                                                   |
|  [ Progress Event ]                                                                               |
|         |                                                                                         |
|         v                                                                                         |
|  [ Stage 1: Candidate Filtering ]                                                                 |
|    - Narrow search space by Discipline (e.g. Civil vs Piping) and Spatial Corridor                |
|         |                                                                                         |
|         v                                                                                         |
|  [ Stage 2: Dual Semantic Retrieval (RRF Fusion) ]                                                |
|    - Sparse Search: BM25 on activity titles, WBS codes, and task notes                            |
|    - Dense Search: pgvector cosine similarity on 768-dim embeddings                               |
|    - Combined Rank via Reciprocal Rank Fusion: RRF = 1 / (60 + Rank_BM25) + 1 / (60 + Rank_Dense)   |
|    - Result: Top 10 Candidate Activities                                                          |
|         |                                                                                         |
|         v                                                                                         |
|  [ Stage 3: Multi-Factor Confidence Scoring Engine ]                                              |
|    - Compute weighted multi-attribute score (Semantic, Spatial, Trade, Quantity, Date)            |
|    - Result: Top 3 Activities with detailed sub-scores                                            |
|         |                                                                                         |
|         v                                                                                         |
|  [ Stage 4: Top-K Contextual LLM Arbitration & Reasoning ]                                        |
|    - Triggered when top 2 candidates have close scores (|Score_1 - Score_2| < 0.15)               |
|    - LLM inspects construction context, analyzes trade jargon, and generates natural-language     |
|      justification for why Candidate 1 is the true match.                                         |
+---------------------------------------------------------------------------------------------------+
```

---

## 11. Confidence Scoring Architecture

The confidence score is computed using an explicit, deterministic mathematical formula that combines semantic signals with physical construction rules:

$$\text{Confidence} = w_{\text{sem}} \cdot S_{\text{sem}} + w_{\text{trade}} \cdot S_{\text{trade}} + w_{\text{loc}} \cdot S_{\text{loc}} + w_{\text{qty}} \cdot S_{\text{qty}} + w_{\text{time}} \cdot S_{\text{time}}$$

### Feature Weights and Sub-Score Definitions:

1. **$S_{\text{sem}}$: Semantic Text Similarity ($w_{\text{sem}} = 0.40$)**
   - Cosine similarity between progress event embedding and schedule activity embedding.
   - Values range strictly between $0.0$ and $1.0$.

2. **$S_{\text{trade}}$: Discipline / Trade Match ($w_{\text{trade}} = 0.20$)**
   - $1.0$ if disciplines match exactly (e.g., event is `PIPING` and activity is `PIPING`).
   - $0.6$ if disciplines are cross-compatible (e.g., `MECHANICAL` and `PIPING`).
   - $0.1$ if disciplines conflict (e.g., `CIVIL` earthwork vs `ELECTRICAL` cabling).

3. **$S_{\text{loc}}$: Spatial / Chainage Overlap ($w_{\text{loc}} = 0.20$)**
   - Evaluates interval overlap between event chainage $[C_{e,\text{start}}, C_{e,\text{end}}]$ and activity chainage $[C_{a,\text{start}}, C_{a,\text{end}}]$:
     $$S_{\text{loc}} = \frac{\text{Length}(\text{Event} \cap \text{Activity})}{\text{Length}(\text{Event})}$$
   - Returns $1.0$ if no spatial scope is specified for non-linear activities.

4. **$S_{\text{qty}}$: Quantity Unit & Magnitude Plausibility ($w_{\text{qty}} = 0.10$)**
   - $1.0$ if Unit of Measure matches (e.g., meters to meters) and quantity does not exceed remaining planned quantity by $>10\%$.
   - $0.3$ if UOM is missing or unconvertible.
   - $0.0$ if reported quantity exceeds planned total by $>50\%$.

5. **$S_{\text{time}}$: Temporal Window Plausibility ($w_{\text{time}} = 0.10$)**
   - Evaluates whether the event date falls within or near the activity's planned execution window (planned start $- 14$ days to planned finish $+ 30$ days).

### Operational Triage Thresholds:
- **$\ge 0.85$ (High Confidence):** Eligible for **Automatic Approval** if zero dependency violations are detected.
- **$0.50 \le \text{Score} < 0.85$ (Medium Confidence):** Routed to **Human-in-the-Loop Review Inbox** with pre-filled recommendations and detailed explanation.
- **$< 0.50$ (Low Confidence):** Flagged as **Unmatched / Anomaly**; requires manual search or prompt to create an ad-hoc field activity.

---

## 12. Human-Review Workflow (HITL)

The Human-in-the-Loop review workflow ensures that field ambiguities and unexpected site occurrences never corrupt the master schedule without human oversight.

```
       [ Extracted Progress Event ]
                    |
                    v
    +-------------------------------+
    | Multi-Factor Match Evaluated  |
    +-------------------------------+
                    |
      +-------------+-------------+
      |                           |
Score >= 0.85 & Valid       Score < 0.85 OR Dependency Violation
      |                           |
      v                           v
[ Auto-Approved ]          [ PENDING_REVIEW Queue ]
                                  |
            +---------------------+---------------------+
            |                     |                     |
            v                     v                     v
      [ APPROVE ]            [ OVERRIDE ]           [ REJECT ]
(Accept recommendation) (Select other activity) (Mark invalid/duplicate)
            |                     |                     |
            +---------------------+---------------------+
                                  |
                                  v
                    +---------------------------+
                    | Immutable Audit Log Entry |
                    | (User, Timestamp, Reason) |
                    +---------------------------+
                                  |
                                  v
                    +---------------------------+
                    | Schedule State Synchronized|
                    +---------------------------+
```

### Review Inbox Actions:
- **1-Click Confirm:** Accept the top recommendation with a single keystroke.
- **Select Alternative Candidate:** Browse the ranked candidate drawer and assign Candidate #2 or #3.
- **Manual Activity Search:** Type-ahead search over all project activities if the matching engine missed the target.
- **Reject / Duplicate:** Discard noise (e.g., weather delays or duplicate reports).
- **Mandatory Audit Logging:** Every override or rejection records the user ID, timestamp, and optional engineer notes.

---

## 13. Schedule Dependency Validation Architecture

Schedule integrity is enforced by a **100% Deterministic Validation Engine** utilizing directed acyclic graph (DAG) algorithms.

### Evaluated Rules:

1. **Predecessor Incomplete (Finish-to-Start Violation):**
   - If Activity B requires Activity A to finish first ($\text{FS}$ relationship), but Activity A is only $60\%$ complete when progress is reported on Activity B:
   - *Severity:* `CRITICAL_WARNING`
   - *Message:* *"Out-of-sequence execution: Activity B reported with 50m progress, but mandatory predecessor Activity A is only 60% complete."*

2. **Start-to-Start Lag Violation:**
   - Predecessor has started, but mandatory lag days have not elapsed.

3. **Cumulative Quantity Overrun:**
   - Total reported quantity exceeds $110\%$ of planned baseline quantity without an approved change order.
   - *Severity:* `WARNING`

4. **Negative Float & Critical Path Slip:**
   - Evaluates whether reported progress delays the project finish date. If an activity on the critical path falls behind, the system calculates the exact projected project delay in days.

5. **Cycle Detection:**
   - Prevents recursive or circular dependencies upon schedule import.

---

## 14. Testing Strategy

To ensure zero regressions and verify system reliability during judging:

1. **Unit Testing (`pytest`):**
   - **Parsers:** Test extraction from valid and malformed P6 `.xer`, MS Project `.xml`, and `.csv` files.
   - **Scoring Engine:** Test all mathematical boundaries, edge cases, and missing field fallbacks.
   - **Deterministic DAG Validator:** Test dependency validation across predefined acyclic graphs with intentional violations.
   - **Pydantic Schemas:** Validate strict type coercion and rejection of invalid payloads.

2. **Integration Testing:**
   - Test FastAPI endpoints against an active PostgreSQL test database with `pgvector`.
   - Test vector indexing and hybrid search querying.
   - Test the `MockProvider` to ensure the entire pipeline executes seamlessly without external network connections.

3. **Semantic Matching Accuracy Benchmark:**
   - A curated benchmark suite of **25 realistic Oil India DPR excerpts** evaluated against a reference 50-activity pipeline schedule.
   - Success Metric: **Top-1 Accuracy $\ge 85\%$**, **Top-3 Recall $\ge 96\%$**.

---

## 15. Development Phases (3-Day SIH Prototype Roadmap)

| Day | Focus Area | Deliverables |
|---|---|---|
| **Day 1** | **Foundation & Ingestion Core** | - Project repository setup (FastAPI + Vite + PostgreSQL + pgvector)<br>- Database schema migrations and models<br>- Primavera P6 (`.xer`), MS Project (`.xml`), and CSV parsers<br>- Replaceable AI Provider interface with Gemini and Mock adapters<br>- Raw DPR text ingestion and structured `ProgressEvent` extraction |
| **Day 2** | **Matching Engine & Rule Validation** | - Activity embedding generator and pgvector indexing<br>- Hybrid search engine (BM25 + Dense vector cosine search)<br>- Multi-factor confidence scoring engine<br>- Deterministic schedule dependency validator (NetworkX DAG)<br>- HITL review workflow endpoints and audit logging |
| **Day 3** | **Frontend UI, Analytics & Polish** | - Split-Screen Match Verification Workspace<br>- HITL Review Inbox with 1-click approvals and triage drawer<br>- Interactive S-Curve (Planned vs. Actual) and Gantt view<br>- Primavera P6 update export generator<br>- Sample Oil India dataset seeding and end-to-end demo rehearsal |

---

*Document Author: ProjectSynapse Lead Software Architect*  
*Version: 1.0.0 | Status: Approved for Implementation*
