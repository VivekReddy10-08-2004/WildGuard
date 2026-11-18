# WildGuard AI

WildGuard AI is a local-first, multimodal wildlife-awareness system for hikers,
drivers, and researchers. It combines audio, image, video, text, and code models
to detect wildlife, explain detections, issue hazard alerts, and support
consented research workflows.

The architecture is designed to run entirely offline on local hardware. User
evidence and activity remain private by default, and research or administrative
access is limited to explicitly consented records.

## System architecture

The source architecture is maintained in [`design.svg`](./design.svg). Open the
SVG directly for a full-size, zoomable version.

![WildGuard AI system architecture](./design.svg)

The system is divided into four layers, with three guarantees applying across
all of them:

- **Offline/local:** open-weight models run on local hardware with no required
  cloud dependency.
- **Multimodal:** audio, images, video, documents, and generated code share a
  coordinated event pipeline.
- **Private by default:** administrative views receive only explicitly
  consented records, with access and policy decisions recorded for audit.

### 1. Presentation layer

| Client | Primary responsibilities |
| --- | --- |
| Hiker mobile interface | Live wildlife-audio alerts, camera queries, detection chat, personal event history, and privacy controls |
| Driver interface | Dashcam or roadside detection, voice interaction, hazard notifications, event playback, and detection summaries |
| Admin/research dashboard | Aggregate statistics, consented wildlife logs, analytics, reviewed code generation, and custom data APIs |

Clients communicate with the backend through REST for request/response work and
WebSockets for live detections and alerts. They do not call models or storage
services directly.

### 2. Application and orchestration layer

| Component | Responsibility |
| --- | --- |
| API gateway / FastAPI backend | REST endpoints, WebSocket connections, request validation, and session handling |
| Auth and consent manager | Role-based access, user permissions, consent filtering, and audit enforcement |
| Event orchestrator | Routes model work, combines multimodal evidence, builds event context, triggers alerts, and persists results |
| Alert manager | Applies hazard thresholds, cooldowns, confidence rules, and delivers UI or push alerts |
| Context builder / chat manager | Combines detection history, retrieved documents, and user questions into grounded prompts |
| Admin analytics and codegen manager | Builds reports and queries, generates API or analysis code, and requires review before use |

The event orchestrator is the center of the runtime. It turns raw input into a
single event containing model results, confidence values, evidence references,
user/session ownership, and alert decisions.

### 3. AI and model-services layer

Each capability is isolated behind a service boundary so models can be loaded,
replaced, or tuned without changing the clients or core policy logic.

| Service | Intended capabilities | Candidate models from the design |
| --- | --- | --- |
| Audio intelligence | Wildlife-sound classification, speech transcription, sound-event detection, rolling audio buffer | YAMNet, BirdNET, Whisper |
| Image intelligence | Wildlife detection, scene understanding, image question answering | YOLO, Qwen3-VL |
| Video intelligence | Frame sampling, animal tracking, motion understanding, video question answering | YOLO tracking, Qwen3-VL |
| Text/document intelligence | Offline safety-document retrieval, grounded Q&A, explicit “answer not found” behavior | Embeddings, vector search, local LLM |
| Code generation | Python analytics, reports, and admin-side API templates | Qwen2.5-Coder |

Model output is advisory until the application layer applies confidence,
authorization, consent, and alerting rules.

### 4. Data layer

| Store | Contents |
| --- | --- |
| Event database | Event metadata, timestamps, labels, confidence values, and user/session links; SQLite locally or PostgreSQL for larger deployments |
| Evidence storage | Audio clips, images, video snippets, and detection snapshots |
| Vector store/document index | Chunked wildlife manuals and trail/road-safety guides with embeddings |
| Audit and consent logs | Sharing permissions, access history, administrative actions, and privacy records |

Event metadata should reference evidence by identifier rather than embedding
large media objects in the relational database. Consent records and audit
events should be append-oriented so access decisions remain traceable.

