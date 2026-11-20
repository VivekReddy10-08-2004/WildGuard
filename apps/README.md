# WildGuard clients

Serve this directory from the repository root:

```bash
python -m http.server 8001 --directory apps
```

| Route | Ownership |
| --- | --- |
| `/web/` | Shared landing page and real local hiker-audio demonstration |
| `/hiker-mobile/` | Compatibility redirect to `/web/#demonstration` |
| `/driver-client/` | Road-video analysis, alerts, evidence review |
| `/admin-dashboard/` | Local runtime health and presentation-session event review |
| `/architecture/` | Master system, model, decision, and evidence flow |
| `/shared/` | Brand assets and common client styling; no product logic |

Client-specific code stays in its client directory. Shared presentation assets
belong in `shared`; backend and model calls always go through the FastAPI gateway.
