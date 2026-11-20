# WildGuard Web — UI/UX Frontend Concept

An accessible, responsive, dependency-free frontend concept for the WildGuard presentation layer.

> **Status:** Prototype, not production. The hiker hero uses the real local
> AnimalCLAP API for uploaded audio. The workspace below it still uses
> deliberately fabricated observations, locations, scores, charts, and a
> scripted field guide.

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
- Interactive unified workspace preview with overview, application event map,
  synthetic detections, filters/search, event details, synthetic CSV export,
  charts, scripted guide, and privacy preference switches.
- Application event map showing the actual hiker audio and driver video
  processing lanes, shared event contract, deterministic alert path, and
  advisory enrichment boundary.
- Evidence-led Maine impact infographic using only the `Economic_Loss` and
  `Insurance` workbook tabs in `Why WildGuard`, with explicit assumptions for
  the 1%, 5%, and 10% illustrative benefit scenarios.
- Mobile workspace navigation, keyboard focus states, reduced-motion support, semantic landmarks, and explicit demonstration labeling
- No cookies, analytics trackers, external assets, or cloud model APIs

## Architecture alignment

This demo is the **shared landing page and working hiker experience**. Product
work is separated by audience while preserving one hiker entry point:

- `apps/web`: landing page plus the wildlife audio alert, phone/watch caution,
  and presentation workspace
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
- Navigate with keyboard through menu, workspace views, filters, details dialog, switches and guide. Check that Escape closes the menu or dialog and returns focus.
- Check browser with reduced motion enabled
- Filter by audio/camera; search no-result case; reset; export CSV and verify the synthetic warning
- Verify all buttons work with no network
- Confirm audio reaches only the local API and demo switches are not represented as real consent
- Before production: add automated unit/E2E tests, complete an assistive technology audit, and validate visual regression, cross-browser behavior, performance on real devices, and backend integration

## Deliberately not implemented

Continuous microphone monitoring, operating-system wearable notifications,
location tracking, real LLM Q&A, authentication, persistence, server
authorization, research exports, code generation execution, WebSocket updates,
and consent audit logging. These are later backend or product integrations.

## Scope

No changes to `main`, backend, data, services, or deployment. Development branch: `feat/ui-ux-overhaul`. Review with Vivek before merging.
