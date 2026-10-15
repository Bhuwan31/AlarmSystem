# 04 — Requirements Specification

> **Global product, Nepal pilot.** AMHEWS is designed for any country or region. Nepal is the **first pilot deployment (testing ground)**. Nepal-specific organisations, languages, laws and numbers in this document describe the pilot's *Deployment Profile* (FR-68), not limits of the product. See [REQUIREMENTS_ENGINEERING.md §1.2.1](../REQUIREMENTS_ENGINEERING.md).

> Deliverables 15–19. Format follows IEEE/ISO/IEC 29148 attributes (ID, statement, source, priority, rationale, verifiable acceptance criterion).
>
> - "**shall**" = mandatory; "**should**" = desirable. One requirement per statement.
> - **Priority** = MoSCoW for the *prototype*: **M**ust / **S**hould / **C**ould / **W**on't (see `08-prioritization-and-traceability.md` for justification).
> - Numbers marked **[T]** are *prototype acceptance targets* measured in a lab/simulated setting, **not** real-world guarantees.
> - **Glossary:** *Area Unit* = smallest configured geographic unit for risk (ward or river reach). *Level* ∈ {NORMAL, WATCH, WARNING, CRITICAL} plus UNKNOWN. *Operator* = authenticated authority user. *Approver* = operator with approval right for the area.
> - Stakeholder codes S1–S24 as in `02-stakeholders-and-personas.md`.

---

## 1. Functional Requirements

### 1.1 Data (G1)

| ID | Requirement | Stakeholder | Pri | Rationale | Acceptance criteria |
|---|---|---|---|---|---|
| FR-01 | The system shall ingest river water-level observations from each configured station source at the source's configured interval. | S19, S8 | M | Water level is the primary flood signal. | Given a simulated station emitting every 60 s, ≥ 99 % of readings are stored with `observed_at` and `received_at` over a 1-hour test **[T]**. |
| FR-02 | The system shall ingest observed and forecast rainfall for configured catchments/points from at least one public weather API. | S19 | M | Rainfall gives lead time before river rise. | Open-Meteo (or mocked equivalent) precipitation for configured points is stored hourly; adapter test with recorded response passes. |
| FR-03 | The system shall import static datasets (administrative boundaries, road network, shelter list, population per area) from GeoJSON/CSV/OSM files. | S21, S23 | M | Geography and exposure are prerequisites for localized risk. | Import of seed files creates area units, road graph, shelters; invalid geometries are rejected with a report. |
| FR-04 | The system should ingest river discharge forecasts from a public global flood-forecast service (e.g. GloFAS via Open-Meteo Flood API) where available. | S19, S8 | C | Adds lead time; known to be coarse at small catchments **[A]**. | Daily forecast stored for ≥ 1 point; marked `advisory` source class. |
| FR-05 | The system shall provide a scenario player that replays scripted timelines of observations as if they were live data. | S22 | M | Prototype has no physical sensors; scenarios double as test oracles. | Playing `scenario_flash_rise.json` produces the expected observation stream with correct timestamps. |
| FR-06 | The system shall validate each incoming observation against schema, unit, physical range and station-specific plausible range. | S19, S21 | M | Bad data must not drive warnings. | Values outside configured range are stored with `quality=BAD` and excluded from risk calculation; unit test covers each rule. |
| FR-07 | The system shall detect missing data when no valid observation from a source/station has been received within its configured staleness window. | S21, S8 | M | Silence must not be interpreted as safety (SR-06). | With staleness 5 min, stopping the simulator opens a `stale` quality event within ≤ 60 s after window expiry **[T]**. |
| FR-08 | The system shall flag abnormal values: spikes (change > configured Δ in one interval), flatlines (identical values for N intervals), and negative/impossible rates. | S19, S21 | M | Sensor faults and transmission errors are common failure causes **[A]**. | Injected spike, flatline and drop-out sequences are each flagged `SUSPECT` with the correct reason. |
| FR-09 | The system shall compare readings from linked sources (e.g. station vs. upstream station, gauge vs. volunteer report) and raise a `conflict` quality event when they disagree beyond a configured tolerance. | S19, S24 | S | Multiple sources may conflict (Failure F7). | Scenario with gauge = normal and 3 verified volunteer reports of overtopping raises a conflict event and dashboard alert. |
| FR-10 | The system shall record, for every observation, its source, provenance (raw payload), and quality flag. | S10, S21 | M | Post-event analysis and trust. | Every row in `observations` has non-null `source_id`, `quality`, `raw`. |

