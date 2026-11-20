# WildGuard Frontend: Design & Integration Handoff

## Principles
- **Local first:** all frontend essentials ship locally. No third-party CDN needed to use the site.
- **Privacy by default:** consent off; no evidence displayed to research users without backend-authenticated, policy-filtered results.
- **Honest status:** distinguish illustrative demo data from detections, confidence estimates from verified safety decisions, and disconnected sensors from monitoring.
- **Readable outdoors:** high contrast, large touch targets, calm visual language, mobile-first fallback, reduced motion.
- **Shared visual language:** pine #102b23, forest #173b2d, leaf #d5eda9, cream #f3f2e9. Branded antler-W icon at `apps/web/assets/wildguard-mark.svg`.

## Proposed frontend boundaries
```text
Landing / shared brand system
  ├─ Hiker experience (camera, audio, chat, personal history, privacy)
  ├─ Driver experience (roadside hazard UI, audio/voice, playback)
  └─ Admin / research experience (consented analytics, events, reviewed codegen)
              ↓ REST and WebSocket only
FastAPI gateway → Auth & consent manager → Event orchestrator → model services + storage
```

The current `apps/web` demo unifies these surfaces for design review. Separate clients can reuse the color tokens, icon, language, and interaction patterns.

## Illustrative interface contracts (proposals, NOT existing endpoints)

Agree actual paths and schemas with the backend owner before integration. Do not assume these routes exist.

| Operation | Proposed method / path | Required guard |
| --- | --- | --- |
| List user events | GET /api/v1/events?cursor=... | Authenticated event owner |
| Event detail | GET /api/v1/events/:id | Ownership / policy check |
| Upload media evidence | POST /api/v1/evidence | Local authenticated session, validation, size/type limits |
| Detection stream | WS /api/v1/stream | Authenticated session, reconnect, timestamps and dedupe |
| Grounded field chat | POST /api/v1/chat | Authorized events + retrieved local sources; answer-not-found |
| Consent state | GET /api/v1/me/consent | Authenticated user |
| Set/revoke consent | PUT /api/v1/me/consent | Explicit action, backend audit |
| Research analytics | GET /api/v1/admin/analytics | Admin role AND consent filter before aggregation |
| Research export | POST /api/v1/admin/exports | Policy/consent filtered, audit, authorization |
| Review codegen | POST /api/v1/admin/codegen/reviews | Restricted to reviewed, sandboxed workflows |

Example **proposed** event view model:
```json
{
  "id": "event-id",
  "observed_at": "2026-11-20T14:42:00Z",
  "modality": "camera",
  "species_label": "unverified prediction",
  "confidence": 0.0,
  "confidence_calibrated": false,
  "evidence_ids": ["evidence-id"],
  "status": "pending_review",
  "alert": { "state": "none", "reason": "no safety determination" }
}
```
Actual event schemas should be versioned in `shared/contracts`. Do not use any sample confidence values as thresholds. Geographic data must never be guessed or fabricated in production.

## Adapter migration steps
1. Put all wire calls behind an adapter module, with a demo adapter and a real FastAPI adapter. Remove hardcoded samples from production builds.
2. Validate and type runtime event payloads; normalize timestamps and clearly distinguish server-calibrated confidence from raw scores.
3. Implement live connection health states: idle, connecting, connected, degraded, offline, reconnecting, with last-updated timestamps.
4. Add evidence loading only via authorized gateway URLs and avoid unauthorized caching.
5. Connect privacy switches to explicit consent dialogs, backend PUT responses, and auditable revocation; never optimistically claim a real consent change.
6. Enforce auth, role checks, and consent **server side** for every read, chart, export and generated report. UI hiding is not authorization.
7. Use server-evaluated alerts only, with severity, timestamp, expiration, cooldown and clear fail-safe states.
8. Add grounded chat citations and an explicit unavailable-answer state; do not provide unsupported wildlife hazard advice.
9. Set up local offline asset packaging, test simulated network failures and ensure all relevant telemetry remains local.
10. Add contract, integration, accessibility, E2E, security, and acceptance tests before production release.

## Proposed acceptance criteria
- All navigation and sample features operate without backend or network.
- Sample data is labeled on every major surface and export.
- Responsive from narrow phones through widescreen without horizontal overflow.
- Mouse, keyboard and reduced-motion paths are usable.
- No false claims of live monitoring or active safety protection.
- Consent defaults to off; real sharing cannot be enabled until server confirmation.
- Root architecture boundaries remain intact; no model or storage calls in clients.
- Merge requires Vivek's explicit review/approval.

## Known gaps
The Excalidraw collaboration room linked in the design request was not independently inspected. The verified root `README.md` and `design.svg` architecture should be reconciled against Vivek's live webpage-duty sketch before final signoff. A full browser screenshot comparison, automated WCAG audit, and production testing have not been completed.
