# 03 — System Context and High-Level Architecture

> Deliverables 13–14 (context is also drawn in `02` §6). Tech stack fixed by the team: **Supabase** (PostgreSQL + PostGIS, Auth, Realtime, Storage), **Python** backend (FastAPI), **Next.js / React** frontend. All stack choices are **[D]**.

## 1. Architectural Drivers

| Driver | Source | Architectural consequence |
|---|---|---|
| Safety: no unsafe recommendation, no contradictory/silent warnings | SR-01..SR-10 | Single *Warning Manager* owns warning state machine; DB constraints enforce one active warning per (area, hazard); routing filters hazards *before* path search |
| Human authority for high-impact alerts | SR-02, Conflict C2 | Approval workflow with role checks in backend **and** RLS in DB |
| Degraded infrastructure | FR-47..FR-50 | PWA offline cache, SMS fallback, data-staleness state, "last known good" display, health monitor |
| Explainability/auditability | FR-14, FR-59 | Rule-based risk engine with stored evidence; append-only hash-chained audit log |
| Extensibility to hazards/regions | SO-16, FR-63..FR-67 | Hazard plug-in interface; configuration tables; no hard-coded thresholds/strings |
| Semester feasibility | S22 | Modular monolith (one FastAPI service, internal modules) rather than microservices; managed Supabase |

**Key decision — modular monolith [D].** Microservices would add deployment and failure-mode complexity disproportionate to a 1-semester team. Modules have clean interfaces (Python packages + DB schemas) so they *could* be split later. *Revisit when:* >1 region in production, independent scaling of ingestion vs. notification, or separate teams.

## 2. Layered Architecture