### 1.2 Risk Assessment (G2)

| ID | Requirement | Stakeholder | Pri | Rationale | Acceptance criteria |
|---|---|---|---|---|---|
| FR-11 | The system shall compute a flood risk level (NORMAL/WATCH/WARNING/CRITICAL/UNKNOWN) for every configured Area Unit using the configured rule set (R1–R10, `03-architecture.md` §3.2). | S8, S9 | M | Core function. | For each scripted scenario, computed levels per area per time step match the scenario oracle 100 % **[T]**. |
| FR-12 | The system shall recompute risk for affected Area Units within 60 s of a new valid observation or configuration change. **[T]** | S8, S2 | M | Timeliness (SO-1). | Measured p95 latency ingest→assessment ≤ 60 s over 100 runs. |
| FR-13 | The system shall display risk on a geographic map as a colour-, pattern- and label-coded layer of Area Units. | S8, S1 | M | Spatial understanding. | Map shows every area with level label and pattern (not colour alone); verified by screenshot test and accessibility check. |
| FR-14 | The system shall store with each assessment its inputs, triggered rules, confidence and engine/config version. | S10, S8 | M | Explainability and auditability. | API `GET /areas/{id}/risk` returns `reasons[]` naming rules; reproducing with stored inputs yields same level. |
| FR-15 | The system shall assign a confidence (HIGH/MEDIUM/LOW) to each assessment, reduced when key inputs are missing, suspect or conflicting. | S8, S9 | M | Handling uncertainty (SR-08). | Stale primary gauge ⇒ confidence LOW and UI badge "Data degraded". |
| FR-16 | The system shall identify vulnerable areas by combining risk level with configured exposure/vulnerability attributes (population, % elderly/disabled where available, critical facilities). | S8, S6, S17 | S | Prioritize response to most vulnerable. | Dashboard "Priority areas" list orders WARNING+ areas by vulnerability index; matches hand calculation for seed data. |
| FR-17 | The system could incorporate an advisory statistical/ML forecast as additional evidence, which shall never on its own raise the level above WATCH or trigger an alert. | S22 | C | Shows extensibility without compromising safety. | With ML component enabled, scenario where only ML predicts flood yields at most WATCH and reason `ML_ADVISORY`. |

### 1.3 Warning Management (G3)

| ID | Requirement | Stakeholder | Pri | Rationale | Acceptance criteria |
|---|---|---|---|---|---|
| FR-18 | When an Area Unit's assessed level rises to WATCH or above, the system shall create a warning *proposal* for that area and hazard, containing level, evidence, suggested message and suggested target areas. | S8 | M | Automates detection while keeping human authority. | Scenario rise to WARNING creates exactly one PROPOSED warning within ≤ 60 s **[T]**. |
| FR-19 | The system shall auto-publish WATCH-level warnings without human approval if the region policy `auto_publish_watch` is enabled. | S2, S8 | S | WATCH = "be prepared", low harm if false; reduces approver load. | With policy on, WATCH proposal becomes ACTIVE automatically and audit shows `actor=system`. |
| FR-20 | The system shall require approval by one authorized approver for WARNING-level warnings and by two distinct authorized approvers for CRITICAL/Evacuate warnings before dissemination. | S8, S9, S10 | M | Human authorization for high-impact actions (SR-02). | Single approval of CRITICAL leaves status PROPOSED; same user approving twice is rejected; second distinct approver activates it. |
| FR-21 | If a CRITICAL proposal is not decided within the configured approval timeout, the system shall escalate it to the next authority tier and, where region policy allows, publish it labelled "Automated precautionary warning – awaiting official confirmation". | S2, S9 | M | Prevents a missed warning due to unavailable approvers (Conflict C2). | Timeout 10 min (test config 30 s) ⇒ escalation notification to district approvers; with policy on, publication with label; audit records both. |
| FR-22 | The system shall allow approvers to edit the proposed message text, target areas and validity before approval, with the edit recorded. | S8 | M | Local knowledge improves messages. | Edited fields stored as diff in audit log. |
| FR-23 | The system shall escalate an ACTIVE warning to a higher level (as a new version superseding the previous) when assessment rises, following the same approval rules as a new warning of that level. | S8, S2 | M | Situations worsen. | WARNING→CRITICAL produces version 2, version 1 SUPERSEDED, recipients receive one escalation message. |
| FR-24 | The system shall allow recipients to acknowledge a warning with one action and optionally indicate "I am safe" or "I need help". | S1, S16 | S | Situational awareness and SAR targeting. | Ack recorded in `deliveries.acked_at`; "need help" creates an incident with location (if consented). |
| FR-25 | The system shall allow authorized operators to cancel an ACTIVE warning only with a mandatory reason and shall send an all-clear or correction message to all recipients of the cancelled warning. | S8, S1 | M | Corrections must reach the same people (INV-3). | Cancel without reason rejected; cancel with reason triggers all-clear deliveries equal in count to original deliveries. |
| FR-26 | The system shall propose de-escalation only after the lower level has persisted with GOOD-quality data for the configured hold time (hysteresis). | S1, S8 | M | Prevents flapping and fatigue (Conflict C8). | Oscillating scenario around threshold yields ≤ 1 level change per hold window. |
| FR-27 | The system shall automatically expire warnings at `valid_until` unless renewed, and notify approvers 15 min before expiry of a WARNING/CRITICAL. | S8 | S | Stale warnings erode trust; unintended expiry is dangerous. | Expiry reminder sent; status EXPIRED after time; renew extends with audit. |
| FR-28 | The system shall prevent contradictory warnings: at most one ACTIVE warning per (Area Unit, hazard); and no system-issued level lower than an imported official warning for the same area and hazard. | S10, S19 | M | Contradictions cause confusion and mistrust (SR-07). | Attempt to activate a second warning for same area/hazard fails (DB constraint); imported official WARNING blocks a system WATCH for that area. |
| FR-29 | The system shall render each warning from approved templates containing: hazard, level (word + icon + colour), affected area names, required action, issuing authority, issue time, valid until, and source/confidence statement. | S1, S6, S7 | M | Complete, actionable messages (SO-5). | Template linter fails any template missing a field; message preview shows all fields in ne and en. |

