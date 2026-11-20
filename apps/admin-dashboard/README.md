# Admin dashboard

Owns authorized event review, consent-filtered analytics, reports, and reviewed
administrative tools. Authentication, authorization, consent filtering, and
auditing must be enforced by the backend before real data is connected.

The implemented hackathon dashboard reads the local presentation-session log
written by the hiker and driver clients, checks the FastAPI health endpoint,
shows cache/description-queue state, documents the model inventory, and renders
each event's processing flow. It deliberately does not present browser storage
as the persistent or consent-authorized event database.