```
┌──────────────────────────────────────── PRESENTATION ───────────────────────────────────────┐
│ (8) Citizen PWA (Next.js)            (9) Authority Dashboard (Next.js)   (12) Admin Console  │
│  risk map · level · actions · shelters  map · approvals · manual alert    regions · thresholds│
│  route · report · offline cache · i18n  shelters · incidents · delivery   templates · users   │
└──────────────▲───────────────────────────────▲──────────────────────────────▲───────────────┘
               │ HTTPS REST + Supabase Realtime (WebSocket) + Web Push                          
┌──────────────┴───────────────────────────────┴──────────────────────────────┴───────────────┐
│                                  APPLICATION (Python / FastAPI)                              │
│ (1) Ingestion adapters ─► (2) Processing & Validation ─► (3) Risk Assessment Engine          │
│      sim gauges, Open-Meteo,      QC rules, staleness,        (4) Flood risk classifier       │
│      GloFAS, OSM, reports         fusion, anomaly flags            (hazard plug-in)           │
│                                                                 │                            │
│ (5) Warning & Alert Manager ◄────────────────────────────────── ┘  proposals                 │
│      state machine · approvals · contradiction guard · templates                             │
│        │                                                                                     │
│ (10) Notification Dispatcher ─► channel adapters: WebPush | SMS(sim) | Email | Siren(sim)    │
│ (6) Evacuation Routing        (7) Shelter Management       (11) Event & Audit Logger         │
│ (13) Health/Degraded-Mode Monitor (watchdog, heartbeats, fallbacks)                          │
│ Scheduler (APScheduler) · Auth middleware (Supabase JWT verify) · RBAC                       │
└──────────────▲──────────────────────────────────────────────────────────────────────────────┘
               │ SQL (asyncpg / supabase-py service role, server-side only)                     
┌──────────────┴──────────────────────────────────────────────────────────────────────────────┐
│                                   DATA (Supabase)                                            │
│ PostgreSQL 15 + PostGIS (+ optional pgRouting) · Row-Level Security · Auth (email/OTP, MFA)  │
│ Realtime (risk_levels, warnings, shelters) · Storage (report photos) · Daily backups/PITR    │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

## 3. Component Specifications

| # | Component | Responsibilities | Key interfaces | Main requirements |
|---|---|---|---|---|
| 1 | **Data Collection Layer** (adapters) | One adapter per source implementing `SourceAdapter.fetch() -> list[Observation]`. Sources: **simulated gauges & rainfall** (scenario player reading CSV/JSON timelines), **Open-Meteo** forecast (precipitation), **Open-Meteo Flood API / GloFAS** river discharge forecast (optional), **OSM** road graph (one-time import via OSMnx), **admin boundaries** (GeoJSON import), **population/vulnerability** (seeded per area from census-style aggregates), **citizen reports** (via API), **road closures** (operator entry / CSV) | Scheduler → adapter → `observations` table | FR-01..FR-05 |
| 2 | **Data Processing Layer** | Unit normalisation; schema & range validation; spike/flatline/rate-of-change checks; staleness tracking per source; cross-source consistency; quality flag (`GOOD/SUSPECT/BAD/MISSING`) | `validate(obs) -> QualityResult`; writes `data_quality_events` | FR-06..FR-10 |
| 3 | **Risk Assessment Engine** | Hazard-agnostic orchestrator: for each Area Unit × Hazard, gather latest valid inputs, call hazard plug-in, combine hazard level with exposure/vulnerability, produce `RiskAssessment` with **level, confidence, evidence, valid_until** | `HazardModel` interface (below) | FR-11..FR-16 |
| 4 | **Flood Risk Classifier** (plug-in) | Threshold rules on water level vs. station thresholds (Watch / Warning / Danger), rate-of-rise rule, upstream-station lead rule, rainfall accumulation rule, forecast rule; output level + reasons | Implements `HazardModel` | FR-11, FR-12, FR-17 |
| 5 | **Warning & Alert Manager** | Owns warning lifecycle state machine; creates *proposals* from assessments; enforces approval policy; contradiction guard; escalation/de-escalation; cancellation; expiry; renders message from templates | REST `/warnings/*`; DB table `warnings` with exclusion constraint | FR-18..FR-29, SR-01, SR-02, SR-07 |
| 6 | **Evacuation Route Recommender** | Load road graph for region; on request remove edges inside active hazard polygons, closed segments, flooded bridges; compute shortest *safe* path to candidate shelters (Dijkstra / A* with penalty weights); compute alternative edge-disjoint route; mark route confidence | `/evacuation/route` | FR-41..FR-46, SR-03, SR-04 |
| 7 | **Shelter Management** | Shelter registry (location, capacity, occupancy, status, accessibility, livestock, elevation, hazard suitability); availability updates; auto-exclude shelters inside hazard zones | `/shelters/*` | FR-38..FR-40, FR-55, SR-05 |
| 8 | **Citizen PWA** | Mobile-first, bilingual, offline-capable; current level for my area(s); action card; shelter list; route on map; report form; emergency numbers; accessibility modes | Next.js routes `/`, `/area/[id]`, `/shelters`, `/route`, `/report` | FR-30..FR-37 |
| 9 | **Authority Dashboard** | Live map (risk choropleth, gauges, reports, closures, shelters); approval queue; manual alert composer with recipient preview; shelter management; incidents; delivery & ack stats; evacuation progress | Next.js `/ops/*` | FR-51..FR-58 |
| 10 | **Notification System** | Fan-out per channel; per-recipient delivery record; retry with backoff; priority queue (Critical first); rate limiting & de-duplication; channel fallback (push → SMS) | `ChannelAdapter.send(msg, recipient) -> DeliveryResult` | FR-30, FR-34, FR-35, NFR-PF2 |
| 11 | **Incident & Event Logging** | Append-only audit log (hash-chained) of every risk change, warning action, config change, login; incident records from reports | `audit_log` table, trigger-based | FR-59..FR-62 |
| 12 | **Administration & Configuration** | Regions, area units, gauges/thresholds, hazards, templates & languages, channels, users/roles, data sources; config versioning with validation and 2-person approval for safety-relevant config | `/admin/*` | FR-63..FR-67 |
| 13 | **Failure & Offline Operation** | Heartbeat/watchdog per source and per job; degraded-mode banners; last-known-good cache; SMS fallback; manual-mode switch; static "emergency info" page served from CDN | `/health`, `system_status` table | FR-47..FR-50, NFR-A*, NFR-R* |

### 3.1 Hazard plug-in interface (extensibility point) [D]

```python
# backend/app/hazards/base.py
class HazardModel(Protocol):
    hazard_code: str                       # "FLOOD", "LANDSLIDE", ...
    required_inputs: list[str]             # e.g. ["water_level", "rainfall_24h"]

    def assess(self, area: AreaUnit, inputs: InputSnapshot, cfg: HazardConfig) -> HazardResult:
        """Return level in {NORMAL, WATCH, WARNING, CRITICAL, UNKNOWN},
        confidence in {HIGH, MEDIUM, LOW}, and a list of human-readable reasons."""
```

Adding a hazard = new `HazardModel` class + `hazards` row + threshold rows + message templates. No change to warnings, notifications, routing, UI shell (SO-16).

### 3.2 Flood risk rules (prototype) [D]

Rules are **transparent and configurable**, not ML. Thresholds per station are configuration data; in a real deployment they must come from DHM/authorities (assumption **[A]** that DHM-style "warning" and "danger" levels exist per station — DHM publishes station warning/danger levels on its hydrology portal **[F — verify]**).

| Rule | Condition (configurable) | Result |
|---|---|---|
| R1 Level | `level ≥ danger_level` | CRITICAL |
| R2 Level | `warning_level ≤ level < danger_level` | WARNING |
| R3 Level | `watch_level ≤ level < warning_level` | WATCH |
| R4 Rate of rise | `Δlevel/Δt ≥ rise_rate_threshold` for N consecutive readings | +1 level (max CRITICAL) |
| R5 Upstream lead | Upstream station linked to area is ≥ WARNING, travel time *t* configured | Downstream area ≥ WATCH immediately; ≥ WARNING if upstream CRITICAL |
| R6 Rainfall | 24 h accumulated rainfall (obs or forecast) ≥ threshold over catchment | ≥ WATCH |
| R7 Forecast | GloFAS/forecast discharge exceeds return-period threshold | ≥ WATCH (never above WATCH alone — forecast-only cannot trigger Critical) |
| R8 Data quality | Key input `MISSING/STALE/BAD` | Level = max(last valid level, WATCH if last valid ≥ WATCH) and `confidence = LOW`; area flagged `DATA_DEGRADED`; **never silently downgrade to NORMAL** (SR-06) |
| R9 Combination | Final = max over rules (conservative), then vulnerability modifier may *raise* Watch→Warning for high-vulnerability areas (configurable) | — |
| R10 De-escalation | Lower level only after `hold_time` (e.g. 2 × reading interval) of consistently lower readings with GOOD quality (hysteresis) | prevents flapping/fatigue |

**Why rules, not ML [D]:** explainable to authorities and examiners, verifiable by test oracles, consistent with safety-critical practice, feasible in a semester. ML forecasting is a *Could* (FR-17) that may only add **advisory** evidence, never auto-issue alerts.

### 3.3 Warning lifecycle state machine [D]

```
                   auto (rules)                   approve (1 camera: Watch/Warning ---> send to staff with alarm ..>notify all)
  ┌──────────┐   or manual draft    ┌───────────┐   approve (2 persons: Critical message from poeple or authority)
  │ (none)   │ ───────────────────► │ PROPOSED  │ ───────────────────────────────────►│  ACTIVE  │
  └──────────┘                      └─────┬─────┘                                     └────┬─────┘
                                          │ reject (reason required)                       │
                                          ▼                         escalate / de-escalate │ update
                                    ┌───────────┐                   (creates new version,  │ (new version,
                                    │ REJECTED  │                   supersedes old)        │  same series)
                                    └───────────┘                                          ▼
     timeout without decision on CRITICAL proposal ──► auto-escalate to next approver tier ┌──────────┐
     and, if configured, AUTO-PUBLISH as "unconfirmed—precautionary" (see Conflict C2)     │SUPERSEDED│
                                                                                           └──────────┘
   ACTIVE ──cancel (reason + all-clear msg)──► CANCELLED      ACTIVE ──valid_until passed──► EXPIRED
```

Invariants enforced in DB and code:
- **INV-1** At most one ACTIVE warning per (area_unit, hazard) — PostgreSQL partial unique index.
- **INV-2** Every transition is audited with actor, time, reason.
- **INV-3** Cancellation always produces an explicit *all-clear/correction* message to the same recipients.
- **INV-4** A system-issued warning can't be lower than an imported official warning for the same area/hazard (contradiction guard, SR-07).

## 4. Data Model (Supabase / PostgreSQL + PostGIS)

```sql
-- core geography & configuration
regions(id, code, name_en, name_ne, country_code, timezone, config jsonb, version int)
area_units(id, region_id, code, name_en, name_ne, level_type /* province|district|municipality|ward|reach */,
           parent_id, geom geometry(MultiPolygon,4326), population int, vulnerability_index numeric,
           vulnerability_notes jsonb)
