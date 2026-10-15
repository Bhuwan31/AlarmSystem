# AlarmSystem — Adaptive Multi-Hazard Early Warning and Evacuation Support System for Nepal

University Requirements Engineering project (team of 4, 4-week prototype). First hazard: river floods. The design is ready to add landslides and earthquakes later.

> **Prototype. This is not an official warning system.** It provides early-warning decision support using simulated and public data. It does not predict floods with certainty, does not guarantee safety, and does not replace DHM, NDRRMA, local government or emergency services.

## Documents
- [REQUIREMENTS_ENGINEERING.md](REQUIREMENTS_ENGINEERING.md): the main Software Requirements Specification (ISO/IEC/IEEE 29148)
- [docs/](docs/README.md): supporting analysis (stakeholders, architecture, use cases, failures, Nepal context, traceability, ethics, testing, team plan)

## Stack
| Layer | Technology |
|---|---|
| Database / Auth / Realtime / Storage | Supabase (PostgreSQL + PostGIS) |
| Backend | Python 3.12, FastAPI, APScheduler, OSMnx + NetworkX (routing) |
| Frontend | Next.js (App Router, TypeScript), MapLibre GL, next-intl (Nepali/English), PWA |
| Hosting | Vercel (frontend), Render / Fly.io (backend), Supabase cloud |

## Planned repository layout
```
backend/     FastAPI app (adapters, processing, hazards, risk, warnings, notify, evacuation, audit)
frontend/    Next.js citizen PWA + /ops dashboard + /admin
supabase/    migrations (schema, RLS) and seed data
docs/        requirements engineering documentation
```
