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

## Planned repository layout
```
backend/     FastAPI app (adapters, processing, hazards, risk, warnings, notify, evacuation, devices, audit)
firmware/    ESP32 gauge and siren node code
frontend/    Next.js citizen PWA + /ops dashboard + /admin
supabase/    migrations (schema, RLS) and seed data
docs/        supporting analysis
presentation/ requirements specification deck
```