hazards(code pk, name_en, name_ne, enabled bool, model_class text)
stations(id, region_id, code, name, kind /* gauge|rain|virtual */, geom geometry(Point,4326),
         upstream_of uuid[], travel_time_min int, source_id)
thresholds(id, station_id, hazard_code, watch numeric, warning numeric, danger numeric,
           rise_rate numeric, rain_24h numeric, valid_from, approved_by, version)
area_station_links(area_id, station_id, role /* primary|upstream */, weight)
data_sources(id, name, kind, url, poll_seconds, staleness_seconds, licence, enabled)

-- observations & quality
observations(id bigserial, source_id, station_id, variable, value numeric, unit,
             observed_at timestamptz, received_at timestamptz, quality text, raw jsonb)
data_quality_events(id, source_id, station_id, kind /* missing|stale|spike|flatline|range|conflict */,
                    detail jsonb, opened_at, closed_at)

-- risk & warnings
risk_assessments(id, area_id, hazard_code, level, confidence, reasons jsonb, inputs jsonb,
                 computed_at, valid_until, engine_version)
warnings(id, series_id, version, area_ids uuid[], hazard_code, level, status, source /* auto|manual|official_import */,
         proposed_by, approved_by uuid[], rejection_reason, valid_from, valid_until,
         message jsonb /* per-language rendered text */, supersedes uuid, created_at)
