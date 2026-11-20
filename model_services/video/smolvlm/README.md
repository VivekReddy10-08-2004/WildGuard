# SmolVLM2 event-description service

SmolVLM2 is an advisory, asynchronous consumer of WildGuard event evidence. It
describes selected frames but cannot create, suppress, or change alerts.

## Setup

```bash
./scripts/setup_smolvlm.sh
```

## Start the local service

```bash
./scripts/run_smolvlm_service.sh
```

The service listens on `127.0.0.1:8011`. It accepts one to three frame paths
under `storage/evidence/`, validates generated JSON, and returns a structured
scene description. The main API returns its rule-based alert immediately and
enriches the event in a background task.