## Core data flows

### Detection and alerting

1. A hiker or driver client streams or uploads audio, image, or video evidence.
2. The API authenticates the session and passes the request to the event
   orchestrator.
3. The orchestrator invokes the appropriate local model services and combines
   their results into an event context.
4. The alert manager evaluates labels, confidence, hazard thresholds, and
   cooldowns.
5. Event metadata and evidence are stored, an audit entry is written, and any
   approved alert is returned over the live client connection.

### Grounded wildlife Q&A

1. The chat manager loads the user's relevant detection history.
2. Text intelligence retrieves relevant passages from the local document index.
3. A local language model answers using the event context and retrieved text.
4. If the local sources do not support an answer, the system reports that the
   answer was not found instead of presenting an unsupported claim.

### Research and administration

1. The auth and consent manager filters records before they reach analytics.
2. The dashboard works only with the resulting consented dataset.
3. Generated queries, scripts, or API templates require safe review before
   execution or publication.
4. Reads, exports, permission changes, and administrative actions are audited.

## Repository layout

The repository is scaffolded according to the following structure. It maps the
architecture's component boundaries into implementation areas; placeholder
files keep currently empty directories available in version control.

```text
WildGuard/
├── README.md
├── design.svg
├── apps/
│   ├── hiker-mobile/             # Hiker experience and privacy controls
│   ├── driver-client/            # Driver alerts, voice, and playback
│   └── admin-dashboard/          # Consented research and admin workflows
├── backend/
│   ├── api/                      # FastAPI routes, schemas, and WebSockets
│   ├── auth/                     # Identity, roles, consent, and policy checks
│   ├── orchestration/            # Event routing and context assembly
│   ├── alerts/                   # Threshold, confidence, and cooldown rules
│   ├── chat/                     # Grounded Q&A and prompt construction
│   └── analytics/                # Reports and reviewed codegen workflows
├── model_services/
│   ├── audio/                    # YAMNet/BirdNET/Whisper adapters
│   ├── image/                    # YOLO and vision-language adapters
│   ├── video/                    # Sampling, tracking, and video Q&A
│   ├── documents/                # Embedding, retrieval, and local Q&A
│   └── codegen/                  # Sandboxed code/template generation
├── data/
│   ├── migrations/               # Relational schema changes
│   ├── documents/                # Locally indexed reference material
│   └── seeds/                    # Development-only reference data
├── storage/
│   ├── events/                   # Local database files in development
│   ├── evidence/                 # Private captured media
│   ├── vectors/                  # Local vector indexes
│   └── audit/                    # Append-oriented audit records
├── shared/
│   ├── contracts/                # Cross-service event and API schemas
│   ├── config/                   # Typed settings and local profiles
│   └── observability/            # Local logs, metrics, and tracing helpers
├── tests/
│   ├── unit/
│   ├── integration/
│   └── end_to_end/
├── scripts/                      # Setup, indexing, and maintenance commands
├── docs/                         # Detailed decisions and operational guides
└── deploy/                       # Local containers and hardware profiles
```

Runtime data under `storage/` should not be committed. Reference documents in
`data/documents/` must have clear licensing and provenance, while generated
indexes can be rebuilt locally from those sources.

## Architectural boundaries

- Clients access the system only through the API gateway.
- Authorization and consent checks happen before retrieval, analytics, export,
  or administrative display—not only in the user interface.
- Model services cannot independently publish alerts or expose stored evidence.
- Shared contracts define stable event payloads; model-specific structures stay
  inside their service adapters.
- Code generation is restricted to administrative workflows and its output is
  reviewed and sandboxed before execution.
- The default deployment must remain useful without internet access; optional
  integrations must not become runtime requirements.

## Implementation status

This repository currently contains the system architecture and its directory
scaffold. `design.svg` remains the source of truth for the intended components
and relationships. Application code, service implementations, schemas, tests,
and deployment configuration have not yet been implemented.