-- INV-1
create unique index one_active_warning on warning_areas(area_id, hazard_code) where status = 'ACTIVE';

-- dissemination
subscriptions(id, user_id null, phone_hash, push_endpoint, area_id, language, channels text[],
              accessibility jsonb, proxy_for_label text, consent_at, expires_at)
deliveries(id, warning_id, subscription_id, channel, status /* queued|sent|delivered|failed|acked */,
           attempts int, last_error, sent_at, acked_at)
message_templates(id, hazard_code, level, language, channel, body, icon, version, approved_by)

-- evacuation
shelters(id, region_id, name_en, name_ne, geom, capacity int, occupancy int, status /* open|full|closed|unsafe */,
         accessible bool, accepts_livestock bool, has_medical bool, contact, updated_at, updated_by)
road_closures(id, geom geometry(LineString,4326), osm_way_ids bigint[], reason, source, starts_at, ends_at)
hazard_zones(id, hazard_code, level, geom, source /* modelled|reported|official */, valid_until)

-- reports & incidents
citizen_reports(id, reporter_id null, geom, category, description, photo_path, water_depth_cm,
                status /* new|verified|rejected|duplicate */, verified_by, created_at)
incidents(id, area_id, kind, severity, geom, report_ids uuid[], status, assigned_to, created_at)

-- governance
profiles(user_id pk → auth.users, role /* citizen|volunteer|local_operator|district_operator|national_operator|responder|admin */,
         area_scope uuid[], mfa_required bool)
