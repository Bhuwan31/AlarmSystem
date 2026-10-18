# AlarmSystem — Adaptive Multi-Hazard Early Warning and Evacuation Support System (AMHEWS)

A flood early-warning and evacuation-support system with **live satellite data, river sensors and sirens**, run by humans through an approval workflow.

- **Global by design:** works for any country or region. Everything country-specific (languages, authorities, administrative levels, time zone, laws, emergency numbers) comes from a configurable *Deployment Profile*.
- **First deployment: Nepal.** The goal is adoption by the Government of Nepal. Nepal is a demanding testing ground: monsoon floods, mountains, landslides that cut roads, uneven connectivity and many languages.
- **First hazard:** river floods. Landslides and earthquakes can be added later as plug-ins.

> **Public warnings and sirens are activated only by authorized people.** The system detects risk and proposes warnings; authorized officials approve them. It does not predict floods with certainty, does not guarantee safety, and does not replace national or local authorities (in Nepal: DHM, NDRRMA, local government). Until the government signs off, the system runs in exercise or shadow mode only.

## Requirements documentation
- **[presentation/AMHEWS-Requirements-Engineering.pptx](presentation/AMHEWS-Requirements-Engineering.pptx)** — the full requirements specification as a 53-slide deck: stakeholders, architecture, live data and hardware, 75 functional and 42 non-functional requirements, safety, security, privacy, use cases, failure scenarios, conflicts, 4-week plan, launch roadmap, traceability and evaluation.
- [docs/](docs/README.md) — supporting analysis notes.

## Live data and hardware

| Input | Source | What it gives |
|---|---|---|
| Satellite rainfall | NASA GPM IMERG | Rainfall over each catchment every 30 min, a few hours' delay |
| Satellite flood extent | Copernicus Sentinel-1 radar | Flooded areas every few days, through cloud |
| Flood forecasts, weather | GloFAS, Open-Meteo | River discharge forecasts, rainfall forecasts |
| National river and rain stations | Department of Hydrology and Meteorology (DHM) | Country-wide live river levels; needs a data-sharing agreement |
| Own river-gauge nodes (1–3 in the semester) | ESP32 + ultrasonic/radar level sensor + rain gauge, solar + battery, GSM/LTE or LoRa, MQTT over TLS | Live river level at the pilot site; 24 h offline buffer |
| Siren node (1 pilot) | GSM relay controller with local manual button | Sounds only on an approved warning (signed command); weekly silent self-test |

## Stack
| Layer | Technology |
|---|---|
| Database / Auth / Realtime / Storage | Supabase (PostgreSQL + PostGIS) |
| Backend | Python 3.12, FastAPI, APScheduler, OSMnx + NetworkX (routing) |
| Devices | ESP32 firmware, MQTT broker (Mosquitto / EMQX) |
| Frontend | Next.js (App Router, TypeScript), MapLibre GL, next-intl (any language; Nepal: Nepali/English), PWA |
| Hosting | Vercel (frontend), Render / Fly.io (backend), Supabase cloud; government hosting at launch |

## Plan
**Semester (4 weeks), Phase 0:**
- Live satellite and weather data.
- 1–3 own gauges.
- A siren pilot in test mode.
- The full warning workflow, citizen app and authority dashboard.
- Exercise mode only.

**After the semester:**

| Phase | What happens |
|---|---|
| 1. Partnership | Meet DHM, NDRRMA and a pilot municipality; sign a data-sharing agreement; connect the DHM feed; security review; real SMS gateway |
| 2. Shadow pilot (one monsoon) | The system runs alongside the official process with no public alerts; lead time and false alarms are compared; operators are trained |
| 3. Government launch | Authorities operate it on government hosting; sirens and cell broadcast go live district by district, then nationally |

## Run it locally

Requirements: Docker Desktop. Live DHM, Open-Meteo and map data need internet access.

```bash
cp .env.example .env
docker compose up -d --build
```

- Dashboard: http://localhost:3000 (click the globe for the full-screen 3D map)
- API docs: http://localhost:8000/docs
- First data arrives within about a minute; risk assessment runs every 2 minutes.

Optional satellite sources: put `EARTHDATA_TOKEN` (NASA GPM IMERG) or `INSAT_INBOX_DIR` (MOSDAC downloads) in `.env`, then enable the source:

```bash
docker compose exec db psql -U amhews -d amhews -c "update data_sources set enabled = true where code = 'gpm_imerg'"
```

### Try the warning workflow and a simulated gauge

```bash
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest
.venv/Scripts/python scripts/dev_token.py anjali approver --mfa
.venv/Scripts/python scripts/simulate_device.py gauge-001 --start 3.5 --rise 1.2
```

Register devices with `POST /api/v1/devices` (admin token), approve warnings with `POST /api/v1/warnings/{id}/approve`. CRITICAL needs two different approvers with MFA. Simulated readings only count while `exercise_mode` is on.

## What is built

| Part | Status |
|---|---|
| DHM live river (316) and rain (513) stations | Working, live |
| Open-Meteo weather grid (Nepal 0.5°, world 15°) | Working, live |
| NASA GPM IMERG satellite rain | Built, needs Earthdata token, untested with real data |
| INSAT-3D/3DR/3DS (MOSDAC) | Built, needs MOSDAC account + files, untested with real data |
| Validation, staleness, risk rules R1–R10, warning proposals | Working, unit-tested |
| Warning approval (1 / 2 approvers, MFA for CRITICAL), cancel, audit log (hash-chained, append-only) | Working, tested end to end |
| MQTT device gateway, device registry, signed siren commands | Working, tested with a simulated gauge and a live MQTT command |
| ESP32 gauge and siren firmware | Written, not yet compiled or bench-tested |
| Dashboard: light spinning globe, full-screen 3D map, live tables | Working |
| Map layers with details and filters: temperature, heatwave risk, humidity, rain forecast, cloud, animated wind flow, wind arrows, world rivers, Nepal rivers incl. cross-border, river and rain gauges, satellite rain, 3D terrain, border | Working |
| Click any place: fly there in 3D terrain + current temperature, humidity, pressure, air flow from surface to jet stream, 24 h outlook, heat status | Working |
| Operator login with two-factor, user management, policies, audit viewer | Working |
| Shelters, citizen "my area" page (Nepali / English) | Working |
| Not built yet | Alert subscriptions with SMS / push delivery, turn-by-turn safe routing (the public page links to OpenStreetMap directions) |

## Pages

| Page | Who | What it does |
|---|---|---|
| `/` Dashboard | everyone | Spinning globe, national conditions, river risk counts, warnings, heaviest rain, source health |
| `/map` 3D map | everyone | Full-screen globe: 14 layers with details and filters, click any place for 3D terrain + current weather |
| `/warnings` | approver to act | Active, proposed and past warnings; approve / reject / cancel; operators issue manual warnings |
| `/rivers`, `/rain` | everyone | All live gauges: search, basin and risk filters, sorting |
| `/stations/[id]` | everyone | One gauge: level chart with watch / warning / danger lines, risk history and reasons, warnings, data problems |
| `/weather` | everyone | Conditions and heat status in main towns; hottest, coldest, windiest and wettest areas |
| `/shelters` | operator to edit | Shelter list with occupancy; add shelters; update status and occupancy |
| `/devices` | admin to register | Own gauges and sirens: status, battery, signal; siren self-test; register a device (secrets shown once) |
| `/sources` | everyone | Freshness of each data source and open data-quality events |
| `/audit` | admin | Hash-chained audit log with one-click tamper check |
| `/admin` | admin | Users and roles, safety policies (exercise mode, thresholds), two-factor set-up |
| `/login` | staff | Email + password, then a 6-digit authenticator code when two-factor is on |
| `/public` | citizens | Nepali / English: flood risk near you, nearest open shelters, emergency numbers — no account needed |

The first admin account comes from `ADMIN_EMAIL` / `ADMIN_PASSWORD` in `.env` (only when no users exist). Change the password and set up two-factor after the first sign-in.

## Map data credits
Open-Meteo (CC BY 4.0) · DHM Nepal · © OpenStreetMap contributors (ODbL, Nepal rivers via `scripts/build_rivers.py`) · Natural Earth (world rivers, borders) · OpenFreeMap basemap · AWS Terrain Tiles (elevation)

## Repository layout
```
backend/     FastAPI app (adapters, processing, risk, warnings, devices, API) + tests + scripts
firmware/    ESP32 gauge and siren node code
frontend/    Next.js operations dashboard with 3D globe
supabase/    migrations (schema, RLS) and seed data
docs/        supporting analysis
presentation/ requirements specification deck
```
