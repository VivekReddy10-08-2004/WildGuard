# WildGuard Web — UI/UX Frontend Concept

An accessible, responsive, dependency-free frontend concept for the WildGuard presentation layer.

> **Status:** Prototype, not production. The workspace uses deliberately fabricated observations, fictitious locations, invented confidence values, static charts, and a scripted field guide. No models, camera, microphone, GPS, alerting, accounts, network calls, or database are connected.

## Run locally

Open `apps/web/index.html` in a modern browser. No installation, build step, CDN, or internet connection is required. For a local HTTP server, run `python -m http.server 8000 --directory apps/web` at the repo root and open `http://localhost:8000`.

## Included

- Original animated barred owl encounter. The owl flies into a wide forest shot, lands, and calls over synthesized woodland ambience. The local film loads on Play and leads to the corresponding example audio observation. Reduced-motion users can advance through still stages. The film is illustrative and does not run detection or contain field footage.
- Antler-W brand mark and custom wordmark. The Listen, See, and Understand illustrations replay independently by mouse, touch, or keyboard.
- Product narrative for hikers, drivers, and researchers
- Interactive unified workspace preview with overview, fictional marker map, synthetic detections, filters/search, event details, synthetic CSV export, charts, scripted guide, and privacy preference switches
- Mobile workspace navigation, keyboard focus states, reduced-motion support, semantic landmarks, and explicit demonstration labeling
- No cookies, analytics trackers, external assets, fonts, model APIs, or external runtime dependencies

## Architecture alignment

This demo is a **shared web presentation prototype**, housed under `apps/web` to avoid implying it replaces the three planned clients:

- `apps/hiker-mobile`: wildlife audio alerts, camera queries, detection Q&A, event history, privacy choices
- `apps/driver-client`: dashcam/roadside detection, voice interaction, hazard notices, playback
- `apps/admin-dashboard`: consent-filtered aggregate research analytics, event review, reviewed code generation and API tooling

The backend gateway exclusively handles REST, WebSocket, auth/consent, authorization, orchestration, evidence, and alerts; clients must not call model services or databases directly. See [integration notes](../../docs/frontend-integration.md) and the root `README.md` / `design.svg`.

## Test checklist

- View at 320px, 375px, 768px, 1024px and desktop widths
- Play, pause, mute, and replay the encounter. Open its matching record and activate each feature illustration with Enter or Space.
- Navigate with keyboard through menu, workspace views, filters, details dialog, switches and guide. Check that Escape closes the menu or dialog and returns focus.
- Check browser with reduced motion enabled
- Filter by audio/camera; search no-result case; reset; export CSV and verify the synthetic warning
- Verify all buttons work with no network
- Confirm no user data leaves the browser and demo switches are not represented as real consent
- Before production: add automated unit/E2E tests, complete an assistive technology audit, and validate visual regression, cross-browser behavior, performance on real devices, and backend integration

## Deliberately not implemented

Real detection, predictions, hazard decisions, location tracking, offline model inference, real LLM Q&A, authentication, persistence, server authorization, research exports, code generation execution, WebSocket updates, and consent audit logging. These are backend or product integrations owned separately.

## Scope

No changes to `main`, backend, data, services, or deployment. Development branch: `feat/ui-ux-overhaul`. Review with Vivek before merging.