### 1.4 Citizen-Facing (G3, G4)

| ID | Requirement | Stakeholder | Pri | Rationale | Acceptance criteria |
|---|---|---|---|---|---|
| FR-30 | The system shall deliver ACTIVE warnings to all subscriptions whose area intersects the warning's target areas, via each subscription's enabled channels. | S1–S7 | M | Core dissemination. | 1,000 synthetic subscriptions: 100 % of in-area receive record; 0 out-of-area **[T]**. |
| FR-31 | The citizen interface shall show the current level, plain-language action, confidence/data status and last-updated time for the user's selected area or current location (with consent). | S1, S7 | M | "What is my risk, what do I do?" | UC-02 test passes; action card text matches template for each level. |
| FR-32 | The system shall allow a user to subscribe to up to 5 areas (e.g. home, farm, parent's home), including on behalf of another person (proxy), without requiring an account. | S1, S4, S6 | S | Migrant family members, carers (P2, P8). | Subscription with phone number only works; proxy label shown in message ("for: Father's home"). |
| FR-33 | The citizen interface shall show level-specific evacuation instructions, including "what to take" and "what not to do" (e.g. do not cross flowing water). | S1, S3 | M | Actionability. | Instructions exist for each level × language; reviewed by DRR proxy. |
| FR-34 | The system shall determine a user's area from (a) chosen area, (b) device location with explicit consent, or (c) QR/area code (e.g. posted at guesthouses, schools). | S7, S1 | S | Tourists and privacy-preferring users (P5). | Each method yields correct area for test points; location is not stored server-side unless the user subscribes with it. |
| FR-35 | The system shall support an SMS channel (simulated gateway in prototype) with compact templates in each configured language (pilot: Nepali and English). | S2, S4 | M | Feature phones / no data (P1, P2). | SMS template ≤ 2 segments per language; simulator log shows delivery. |
| FR-36 | The system shall allow a user to request assistance (e.g. mobility help) that creates an incident visible to the responsible local operator and volunteers. | S6, S4, S24 | S | Vulnerable people need help evacuating. | Request appears on dashboard within ≤ 10 s **[T]** with category and location. |
| FR-37 | The system shall allow citizens and volunteers to report local conditions (category, location, optional water depth, optional photo, description), working offline and syncing later. | S1, S24, S8 | M | Ground truth; detects events sensors miss. | Offline report queued in PWA and submitted on reconnect; operator sees it with `new` status. |

### 1.5 Evacuation & Shelters (G4)

| ID | Requirement | Stakeholder | Pri | Rationale | Acceptance criteria |
|---|---|---|---|---|---|
| FR-38 | The system shall return the nearest suitable shelters (default 3) ranked by safe-route travel distance, filtered to status `open` with available capacity > 0. | S1, S8 | M | Shelter lookup. | For seed data, results match hand-computed ranking; full/closed shelters never returned. |
| FR-39 | The system shall allow filtering shelters by accessibility (step-free), medical support and livestock acceptance. | S6, S3 | S | Specific needs (P1, P8). | Filter `accessible=true` returns only accessible shelters. |
| FR-40 | The system shall show shelter details: name (ne/en), address/landmark, capacity, current occupancy, last-updated time, facilities, contact. | S1, S17 | M | Informed choice. | Detail page shows all fields; occupancy timestamp visible. |
| FR-41 | The system shall compute a recommended walking (default) or vehicle route from the user's location to a selected shelter over the road/path network. | S1 | M | Core evacuation support. | Route returned for 20 test origin/shelter pairs. |
| FR-42 | The system shall exclude from routing all edges intersecting active hazard zones (WARNING+), recorded road closures, and bridges flagged unsafe. | S1, S20 | M | Never route people into danger (SR-03). | 0 / N test routes intersect excluded geometry. |
| FR-43 | The system shall allow operators to record and remove road/bridge closures (map drawing or segment selection) with reason and time window. | S20, S11 | M | Closures change rapidly. | Closure recorded ⇒ subsequent route requests avoid it. |
| FR-44 | The system shall provide at least one alternative route (edge-disjoint where possible) and state when no safe route exists, with fallback advice ("move to higher ground / upper floor; call 100"). | S1 | M | Primary route may become blocked (F12). | No-route scenario returns explicit "no safe route" with fallback advice — never an unsafe route. |
| FR-45 | The system shall recompute and push updated recommendations to users who requested a route within the last N minutes when a closure or hazard zone change affects their route. | S1 | S | Conditions change during evacuation. | Adding closure on active route triggers re-route notification ≤ 60 s **[T]**. |
| FR-46 | The system shall display route warnings (e.g. "passes within 100 m of river", "low confidence – road data incomplete"). | S1 | S | Honest uncertainty (SR-04). | Route through low-confidence segments carries warning text. |

### 1.6 Degraded & Offline Operation (G6)

| ID | Requirement | Stakeholder | Pri | Rationale | Acceptance criteria |
|---|---|---|---|---|---|
| FR-47 | The citizen PWA shall cache, for subscribed areas, the last known risk state, active warnings, instructions, shelter list and emergency contacts, and display them offline with timestamp. | S2, S1 | M | Connectivity fails during disasters. | With network disabled in DevTools, all listed content renders with "last updated" time. |
| FR-48 | The system shall expose a status page showing each component's and each data source's health and freshness. | S21, S8 | M | Operators must know what to trust. | Stopping a source turns its status `degraded` within ≤ 60 s **[T]**. |
| FR-49 | The system shall fall back to SMS for subscribers with SMS enabled when web-push delivery fails or is not acknowledged within the configured time for WARNING+. | S2 | S | Channel redundancy. | Push failure simulated ⇒ SMS sent; delivery record shows both attempts. |
| FR-50 | The system shall publish a static snapshot of active warnings and shelters (JSON + HTML) to a CDN-hosted location every 60 s, usable if the backend is down. | S1, S21 | S | Server crash tolerance (F15). | With backend stopped, static page shows last snapshot ≤ 2 min old. |

### 1.7 Authorities & Coordination (G5)

| ID | Requirement | Stakeholder | Pri | Rationale | Acceptance criteria |
|---|---|---|---|---|---|
| FR-51 | The dashboard shall show, for the operator's scope, a live map of area risk, stations with latest values/trends, active warnings, shelters, closures and reports. | S8, S9, S10 | M | Monitoring. | Changes appear without page reload ≤ 5 s after DB update **[T]**. |
| FR-52 | The dashboard shall list areas sorted by level and vulnerability, with time-in-level and trend arrow. | S8, S9 | M | Prioritization. | List order matches level then vulnerability. |
| FR-53 | Operators shall be able to manually compose a warning for selected areas from templates, preview recipients count/areas/messages per language, and submit it to the approval workflow. | S8, S9 | M | Authorities may know of risk before data shows it (e.g. embankment breach). | Manual WARNING follows FR-20; preview count equals actual deliveries. |
| FR-54 | The dashboard shall show evacuation progress indicators: acknowledgements (safe/need help), shelter occupancy vs. capacity, open assistance requests per area. | S8, S9, S11 | S | Monitor evacuation. | Indicators update with simulated acks. |
| FR-55 | Authorized shelter managers shall update shelter status (open/full/closed/unsafe) and occupancy; changes shall propagate to citizen recommendations immediately. | S8, S17 | M | Shelter availability (F13). | Setting `full` removes shelter from FR-38 results on next request. |
| FR-56 | Operators shall triage citizen reports (verify / reject / mark duplicate / convert to incident) and see clustered reports on the map. | S8, S14 | M | Manage report volume and misinformation. | Status transitions audited; verified reports feed FR-09. |
| FR-57 | The dashboard shall show per-warning delivery statistics by channel (queued/sent/delivered/failed/acked). | S8, S10 | M | Detect non-delivery (F11). | Stats equal counts in `deliveries`. |
| FR-58 | The system shall export ACTIVE warnings as CAP 1.2 XML and a JSON feed for other agencies' systems. | S10, S18 | S | Interoperability (BIPAD, telecom). | CAP output validates against CAP 1.2 schema. |

### 1.8 Logging & Post-Event Analysis (G7)

| ID | Requirement | Stakeholder | Pri | Rationale | Acceptance criteria |
|---|---|---|---|---|---|
| FR-59 | The system shall append to a tamper-evident audit log every risk level change, warning lifecycle action, delivery batch, configuration change, login and permission change. | S10, S21 | M | Accountability, learning (SO-15). | Hash-chain verification script detects any modified/deleted row. |
| FR-60 | The system shall provide an event timeline for a selected period/area combining observations, assessments, warnings, deliveries and reports. | S10, S8 | S | After-action review. | Timeline export (CSV/JSON) for scenario run contains all event types. |
| FR-61 | The system shall allow replay of a past period through the risk engine with a different configuration (what-if) without affecting live data. | S10, S22 | C | Threshold tuning and validation. | Replay with changed thresholds shows differing levels in sandbox only. |
| FR-62 | The system shall compute post-event metrics: lead time (first WATCH/WARNING before observed peak), false alarms, missed events, delivery rates. | S10, S19 | S | Evaluation (doc 10). | Metrics report generated for each scenario. |

### 1.9 Administration & Configuration (G8)

| ID | Requirement | Stakeholder | Pri | Rationale | Acceptance criteria |
|---|---|---|---|---|---|
| FR-63 | Admins shall configure regions and area units (import boundaries, names in each language, parent hierarchy, population/vulnerability attributes). | S21, S8 | M | Adaptation to new places (UC-13). | New municipality configured from GeoJSON without code change. |
| FR-64 | Admins shall configure stations, area–station links (primary/upstream, travel time) and thresholds; changes to thresholds shall require approval by a second authorized user and be versioned. | S21, S19 | M | Thresholds are safety-relevant. | Threshold change pending until second approval; previous version retrievable. |
| FR-65 | Admins shall manage message templates per hazard × level × language × channel, with mandatory-field linting and approval. | S21, S8 | M | Multilingual, consistent messages. | Template missing a required placeholder cannot be saved. |
| FR-66 | Admins shall manage users, roles and geographic scopes. | S21 | M | RBAC. | Operator scoped to Ward 5 cannot approve warnings for Ward 6 (API + RLS test). |
| FR-67 | Admins shall enable/disable hazard types and data sources and set region policies (auto-publish WATCH, Critical timeout, auto-publish unconfirmed Critical). | S21, S10 | M | Adaptive design. | Toggling policy changes behaviour in the corresponding test. |
| FR-68 | The system shall load every country- or region-specific setting (administrative hierarchy, languages, official authorities, emergency numbers, time zone, calendar, legal texts, channels) from a Deployment Profile; nothing country-specific is hard-coded. | S10, S21 | M | Global by design; Nepal is the first pilot. | A second test profile changes all of these with no code change. |

---

## 2. Non-Functional Requirements

### 2.1 Performance (PF)

| ID | Requirement | Pri | Rationale | Acceptance / measurement |
|---|---|---|---|---|
| NFR-PF1 | End-to-end alert generation latency (valid observation ingested → warning PROPOSED) shall be ≤ 60 s at p95 **[T]**. | M | Detection must not add meaningful delay vs. hydrological lead times of hours **[A]**. | Instrumented timestamps over 100 scenario runs. |
| NFR-PF2 | Notification dispatch (ACTIVE → all push/SMS handed to channel provider) shall complete for 1,000 recipients within ≤ 60 s **[T]**; CRITICAL messages are dispatched before lower levels. | M | Timely delivery; prioritization. | Load test with 1,000 synthetic subscriptions. Note: *delivery to handset* depends on external networks and is measured, not guaranteed. |
| NFR-PF3 | Public read APIs (risk, warnings, shelters) shall respond ≤ 1 s p95 and route requests ≤ 3 s p95 at 50 concurrent users **[T]**. | M | Emergency use; low-bandwidth users. | k6/Locust test. |
| NFR-PF4 | Citizen home page initial load shall be ≤ 300 KB compressed (excluding map tiles) and usable on a simulated 3G "slow" profile within 5 s **[T]**. | S | Low-end phones/networks **[A]**. | Lighthouse with throttling. |
| NFR-PF5 | Dashboard realtime updates shall appear ≤ 5 s after the DB change **[T]**. | S | Situational awareness. | Timestamp comparison. |

### 2.2 Availability (A)

| ID | Requirement | Pri | Rationale | Acceptance |
|---|---|---|---|---|
| NFR-A1 | The prototype shall achieve ≥ 99 % availability of public read endpoints during a continuous 72-h test window **[T]**. *(A production target would be set by authorities; e.g. ≥ 99.9 % in monsoon season — not claimed here.)* | S | Realistic for free-tier hosting. | Uptime monitor (e.g. UptimeRobot) log. |
| NFR-A2 | The system shall provide a static fallback (FR-50) independent of the backend and database. | S | Disaster-time availability. | Kill backend → fallback page reachable. |
| NFR-A3 | The backend shall be deployable as ≥ 2 stateless instances behind a load balancer; schedulers shall use a DB lock (leader election) so jobs run exactly once. | C | Redundancy. | Two instances, kill one, ingestion continues; no duplicate warnings. |
| NFR-A4 | Planned maintenance shall not be performed when any area is at WARNING or above (maintenance freeze rule). | S | Avoid self-inflicted outages during events. | Deployment script checks `/status` and refuses. |

### 2.3 Reliability (R)

| ID | Requirement | Pri | Rationale | Acceptance |
|---|---|---|---|---|
| NFR-R1 | No observation shall drive a risk computation unless it passed validation (FR-06/FR-08) with quality GOOD or (with reduced confidence) SUSPECT. | M | Garbage in → false/missed alerts. | Fault-injection tests. |
| NFR-R2 | External adapter failures shall be isolated (timeouts ≤ 10 s, retries with exponential backoff, circuit breaker) and shall not stop other adapters or the risk engine. | M | Fault tolerance. | Mock API returning 500/timeouts; other sources continue. |
| NFR-R3 | Notification sending shall be at-least-once with idempotency keys so that a recipient never receives the same warning version more than once per channel. | M | No lost, no duplicate alerts. | Crash dispatcher mid-batch; on restart, all remaining sent once. |
| NFR-R4 | After a backend restart the system shall resume scheduled jobs and recompute all area risk within ≤ 2 min **[T]**. | M | Recovery. | Restart test. |
| NFR-R5 | Database shall have daily backups and point-in-time recovery; restore procedure documented and rehearsed once. | S | Recovery. | Restore drill record. |

### 2.4 Usability & Accessibility (U)

| ID | Requirement | Pri | Rationale | Acceptance |
|---|---|---|---|---|
| NFR-U1 | Emergency screens shall present at most one primary action per screen, using plain language at about a primary-school reading level (validated with users). | M | Stress reduces cognitive capacity. | Usability test: ≥ 80 % of participants identify correct action within 30 s **[T]**. |
| NFR-U2 | Citizen pages shall conform to WCAG 2.2 Level AA (contrast, text resize to 200 %, screen-reader labels, keyboard navigation). | M | Persons with disabilities (S6). | axe-core automated + manual NVDA/TalkBack check. |
| NFR-U3 | Risk levels shall be conveyed redundantly by word, icon, colour and (in app) an optional distinctive sound/vibration pattern; colour shall never be the sole cue. | M | Colour-blindness, low literacy. | Review checklist. |
| NFR-U4 | All citizen UI strings and templates shall be available in every language configured for a deployment, with English as fallback (pilot: Nepali in Devanagari + English); new languages (e.g. Maithili, Bhojpuri, Tharu, Tamang, Newar for the pilot, or any other) are added via language packs without code change. | M | Rural and multilingual users. | Add a dummy language pack → UI renders it. |
| NFR-U5 | The citizen app shall offer a "read aloud" function (browser TTS) for the action card, and SMS/IVR text shall be written to be read aloud by a helper. | S | Low literacy, visual impairment. | TTS plays in en; ne where browser voice available (limitation documented). |
| NFR-U6 | Operators shall be able to approve a warning in ≤ 3 clicks from the dashboard notification, with evidence visible on the same screen. | S | Speed under pressure without blind approval. | Task analysis. |

### 2.5 Scalability (SC)

| ID | Requirement | Pri | Acceptance |
|---|---|---|---|
| NFR-SC1 | Adding a region shall require only configuration/data import (FR-63). | M | Demo: add second municipality. |
| NFR-SC2 | Adding a hazard shall require only a `HazardModel` plug-in, config rows and templates — no change to core tables or warning/notification modules. | M | Landslide stub demo (SO-16). |
| NFR-SC3 | Adding a data source shall require only a new adapter class and a `data_sources` row. | M | Add mock source in < 1 day. |
| NFR-SC4 | Design shall document the path to ≥ 1 M subscribers (queue-based dispatch, operator broadcast channels). | C | Architecture doc §9. |

### 2.6 Maintainability (M)

| ID | Requirement | Pri | Acceptance |
|---|---|---|---|
| NFR-M1 | Modules shall interact only through defined interfaces; no module accesses another module's tables directly except via its service (enforced by code review + import-linter). | S | Lint passes. |
| NFR-M2 | Thresholds, policies, templates, languages, channels and region data shall be configuration, not code. | M | Grep for hard-coded thresholds returns none. |
| NFR-M3 | Backend unit test coverage of risk engine, warning state machine, routing filter and validation ≥ 85 % lines **[T]**. | M | Coverage report. |
| NFR-M4 | DB schema changes only via versioned migrations in `supabase/migrations`. | M | CI check. |

### 2.7 Interoperability (I)

| ID | Requirement | Pri | Acceptance |
|---|---|---|---|
| NFR-I1 | Warnings shall be exportable in OASIS CAP 1.2 (FR-58). | S | Schema validation. |
| NFR-I2 | Geodata shall use WGS84 (EPSG:4326) and GeoJSON for exchange. | M | API contract tests. |
| NFR-I3 | Channel adapters shall follow a common interface so real SMS aggregators, cell broadcast or sirens can be added. | M | Interface test with 2 implementations. |
| NFR-I4 | Data adapters shall support pull (HTTP/JSON, CSV) and push (webhook) integration so that DHM or BIPAD feeds can be integrated if access is granted. | S | Webhook mock test. |
| NFR-I5 | Map display shall use OSM-based tiles with correct attribution (ODbL). | M | Attribution visible. |

---

## 3. Safety Requirements (SR)

Derived from hazard analysis (`06` §Failure scenarios) — every SR traces to ≥ 1 failure scenario. Safety requirements receive **higher verification rigor**: each must have a dedicated automated test *and* a scenario test, and changes require review by two team members.

| ID | Safety requirement | Mitigates | Verification |
|---|---|---|---|
| SR-01 | The system shall never silently drop a warning: every ACTIVE warning shall have, per target subscription, a delivery record whose final state is `delivered`, `acked` or `failed` (with reason) — and failed WARNING+ deliveries shall be surfaced to operators. | F10, F11 | Fault-injection: channel failures appear on dashboard. |
| SR-02 | WARNING requires one and CRITICAL requires two distinct authorized human approvals, except the documented, policy-controlled precautionary path (FR-21). | F16, F17 | State machine tests incl. same-user double approval. |
| SR-03 | The routing module shall never return a route that intersects an active WARNING+ hazard zone, a recorded closure or an unsafe bridge; if none exists it shall return "no safe route" and fallback advice. | F12 | Property-based test over random origins. |
| SR-04 | Every route and shelter recommendation shall state its data timestamp and limitations ("Road conditions may have changed – follow officials on site"). | F12, F14 | UI test. |
| SR-05 | Shelters located inside an active WARNING+ hazard zone, or with status full/closed/unsafe, shall never be recommended. | F13 | Test. |
| SR-06 | Loss, staleness or invalidity of input data shall never by itself lower an area's level; it shall lower confidence and alert operators (fail-safe/fail-noisy). | F4, F5, F6 | Scenario: gauge stops at WARNING → level stays ≥ WARNING with LOW confidence. |
| SR-07 | The system shall not publish a level lower than an imported/entered official authority warning for the same area and hazard, and shall label its own warnings with the issuing authority. | F7, C6 | Contradiction guard test. |
| SR-08 | Every risk display and warning shall show confidence; LOW-confidence CRITICAL proposals shall be highlighted to approvers with the reasons. | F6, F8 | UI + API test. |
| SR-09 | Cancellation/correction messages shall be sent to every recipient of the original warning through the same channels (INV-3). | F17 | Count equality test. |
| SR-10 | The system shall display on every citizen screen and message that it is decision support, and that official instructions from police/local authorities on site take precedence. | Ethics, F18 | Content review. |
| SR-11 | A forecast-only or ML-only signal shall not raise the level above WATCH (R7, FR-17). | F8, F19 | Test. |
| SR-12 | The system shall reject test/simulated data in production mode: scenario-player observations carry `is_simulated=true` and are excluded unless the region is in `exercise` mode, in which case every message is prefixed "EXERCISE – NOT A REAL WARNING". | F16, F17 | Mode test. |

## 4. Security Requirements (S)

| ID | Requirement | Pri | Verification |
|---|---|---|---|
| NFR-S1 | All operator/admin accounts shall use MFA (TOTP); approvals require a session authenticated with MFA within the last 12 h. | M | Login tests. |
| NFR-S2 | Authorization shall be enforced both in the API (role + area scope) and in the database (Supabase RLS); the service-role key shall exist only on the backend. | M | Negative tests with forged JWT/role; secret scan in CI. |
| NFR-S3 | All traffic shall use TLS 1.2+; data at rest encrypted (Supabase-managed); secrets stored in environment/secret manager, never in repo. | M | SSL Labs, gitleaks. |
| NFR-S4 | Admin accounts shall be separate from operator accounts; privileged config changes (thresholds, policies, roles) require a second approver (FR-64). | M | Test. |
| NFR-S5 | Protection against malicious alerts: no unauthenticated endpoint can create/approve warnings; rate limits on approval and issue endpoints; anomaly alert when a user issues > N warnings/hour; signed outgoing messages where the channel supports it (e.g. web push payload signed, CAP `<signature>` future). | M | Pen-test checklist (OWASP ASVS L2 subset). |
| NFR-S6 | Citizen report endpoint shall be rate-limited per device/IP and reports shall be unverified until triaged; unverified reports never trigger warnings alone. | M | Flood-of-reports test. |
| NFR-S7 | Brute-force protection: lockout/backoff after 5 failed logins; login anomalies logged. | S | Test. |
| NFR-S8 | Dependencies scanned (pip-audit, npm audit) in CI; no known critical CVEs at release. | S | CI report. |
| NFR-S9 | Inputs validated server-side (Pydantic schemas); outputs encoded to prevent XSS; uploads limited to images ≤ 5 MB, re-encoded, EXIF stripped. | M | Tests. |

## 5. Privacy Requirements (PR)

> Each deployment follows its country's data-protection law (pilot: Nepal's *Individual Privacy Act, 2075 (2018)* **[F — team to review relevant sections]**); GDPR-style principles (minimisation, purpose limitation) are adopted as design good practice **[D]**.

