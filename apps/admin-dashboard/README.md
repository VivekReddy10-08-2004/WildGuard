# Admin dashboard

Owns authorized event review, consent-filtered analytics, reports, and reviewed
administrative tools. Authentication, authorization, consent filtering, and
auditing must be enforced by the backend before real data is connected.

The implemented hackathon dashboard reads the SQLite-backed local
presentation-session log written by the hiker and driver API routes, checks the
FastAPI health endpoint, shows both cache levels and description-queue state,
documents the model inventory, and renders each event's processing flow.
Browser storage remains an offline fallback. SQLite is single-machine demo
persistence, not a consent-authorized research database or formal audit log.

The export panel calls `GET /session/events/export`. JSON and CSV are
deterministic copies of the session records. The `ai` format sends a read-only
copy to the local `qwen2.5-coder:7b` Ollama model and downloads its advisory
Markdown presentation report; generated text never changes stored records.

The Admin event flow documents how normalized audio/video session summaries
move through SQLite, health and event APIs, the read-only dashboard renderer,
and log maintenance without deleting cached inference or media evidence.