config_changes(id, entity, entity_id, diff jsonb, proposed_by, approved_by, status, created_at)
audit_log(id bigserial, at timestamptz, actor, action, entity, entity_id, payload jsonb, prev_hash, hash)
system_status(component, status /* ok|degraded|down */, detail, updated_at)
```

**RLS policy sketch [D]:** citizens read public risk/warnings/shelters; write own reports/subscriptions only. Operators read/write only rows whose `area_id` ∈ `profiles.area_scope`. Approvals executed only through backend (service role) after server-side role and two-person checks — the frontend never holds the service key.

## 5. API Design (FastAPI, REST + Realtime)

| Method & path | Role | Purpose | Req |
|---|---|---|---|
| `GET /api/v1/areas/{id}/risk` | public | Current level, confidence, reasons, valid_until, staleness | FR-31 |
| `GET /api/v1/risk/map?region=&hazard=` | public | GeoJSON of area risk (cached, ETag) | FR-13 |
| `GET /api/v1/warnings/active?lat=&lon=` or `?area=` | public | Active warnings for location/area | FR-30 |
| `POST /api/v1/subscriptions` | public | Subscribe area/language/channels (consent) | FR-32 |
| `GET /api/v1/shelters/nearest?lat=&lon=&accessible=&limit=3` | public | Ranked open shelters | FR-38 |
| `POST /api/v1/evacuation/route` | public | `{from, shelter_id?, mode, accessible}` → primary + alternative routes, warnings on route | FR-41..FR-44 |
| `POST /api/v1/reports` | public/volunteer | Citizen condition report | FR-37 |
| `POST /api/v1/warnings` | operator | Manual draft | FR-53 |
| `POST /api/v1/warnings/{id}/approve` · `/reject` · `/cancel` · `/escalate` | operator (scoped) | Lifecycle | FR-20..FR-27 |
| `GET /api/v1/warnings/{id}/recipients/preview` | operator | Count & areas before send | FR-53 |
| `GET /api/v1/deliveries/stats?warning=` | operator | Sent/delivered/failed/acked | FR-57 |
| `POST /api/v1/warnings/{id}/ack` | recipient | Acknowledge ("I am safe / I need help") | FR-24 |
| `PATCH /api/v1/shelters/{id}` | local operator | Occupancy/status | FR-55 |
| `POST /api/v1/road-closures` | operator | Closure | FR-43 |
| `POST /api/v1/admin/regions` … `/thresholds` … `/templates` | admin (+approver) | Config with validation | FR-63..FR-67 |
| `POST /api/v1/sim/scenarios/{name}/play` | admin (dev only) | Run scripted scenario | Testing |
| `GET /health`, `GET /api/v1/status` | public | Component and data freshness status | FR-48 |
| **Realtime channels** | — | `risk_assessments`, `warnings`, `shelters`, `system_status` changes pushed to dashboards | NFR-PF2 |
| **CAP export** `GET /api/v1/cap/{warning_id}.xml` | public | OASIS Common Alerting Protocol 1.2 | NFR-I1 |

## 6. Key Data Flows

**A. Automatic detection → warning (happy path)**
```
Scheduler(60s) → SimGaugeAdapter.fetch → observations(GOOD)
  → RiskEngine.recompute(affected areas) → risk_assessments (WARNING, HIGH, reasons=[R2,R4])
  → WarningManager.propose() → warnings(PROPOSED) → Realtime → Dashboard approval queue
  → operator approve → ACTIVE → Dispatcher fan-out (priority) → deliveries
  → citizens receive push/SMS → ack → stats on dashboard → audit_log at every step