| ID | Requirement | Pri | Verification |
|---|---|---|---|
| NFR-PR1 | Data minimisation: subscription requires only area(s), language, channel endpoint (push endpoint or phone). No name, ID number or account is required for citizens. | M | Schema review. |
| NFR-PR2 | Device location shall be used on-device or transiently to resolve an area; it shall not be stored unless the user explicitly opts in to location-based subscription or attaches location to a report/help request. | M | Code review; DB inspection. |
| NFR-PR3 | Phone numbers shall be stored encrypted and indexed by salted hash; operators see only counts, except for help requests where the user consented to share contact. | M | DB inspection. |
| NFR-PR4 | Disability/assistance information shall be voluntary, purpose-limited to evacuation assistance, visible only to scoped responders, and deletable by the user. | M | RLS test. |
| NFR-PR5 | Retention: raw observations kept indefinitely (non-personal); citizen reports' personal fields (contact, precise location of residence) anonymised after 90 days; subscriptions expire after 12 months without renewal; audit log retained ≥ 5 years (configurable) with personal data pseudonymised **[D — values to be validated with authorities]**. | S | Retention job test. |
| NFR-PR6 | Clear privacy notice in ne/en at subscription and report time; consent recorded with timestamp; user can unsubscribe/delete via one link/SMS keyword (e.g. "STOP"). | M | UI review; test. |
| NFR-PR7 | No third-party analytics/ad trackers on citizen pages. | M | Network inspection. |
| NFR-PR8 | Photos in reports shall have EXIF stripped and faces not required; operators warned not to share identifiable images publicly. | S | Test. |
