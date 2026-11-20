# WildGuard Web — UI/UX Frontend Concept

An accessible, responsive, dependency-free frontend concept for the WildGuard presentation layer.

> **Status:** Prototype, not production. The hiker hero uses the real local
> AnimalCLAP API for uploaded audio and records local session summaries through
> the FastAPI/SQLite backend.

## Run locally

Start the two local model/API processes and the static client in separate
terminals. No CDN or internet inference service is required.

```bash
./scripts/run_animalclap_service.sh
./scripts/run_wildguard_api.sh
uv run python -m http.server 8001 --directory apps
```

Open `http://localhost:8001/web/`.

## Included

- Responsive phone and smartwatch hiker-awareness demonstration backed by
  `POST /audio/analyze`. The built-in coyote clip is a verified AnimalCLAP test
  case, and users can upload a local audio file for the same inference path.
- Antler-W brand mark and custom wordmark. The Listen, See, and Understand illustrations replay independently by mouse, touch, or keyboard.
- Product narrative for hikers, drivers, and researchers
- Detailed Hiker event flow naming capture, FastAPI validation, AnimalCLAP,
  uncertainty handling, phone/watch output, and SQLite session persistence.
- Evidence-led Maine impact infographic using only the `Economic_Loss` and
  `Insurance` workbook tabs in `Why WildGuard`, with explicit assumptions for
  the 1%, 5%, and 10% illustrative benefit scenarios.
- Mobile navigation, keyboard focus states, reduced-motion support, semantic
  landmarks, and explicit demonstration labeling.
- No cookies, analytics trackers, external assets, or cloud model APIs

## Architecture alignment

This demo is the **shared landing page and working hiker experience**. Product
work is separated by audience while preserving one hiker entry point:

- `apps/web`: landing page plus the wildlife audio alert, phone/watch caution,
  detailed event flow, and impact evidence
- `apps/hiker-mobile`: compatibility redirect to `apps/web/#demonstration`
- `apps/driver-client`: dashcam/roadside detection, voice interaction, hazard notices, playback
- `apps/admin-dashboard`: local API health, model inventory, and real events
  created during the current browser demo session
- `apps/architecture`: master explanation of inputs, models, deterministic
  decisions, advisory descriptions, evidence, and client outputs

Shared media and brand assets live under `apps/shared`. The backend gateway
handles the local REST routes, inference orchestration, evidence, and alerts;
clients must not call model services directly. Authentication, durable storage,
WebSocket streaming, and server-enforced consent remain production work.
See [integration notes](../../docs/frontend-integration.md) and the root
`README.md` / `design.svg`.

## Test checklist

- View at 320px, 375px, 768px, 1024px and desktop widths
- Run the coyote field test, upload an audio file, and verify phone/watch result,
  waveform, caution, error, and loading states.
- Navigate with the keyboard through the menu, audio controls, event flow,
  impact section, and privacy details. Check that Escape closes the menu.
- Check browser with reduced motion enabled
- Verify the hiker controls report a clear local-service error when the API is
  unavailable.
- Confirm audio reaches only the local API and demo switches are not represented as real consent
- Before production: add automated unit/E2E tests, complete an assistive technology audit, and validate visual regression, cross-browser behavior, performance on real devices, and backend integration

## Deliberately not implemented

Continuous microphone monitoring, operating-system wearable notifications,
location tracking, real LLM Q&A, authentication, persistence, server
authorization, research exports, code generation execution, WebSocket updates,
and consent audit logging. These are later backend or product integrations.

## Scope

No changes to `main`, backend, data, services, or deployment. Development branch: `feat/ui-ux-overhaul`. Review with Vivek before merging.