```

**B. Critical with no approver (timeout)** — proposal escalates to district tier after `T_approve` (config, e.g. 10 min **[T]**); if still unapproved and region policy `auto_publish_unconfirmed_critical = true`, publishes a *precautionary* warning labelled as automated/unconfirmed and pages all approvers (Conflict C2 resolution).

**C. Data degraded** — no reading for `staleness_seconds` → `data_quality_events(stale)` → area confidence LOW, level held (R8) → dashboard banner "Gauge X stale since 14:05" → citizen view shows "Data delayed — follow local authority instructions".

## 7. Degraded / Offline Operation Design

| Condition | Behaviour |
|---|---|
| Citizen offline | PWA service worker caches: last risk state for subscribed areas (with timestamp), action cards, shelter list, simplified route map tiles for the area, emergency numbers. UI shows "Last updated hh:mm — may be outdated". |
| Citizen has SMS but no data | SMS channel (simulated gateway with production-shaped API) sends compact template ≤ 160 GSM-7 chars in English or ≤ 70 UCS-2 chars per segment for Nepali (Devanagari requires UCS-2 **[F]**) — templates designed for 2 segments max. |
| Backend down | Static emergency page on CDN (Vercel) with last published warnings snapshot (exported every minute to Supabase Storage/public JSON); operators fall back to manual SOP (phone/radio) — documented in runbook. |
| External API down | Adapter marks source stale; engine uses remaining sources + R8; dashboard shows degraded sources. |
| Database down | FastAPI returns 503 + cached last-known public state from in-memory cache; Supabase PITR for recovery. |
| Power loss at operator site | Dashboard is web-based: any device with battery/mobile data works; no on-prem dependency **[D]**. |

## 8. Technology Choices and Trade-offs

| Concern | Choice [D] | Alternatives considered | Trade-off / why |
|---|---|---|---|
| DB | **Supabase Postgres + PostGIS** | Firebase, MongoDB | Spatial queries (point-in-polygon, distance), constraints for safety invariants, RLS, Realtime; free tier fits prototype. Vendor dependence → mitigate with plain SQL migrations (portable to any Postgres). |
| Backend | **FastAPI (Python 3.12)** + APScheduler + Pydantic | Django, Supabase Edge Functions | Python ecosystem for geo (Shapely, OSMnx, NetworkX); typed contracts; async I/O for adapters. Edge functions would split logic across runtimes. |
| Routing | **OSMnx + NetworkX** in backend (graph cached per region) | pgRouting, OSRM, GraphHopper | Simplest to make hazard-aware (remove edges on the fly) and to test. Slower on big graphs → acceptable for one district; revisit with pgRouting/OSRM for national scale. |
| Frontend | **Next.js 15 App Router**, TypeScript, **MapLibre GL** + OSM tiles, **next-intl**, PWA via Serwist/Workbox, Tailwind | Leaflet, i18next | MapLibre handles vector styling of risk layers; next-intl gives ICU messages incl. Nepali numerals. |
| Auth | Supabase Auth (email OTP / password + **TOTP MFA** for operators/admins) | Keycloak | Built-in, RLS-integrated. |
| Notifications | Web Push (VAPID, `pywebpush`), email (SMTP dev), **SMS & siren simulators** behind `ChannelAdapter` | Twilio, local aggregator | Real SMS in Nepal requires an aggregator/operator agreement **[A]**; adapter interface makes swap trivial. |
| Hosting | Frontend: Vercel; Backend: Render/Fly.io/Railway (1–2 instances); DB: Supabase | Self-host | Free/cheap; adequate for demo. |
| Alert format | **CAP 1.2** export | Custom JSON only | International standard for public warning interop (ITU-T X.1303) **[F]**. |

## 9. Scale & Reliability Estimates (prototype vs. future)

| Quantity | Prototype assumption [A] | National-scale thought experiment [A] |
|---|---|---|
| Area units | ~50 wards in 1–2 municipalities | ~6,700 wards nationwide **[F: Nepal has 6,743 wards — verify]** |
| Stations | 3–6 simulated | Hundreds of DHM stations |
| Subscribers | ≤ 1,000 synthetic | Millions → SMS/cell-broadcast via operators, not app push |
| Observation rate | 1/min/station | Same order; ingestion trivial |
| Fan-out peak | 1,000 messages in < 60 s | Requires queue (e.g. Redis/RQ or Postgres-backed queue), multiple dispatchers, operator-side broadcast |

*Revisit as the system grows:* move dispatcher to a dedicated worker + queue; replace in-memory graph with pgRouting/OSRM; multi-region Supabase or self-hosted Postgres with streaming replica; formal CAP feed integration with BIPAD; cell broadcast via telecom operators.

## 10. Proposed Repository Layout

```
AlarmSystem/
├── docs/                       # this RE documentation
├── backend/                    # FastAPI
│   ├── app/
│   │   ├── adapters/           # sim_gauge.py, open_meteo.py, glofas.py, osm_import.py
│   │   ├── processing/         # validation.py, staleness.py, fusion.py
│   │   ├── hazards/            # base.py, flood.py, landslide_stub.py
│   │   ├── risk/               # engine.py
│   │   ├── warnings/           # state_machine.py, guard.py, templates.py
│   │   ├── notify/             # dispatcher.py, channels/{webpush,sms_sim,email,siren_sim}.py
│   │   ├── evacuation/         # graph.py, router.py, shelters.py
│   │   ├── audit/              # logger.py (hash chain)
│   │   ├── health/             # watchdog.py
│   │   └── api/                # routers per resource
│   ├── scenarios/              # scripted flood scenarios (JSON) used as test oracles
│   └── tests/
├── frontend/                   # Next.js (citizen + /ops + /admin)
└── supabase/
    ├── migrations/             # SQL schema, RLS, indexes, triggers
    └── seed/                   # regions, wards, stations, thresholds, shelters, templates (ne/en)
```
