# Software Requirements Specification (SRS)
## Adaptive Multi-Hazard Early Warning and Evacuation Support System for Nepal (AMHEWS-Nepal)

| Item | Value |
|---|---|
| Document | Software Requirements Specification, structured per ISO/IEC/IEEE 29148:2018 |
| Version | 1.0 (baseline for the 4-week prototype) |
| Status | Draft for team review |
| Project type | University Requirements Engineering project, 4 team members, 4-week delivery |
| Technology | Supabase (PostgreSQL + PostGIS, Auth, Realtime, Storage) · Python 3.12 / FastAPI · Next.js (React, TypeScript) PWA |
| Initial hazard | Riverine flood (architecture prepared for landslide and earthquake) |
| Supporting documents | `docs/01`–`docs/11` (detailed analysis: stakeholders, architecture, use cases, failures, Nepal context, traceability, ethics, team plan) |

### Revision history
| Version | Date | Author | Change |
|---|---|---|---|
| 0.1 | Week 0 | Project Lead | Initial draft from analysis documents |
| 1.0 | Week 0 | Project Lead | Consolidated SRS, re-prioritized for 4-week delivery |

### Approval
| Role | Name | Signature / date |
|---|---|---|
| Project Lead / RE Lead (A) | | |
| Data & Risk Engineer (B) | | |
| Warning & Evacuation Engineer (C) | | |
| Frontend & UX Engineer (D) | | |
| Supervisor / Course instructor | | |

---

## Table of Contents
1. Introduction
2. Overall Description
3. Stakeholder Requirements
4. System Functional Requirements
5. External Interface Requirements
6. Non-Functional Requirements
7. Safety Requirements
8. Security Requirements
9. Privacy Requirements
10. Data Requirements
11. Core vs. Configurable Requirements
12. Use Case Summary
13. Prioritization and 4-Week Release Plan
14. Verification and Validation
15. Traceability
16. Requirements Management and Change Control
17. Assumptions, Dependencies, Constraints and Open Issues
- Appendix A: Glossary
- Appendix B: Risk Level Definitions
- Appendix C: Warning Message Specification
- Appendix D: Conflict Resolutions Embedded in Requirements
- Appendix E: Requirement Quality Checklist

---

## 1. Introduction

### 1.1 Purpose
This SRS defines the stakeholder and system requirements for AMHEWS-Nepal. It is the binding reference for design, implementation, testing and evaluation of the 4-week prototype, and it is the main Requirements Engineering deliverable of the project.

Intended readers: the project team, the course supervisor and examiners, and domain reviewers (disaster-risk-reduction experts, NGO or municipal staff acting as validators).

### 1.2 Product scope
AMHEWS-Nepal is a **decision-support and early-warning system**. It:
- monitors environmental data (simulated river levels and rainfall, plus public forecast APIs);
- assesses flood risk per local area using transparent, configurable rules;
- proposes warnings that authorized humans approve;
- disseminates localized, multilingual, actionable warnings;
- recommends shelters and hazard-aware evacuation routes;
- supports authorities with a monitoring dashboard;
- keeps operating, in degraded form, when data or connectivity fail.

**Objective:** reduce the human impact of floods (casualties, injuries, evacuation delays, misinformation) through earlier, clearer and better-targeted information and coordination.

**The system does NOT:** prevent disasters, guarantee prediction accuracy, guarantee safety, control physical infrastructure, or replace the legal authority of government bodies (DHM, NDRRMA, local governments, security forces).

### 1.3 Definitions, acronyms and abbreviations
See Appendix A. Key terms:
- **Area Unit:** the smallest configured geographic unit for risk (ward or river reach).
- **Level:** NORMAL, WATCH, WARNING, CRITICAL, plus UNKNOWN.
- **Operator:** an authenticated authority user.
- **Approver:** an operator with approval rights for an area.

### 1.4 References
1. ISO/IEC/IEEE 29148:2018 — Requirements engineering.
2. ISO/IEC 25010:2011 — Product quality model.
3. OASIS Common Alerting Protocol (CAP) v1.2.
4. W3C Web Content Accessibility Guidelines (WCAG) 2.2.
5. OWASP Application Security Verification Standard (ASVS) 4.x.
6. Government of Nepal: Disaster Risk Reduction and Management Act, 2074 (2017); Local Government Operation Act, 2074 (2017); Individual Privacy Act, 2075 (2018). *Team to cite the official texts.*
7. National Statistics Office, National Population and Housing Census 2021.
8. WMO/UNDRR "Early Warnings for All": four pillars of people-centred early warning.
9. Project analysis documents `docs/01`–`docs/11`.

### 1.5 Document conventions

| Convention | Meaning |
|---|---|
| **shall** | Mandatory requirement |
| **should** | Desirable requirement |
| **may** | Optional |
| **[F]** | Verified fact (source in `docs/07` §3) |
| **[A]** | Assumption, to be validated |
| **[D]** | Design decision |
| **[T]** | Prototype acceptance target, measured in a simulated/lab environment. **Not a real-world guarantee.** |
| **Priority** | MoSCoW for the 4-week prototype: **M** Must, **S** Should, **C** Could, **W** Won't (this release) |
| **Verification method** | **T** Test, **D** Demonstration, **I** Inspection, **A** Analysis |
| **ID scheme** | `STK-` stakeholder requirement · `FR-` functional · `NFR-PF/A/R/U/SC/M/I` non-functional · `SR-` safety · `SEC-` security · `PRV-` privacy · `DR-` data · `IR-` interface |

**ID rules:** IDs are stable and never reused. Deleted requirements are marked *Withdrawn*.

---

## 2. Overall Description

### 2.1 Product perspective
The system is a new, self-contained web system. It complements existing official mechanisms (DHM flood forecasts and SMS alerts, NDRRMA's BIPAD portal, community-based early warning systems) **[F]**, and interoperates with them via standard formats (CAP, GeoJSON) **[D]**.

```
 External data ──► [Ingest → Validate → Assess risk → Propose warning → Human approval
 (simulated gauges,      → Disseminate → Acknowledge → Log]  ──► Citizens (PWA, SMS-sim, push)
  Open-Meteo, OSM,             ▲             │                ──► Authorities (dashboard)
  boundaries, reports)         │             ▼                ──► Other systems (CAP/JSON)
                          Admin config    Shelters + safe routing
```

### 2.2 Product functions (summary)
1. Data ingestion, validation and data-quality monitoring
2. Area-based risk assessment with confidence and explanation
3. Warning lifecycle management with human approval
4. Multichannel, multilingual notification
5. Citizen information: risk, instructions, shelters, routes, reports
6. Authority dashboard: monitoring, approvals, shelters, reports, delivery status
7. Audit and event logging
8. Configuration of regions, thresholds, templates, roles and policies
9. Degraded and offline operation

### 2.3 User classes and characteristics

| User class | Description | Technical skill | Access | Frequency |
|---|---|---|---|---|
| Citizen (resident, farmer, elderly, person with disability, proxy/carer) | At-risk public | Low to medium; may have a feature phone only **[A]** | Public, no account required | Occasional; intense during events |
| Tourist/visitor | Non-local, often English-speaking | Medium | Public | Rare |
| Community volunteer | Gauge reader, relays warnings | Medium | Public + verified reporter flag | During monsoon |
| Local operator (ward/municipality) | Monitors, proposes, approves within scope | Medium, non-IT | Authenticated, MFA, scoped | Daily in monsoon |
| District/national operator | Coordination, escalation approvals | Medium | Authenticated, MFA, wider scope | During events |
| Responder (police, APF, army, fire, SAR) | Views incidents, closures, help requests | Medium | Authenticated, read-mostly | During events |
| Shelter manager (municipality/NGO) | Updates shelter status | Low to medium | Authenticated, shelter scope | During events |
| Administrator | Configuration, users, data sources | High | Authenticated, MFA, admin | Setup + maintenance |

### 2.4 Operating environment
- **Citizen client:** modern mobile browsers (Chrome on Android as the primary target **[A]**), installable PWA, works on low-end devices and slow networks.
- **Dashboard:** desktop and mobile browsers.
- **Backend:** FastAPI on a container host (Render, Fly.io or Railway).
- **Database:** Supabase cloud (PostgreSQL 15+, PostGIS).
- **Frontend hosting:** Vercel.
- **Character set:** UTF-8 throughout. Devanagari is rendered with a Noto Sans Devanagari web font.

### 2.5 Design and implementation constraints
| ID | Constraint |
|---|---|
| CON-01 | Delivery within **4 weeks** by **4 developers** |
| CON-02 | Stack fixed: Supabase, Python/FastAPI, Next.js |
| CON-03 | No physical sensors; simulated and public data only |
| CON-04 | Free or low-cost tiers; no paid SMS gateway (simulated) |
| CON-05 | Only open data under compatible licences (e.g. OSM under ODbL, with attribution) |
| CON-06 | No real personal data; synthetic users only |
| CON-07 | Every screen and message carries a prototype disclaimer ("PROTOTYPE – NOT AN OFFICIAL WARNING SYSTEM") |
| CON-08 | Warning authority remains with humans and government; the system only proposes |

### 2.6 Assumptions and dependencies
Detailed in §17. Key items:
- Public APIs (Open-Meteo, OSM extracts) remain available.
- Thresholds used are illustrative.
- Stakeholder validation uses proxies where officials are not reachable.

### 2.7 Apportioning of requirements
The requirements are apportioned across releases:
- **R1 (Week 2):** core pipeline.
- **R2 (Week 4):** complete prototype.
- **Future:** Won't-have items.

See §13.

---

## 3. Stakeholder Requirements

Stakeholder needs (StRS level) are derived from the stakeholder analysis (`docs/02`). They are refined into system requirements below.

| ID | Stakeholder need | Stakeholders | Goal | Refined by |
|---|---|---|---|---|
| STK-01 | Know as early as possible when my area may flood | Residents, farmers, elderly | G1 | FR-01..FR-12, FR-18, FR-19 |
| STK-02 | Understand what the warning means and what to do, in my language, even with low literacy or a disability | Residents, elderly, persons with disabilities, tourists | G3.3 | FR-29, FR-31, FR-33, NFR-U1..U6 |
| STK-03 | Receive warnings without a smartphone or mobile data | Feature-phone users, remote communities | G3, G6 | FR-35, FR-49 |
| STK-04 | Know where to go and how to get there safely | Residents, persons with disabilities | G4 | FR-38..FR-46 |
| STK-05 | Report what I see and ask for help | Residents, volunteers | G1, G5 | FR-24, FR-36, FR-37 |
| STK-06 | Trustworthy, evidence-based risk picture for my jurisdiction | Local/district/national authorities | G2, G5 | FR-11..FR-16, FR-51, FR-52 |
| STK-07 | Final authority over high-impact warnings and protection from blame for system errors | Authorities | G3.2, G7 | FR-20..FR-22, FR-59, SR-02 |
| STK-08 | One consistent public voice, never contradicting official warnings | DHM, NDRRMA | G3.1 | FR-28, SR-07 |
| STK-09 | Know whether warnings reached people and how evacuation is progressing | Authorities, police, SAR | G5 | FR-24, FR-54, FR-57 |
| STK-10 | Current shelter and road information | Shelter managers, police, road authorities | G4, G5 | FR-43, FR-55 |
| STK-11 | Personal data, especially location and disability, not misused | Citizens, NGOs | G7 | PRV-01..PRV-08 |
| STK-12 | System cannot be abused to send fake warnings | All | G7 | SEC-01..SEC-09, SR-02 |
| STK-13 | Configure new areas, thresholds and languages without developers | Administrators, municipalities | G8 | FR-63..FR-67 |
| STK-14 | Add other hazards later without redesign | NDRRMA, developers | G8 | NFR-SC2 |
| STK-15 | System keeps helping when internet, power or data sources fail | All | G6 | FR-47..FR-50, SR-06, NFR-A*, NFR-R* |
| STK-16 | Evidence to learn from after each event | NDRRMA, DHM, researchers | G7 | FR-59..FR-62 |

**Goal hierarchy:**
- **G0:** Reduce human impact of floods.
  - **G1:** Know the risk early.
  - **G2:** Assess risk transparently per area.
  - **G3:** Warn the right people correctly.
    - **G3.1:** No contradiction or silent loss.
    - **G3.2:** Human authority.
    - **G3.3:** Understandable by all.
  - **G4:** Enable safe action.
  - **G5:** Coordinate authorities.
  - **G6:** Resilience to infrastructure failure.
  - **G7:** Trust (security, privacy, accountability).
  - **G8:** Adaptability.

---

## 4. System Functional Requirements

> Each requirement has: ID, statement, source stakeholder(s), priority (4-week MoSCoW), rationale, acceptance criteria and verification method. Stakeholder codes S1–S24 are defined in `docs/02`.

### 4.1 Data Collection and Processing (Module M1/M2, owner B)

| ID | Requirement | Source | Pri | Rationale | Acceptance criteria | Ver |
|---|---|---|---|---|---|---|
| FR-01 | The system shall ingest river water-level observations from each configured station at the station's configured interval. | S19, S8 | M | Water level is the primary flood signal. | Simulated station at 60 s for 1 h: ≥ 99 % of readings stored with `observed_at` and `received_at` **[T]**. | T |
| FR-02 | The system shall ingest observed or forecast rainfall for configured points from at least one public weather API. | S19 | M | Rainfall provides lead time before the river rises. | Open-Meteo precipitation stored hourly for configured points; adapter test with a recorded response passes. | T |
| FR-03 | The system shall import static datasets (area boundaries, road network, shelters, population per area) from GeoJSON, CSV or OSM files. | S21, S23 | M | Geography and exposure are prerequisites for localized risk. | Seed import creates area units, road graph and shelters; invalid geometries are rejected with an error report. | T |
| FR-04 | The system may ingest river-discharge forecasts from a public global flood forecast service (GloFAS via Open-Meteo Flood API). | S19 | C | Extra lead time; coarse resolution **[A]**. | Daily forecast stored for ≥ 1 point and tagged `advisory`. | T |
| FR-05 | The system shall provide a scenario player that replays scripted observation timelines as live data. | S22 | M | No physical sensors; scenarios double as test oracles. | Playing a scenario file produces the scripted readings at scripted relative times. | T |
| FR-06 | The system shall validate each observation against schema, unit, physical range and station-specific plausible range. | S19, S21 | M | Bad data must not drive warnings. | Out-of-range values stored as `BAD` and excluded from risk computation; one unit test per rule. | T |
| FR-07 | The system shall detect missing data when no valid observation has arrived from a source/station within its configured staleness window. | S21, S8 | M | Silence must never be read as safety. | With a 5-min window, stopping the simulator opens a `stale` event ≤ 60 s after the window expires **[T]**. | T |
| FR-08 | The system shall flag abnormal values: spikes (change > configured Δ per interval), flatlines (identical values for N intervals) and physically impossible rates. | S19, S21 | M | Sensor faults are a common failure cause **[A]**. | Injected spike, flatline and drop are each flagged `SUSPECT` with the correct reason code. | T |
| FR-09 | The system should detect conflicts between linked sources (e.g. gauge vs. upstream gauge, gauge vs. verified volunteer reports) beyond a configured tolerance and raise a conflict event. | S19, S24 | S | Sources may disagree. | Gauge NORMAL plus 3 verified reports of overtopping raises a conflict event visible on the dashboard. | T |
| FR-10 | The system shall store each observation's source, raw payload and quality flag. | S10, S21 | M | Provenance for audit and analysis. | No `observations` row has a null `source_id`, `quality` or `raw`. | I |

### 4.2 Risk Assessment (Module M3/M4, owner B)

| ID | Requirement | Source | Pri | Rationale | Acceptance criteria | Ver |
|---|---|---|---|---|---|---|
| FR-11 | The system shall compute a flood level (NORMAL, WATCH, WARNING, CRITICAL, UNKNOWN) for every configured Area Unit using the configured rule set (Appendix B, rules R1–R10). | S8, S9 | M | Core function. | For each scripted scenario, levels per area per time step match the scenario oracle 100 % **[T]**. | T |
| FR-12 | The system shall recompute risk for affected areas within 60 s of a new valid observation or a configuration change **[T]**. | S2, S8 | M | Timeliness. | p95 ingest→assessment ≤ 60 s over 100 runs. | T |
| FR-13 | The system shall display risk on a map as area polygons coded by colour, pattern and text label. | S1, S8 | M | Spatial understanding; colour is never the sole cue. | Every area shows a level label; accessibility check passes. | D |
| FR-14 | The system shall store, with each assessment, its inputs, triggered rules, confidence, and engine and configuration version. | S8, S10 | M | Explainability and auditability. | `GET /areas/{id}/risk` returns `reasons[]`; re-running with the stored inputs reproduces the level. | T |
| FR-15 | The system shall assign a confidence (HIGH, MEDIUM, LOW) to each assessment, reduced when key inputs are missing, suspect or conflicting. | S8, S9 | M | Communicates uncertainty. | A stale primary gauge gives LOW confidence and a "Data degraded" badge. | T |
| FR-16 | The system should rank areas at WARNING or above by a configured vulnerability index (population, vulnerable groups, critical facilities). | S6, S8, S17 | S | Prioritizes the most vulnerable. | Priority list order equals a hand calculation on seed data. | T |
| FR-17 | The system may use an advisory statistical/ML forecast as extra evidence. This evidence shall never alone raise the level above WATCH. | S22 | C | Extensibility without compromising safety. | ML-only signal yields at most WATCH with reason `ML_ADVISORY`. | T |

### 4.3 Warning Management (Module M5, owner C)

| ID | Requirement | Source | Pri | Rationale | Acceptance criteria | Ver |
|---|---|---|---|---|---|---|
| FR-18 | When an area's level rises to WATCH or above, the system shall create one warning **proposal**. The proposal contains level, evidence, a suggested message and target areas. | S8 | M | Automated detection with human authority. | A rise to WARNING creates exactly one PROPOSED warning ≤ 60 s **[T]**. | T |
| FR-19 | If region policy `auto_publish_watch` is enabled, WATCH proposals shall become ACTIVE without approval. | S2, S8 | S | WATCH is low-harm and early; reduces approver load. | With the policy on, a WATCH becomes ACTIVE with `actor=system` in the audit log. | T |
| FR-20 | WARNING shall require approval by 1 authorized approver. CRITICAL shall require approval by 2 distinct authorized approvers. Both approvals happen before dissemination. | S8–S10 | M | Human authorization for high-impact actions. | A single approval leaves CRITICAL as PROPOSED; the same user approving twice is rejected; a second distinct approver activates it. | T |
| FR-21 | If a CRITICAL proposal is undecided at the approval timeout, the system shall notify the next authority tier. Where region policy allows, it shall publish the warning labelled "Automated precautionary warning – awaiting official confirmation". | S2, S9 | S | Prevents missed warnings when approvers are unavailable. | Timeout (test: 30 s) produces an escalation notice; with the policy on, the labelled warning is published; both actions are audited. | T |
| FR-22 | Approvers shall be able to edit message text, target areas and validity before approval. Edits shall be recorded. | S8 | M | Local knowledge improves messages. | Diff stored in the audit log. | T |
| FR-23 | The system shall escalate an ACTIVE warning to a higher level as a new version that supersedes the previous one, under the approval rules of the new level. | S2, S8 | M | Situations worsen. | WARNING→CRITICAL creates version 2; version 1 becomes SUPERSEDED; recipients get one escalation message. | T |
| FR-24 | Recipients should be able to acknowledge a warning with one action and optionally choose "I am safe" or "I need help". | S1, S16 | S | Situational awareness. | Ack stored; "need help" creates an incident. | T |
| FR-25 | Operators shall cancel an ACTIVE warning only with a mandatory reason. The system shall then send an all-clear or correction message to every recipient of the cancelled warning. | S1, S8 | M | Corrections must reach the same people. | Cancel without a reason is rejected; all-clear deliveries equal the original deliveries. | T |
| FR-26 | The system shall propose de-escalation only after the lower level has persisted with GOOD-quality data for the configured hold time. | S1, S8 | M | Prevents flapping and alert fatigue. | Oscillating scenario: ≤ 1 level change per hold window. | T |
| FR-27 | Warnings shall expire at `valid_until` unless renewed. Approvers should be reminded 15 min before a WARNING or CRITICAL expires. | S8 | S | Stale warnings erode trust. | Status becomes EXPIRED; the reminder is sent. | T |
| FR-28 | The system shall allow at most one ACTIVE warning per (area, hazard). It shall not publish a level lower than an official/imported warning for the same area and hazard. | S10, S19 | M | Contradictions destroy trust. | A second activation fails at the DB constraint; an official WARNING blocks a system WATCH. | T |
| FR-29 | Each warning shall be rendered from an approved template. The rendered warning shall contain: hazard, level (word, icon, colour), area names, required action, issuing authority, issue time, valid-until and a confidence statement. | S1, S6, S7 | M | Complete, actionable messages. | The template linter rejects any missing field; preview shows Nepali and English. | T |

### 4.4 Citizen Services (Module M8/M10, owners D + C)

| ID | Requirement | Source | Pri | Rationale | Acceptance criteria | Ver |
|---|---|---|---|---|---|---|
| FR-30 | The system shall deliver ACTIVE warnings to every subscription whose area intersects the target areas, through each enabled channel. | S1–S7 | M | Core dissemination. | 1,000 synthetic subscriptions: 100 % of in-area subscriptions get a delivery record and 0 out-of-area subscriptions do **[T]**. | T |
| FR-31 | The citizen interface shall show, for the selected area or the consented current location: level, plain-language action, confidence/data status and last-updated time. | S1, S7 | M | "What is my risk and what do I do?" | Action card text matches the template for each level. | D |
| FR-32 | Users should be able to subscribe to up to 5 areas without an account, including on behalf of another person (proxy). | S1, S4, S6 | S | Migrant family members and carers. | Phone-only subscription works; the proxy label appears in the message. | T |
| FR-33 | The citizen interface shall show level-specific instructions, including what to take and what not to do. | S1, S3 | M | Actionability. | Instructions exist for each level × language; reviewed by a domain proxy. | I |
| FR-34 | The system should resolve a user's area by manual selection, consented device location, or a QR/area code. | S1, S7 | S | Tourists; privacy choice. | Each method returns the correct area for test points. | T |
| FR-35 | The system shall support an SMS channel (simulated gateway) with compact Nepali and English templates of at most 2 segments. | S2, S4 | M | Feature phones; no mobile data. | Template length ≤ 2 segments (UCS-2 for Devanagari); simulator logs the delivery. | T |
| FR-36 | Users should be able to request assistance, which creates an incident visible to the scoped operators. | S4, S6, S24 | S | Vulnerable people need help evacuating. | Request appears on the dashboard ≤ 10 s **[T]**. | T |
| FR-37 | Citizens and volunteers shall be able to report local conditions: category, location, optional water depth, photo and text. | S1, S8, S24 | M | Ground truth; catches what sensors miss. | Report appears on the dashboard with status `new`. *Offline queueing is S.* | T |

### 4.5 Evacuation and Shelters (Module M6/M7, owner C)

| ID | Requirement | Source | Pri | Rationale | Acceptance criteria | Ver |
|---|---|---|---|---|---|---|
| FR-38 | The system shall return the nearest suitable shelters (default 3), ranked by safe-route distance. Only shelters with status `open` and capacity > 0 are returned. | S1, S8 | M | Shelter lookup. | Matches a hand-computed ranking; full or closed shelters are never returned. | T |
| FR-39 | The system should filter shelters by accessibility, medical support and livestock acceptance. | S3, S6 | S | Specific needs. | `accessible=true` returns only accessible shelters. | T |
| FR-40 | The system shall show shelter details: names (ne/en), landmark, capacity, occupancy, last update, facilities and contact. | S1, S17 | M | Informed choice. | All fields displayed, including the occupancy timestamp. | D |
| FR-41 | The system shall compute a walking (default) or vehicle route from the user's location to a selected shelter. | S1 | M | Core evacuation support. | Routes returned for 20 test origin/shelter pairs. | T |
| FR-42 | Routing shall exclude every road segment that intersects an active WARNING or CRITICAL hazard zone, a recorded closure or an unsafe bridge. | S1, S20 | M | Never route people into danger. | 0 of N test routes intersect excluded geometry. | T |
| FR-43 | Operators shall record and remove road and bridge closures with a reason and a time window. | S11, S20 | M | Closures change quickly. | Routes requested after a closure avoid it. | T |
| FR-44 | The system shall provide an alternative route where one exists. When no safe route exists it shall say so explicitly and give fallback advice. | S1 | M | Primary routes get blocked. | No-route scenario returns "no safe route" and the fallback advice, never an unsafe route. | T |
| FR-45 | The system should push updated recommendations to recent route requesters when a closure or hazard change affects their route. | S1 | S | Conditions change during evacuation. | Re-route notice ≤ 60 s **[T]**. | T |
| FR-46 | Routes should carry warnings such as "passes near river" or "road data incomplete". | S1 | S | Honest uncertainty. | Warning text is present for low-confidence segments. | T |

### 4.6 Degraded and Offline Operation (Module M13, owners D + A)

| ID | Requirement | Source | Pri | Rationale | Acceptance criteria | Ver |
|---|---|---|---|---|---|---|
| FR-47 | The citizen PWA shall cache, for subscribed or selected areas, the last risk state, active warnings, instructions, shelter list and emergency numbers. It shall display them offline with a timestamp. | S1, S2 | M | Connectivity fails in disasters. | With the network disabled, the cached content renders with "last updated" shown. | D |
| FR-48 | The system shall show a status page with the health and freshness of each component and data source. | S8, S21 | M | Operators must know what to trust. | A stopped source shows `degraded` ≤ 60 s **[T]**. | T |
| FR-49 | For WARNING and above, the system should fall back to SMS when web push fails. | S2 | S | Channel redundancy. | Simulated push failure leads to an SMS; both attempts are recorded. | T |
| FR-50 | The system should publish a static snapshot of active warnings and shelters every 60 s that remains readable if the backend is down. | S1, S21 | S | Server-crash tolerance. | Backend stopped: static page shows a snapshot ≤ 2 min old. | D |

### 4.7 Authority Dashboard (Module M9, owner D)

| ID | Requirement | Source | Pri | Rationale | Acceptance criteria | Ver |
|---|---|---|---|---|---|---|
| FR-51 | The dashboard shall show a live map, within the operator's scope, of area risk, stations (latest values), active warnings, shelters, closures and reports. | S8–S10 | M | Monitoring. | Updates appear without reload ≤ 5 s after a DB change **[T]**. | D |
| FR-52 | The dashboard shall list areas sorted by level, then vulnerability, with time-in-level and trend. | S8, S9 | M | Prioritization. | Order verified on seed data. | T |
| FR-53 | Operators shall compose manual warnings from templates and preview the recipient count, areas and messages per language before submitting them for approval. | S8, S9 | M | Authorities may know of a risk before the data shows it. | Preview count equals the actual deliveries. | T |
| FR-54 | The dashboard should show evacuation progress: acknowledgements, shelter occupancy vs. capacity, and open assistance requests. | S8, S11 | S | Monitors evacuation. | Indicators update with simulated acks. | D |
| FR-55 | Authorized shelter managers shall update shelter status (open, full, closed, unsafe) and occupancy, and changes shall take effect in recommendations immediately. | S8, S17 | M | Shelter availability changes. | Marking a shelter `full` removes it from FR-38 results on the next request. | T |
| FR-56 | Operators shall triage reports: verify, reject, mark duplicate, convert to incident. | S8, S14 | M | Report volume and misinformation. | Transitions are audited. | T |
| FR-57 | The dashboard shall show per-warning delivery statistics by channel (queued, sent, delivered, failed, acked). | S8, S10 | M | Detects non-delivery. | Stats equal the counts in `deliveries`. | T |
| FR-58 | The system may export ACTIVE warnings as CAP 1.2 XML and a JSON feed. | S10, S18 | C | Interoperability. | Output validates against the CAP 1.2 schema. | T |

### 4.8 Logging and Analysis (Module M11, owner A)

| ID | Requirement | Source | Pri | Rationale | Acceptance criteria | Ver |
|---|---|---|---|---|---|---|
| FR-59 | The system shall write an append-only audit record for every risk change, warning action, delivery batch, configuration change, login and role change. | S10, S21 | M | Accountability. | Audit rows exist for each scenario action; UPDATE and DELETE on the table are denied. *Hash-chain tamper evidence is S.* | T |
| FR-60 | The system should provide an event timeline for a chosen period/area, exportable as CSV or JSON. | S8, S10 | S | After-action review. | Export contains all event types for a scenario run. | D |
| FR-61 | The system may replay a past period with alternative configuration in a sandbox. | S10, S22 | C | Threshold tuning. | Live data is unaffected. | T |
| FR-62 | The system should compute post-event metrics: lead time, false alarms, missed events, delivery rates. | S10, S19 | S | Evaluation. | Metrics report per scenario. | T |

### 4.9 Administration and Configuration (Module M12, owner A for back end, D for UI)

| ID | Requirement | Source | Pri | Rationale | Acceptance criteria | Ver |
|---|---|---|---|---|---|---|
| FR-63 | Admins shall configure regions and area units (boundaries, names per language, hierarchy, population and vulnerability). | S8, S21 | M | Adaptation to new places. | A second municipality is configured from seed files without code change. *Full admin UI is S; seed/CSV import is M.* | D |
| FR-64 | Admins shall configure stations, area–station links and thresholds. Threshold changes shall be versioned. A second approver should be required. | S19, S21 | M | Thresholds are safety-relevant. | Previous versions retrievable. Two-person approval is tested if implemented (S). | T |
| FR-65 | Admins shall manage message templates per hazard × level × language × channel, with mandatory-field linting. | S8, S21 | M | Consistent multilingual messages. | A template with a missing placeholder cannot be saved. | T |
| FR-66 | Admins shall manage users, roles and geographic scopes. | S21 | M | Role-based access control. | A Ward 5 operator cannot approve for Ward 6 (API and RLS tests). | T |
| FR-67 | Admins shall enable or disable hazards and data sources and set region policies (auto-publish WATCH, CRITICAL timeout, precautionary auto-publish). | S10, S21 | M | Adaptive design. | Toggling each policy changes behaviour in its test. | T |

---

## 5. External Interface Requirements

### 5.1 User interfaces

| ID | Requirement | Pri |
|---|---|---|
| IR-UI-01 | The citizen home screen shall show one dominant element: current level + action card + "Find shelter" button. Details are available by progressive disclosure ("Why?"). | M |
| IR-UI-02 | A language switch (नेपाली / English) shall be reachable from every screen. Nepali shall be the default when the browser locale is `ne` **[D]**. | M |
| IR-UI-03 | Levels shall use the fixed colour, icon and wording set in Appendix B. | M |
| IR-UI-04 | Every citizen screen shall show the decision-support disclaimer and the prototype banner. | M |
| IR-UI-05 | The dashboard shall have a three-panel layout (map, area list, action queue). Pending approvals shall always be visible. | M |
| IR-UI-06 | Destructive or high-impact actions (approve CRITICAL, cancel, publish) shall require an explicit confirmation step that restates area, level and recipient count. | M |
| IR-UI-07 | Touch targets shall be ≥ 44 × 44 px. Base font size ≥ 16 px; text scalable to 200 %. | M |

### 5.2 Software interfaces

| ID | Interface | Protocol / format | Pri |
|---|---|---|---|
| IR-SW-01 | Supabase PostgreSQL/PostGIS | SQL over TLS (backend only, service role); PostgREST + RLS for limited client reads | M |
| IR-SW-02 | Supabase Auth | JWT (verified by the backend with the project JWT secret/JWKS); TOTP MFA | M |
| IR-SW-03 | Supabase Realtime | WebSocket subscriptions on `risk_assessments`, `warnings`, `shelters`, `system_status` | M |
| IR-SW-04 | Open-Meteo Forecast API | HTTPS/JSON; timeout 10 s; retry with backoff | M |
| IR-SW-05 | Open-Meteo Flood API (GloFAS) | HTTPS/JSON | C |
| IR-SW-06 | OSM data | One-time extract (Overpass/OSMnx), stored as a graph | M |
| IR-SW-07 | Web Push | VAPID (RFC 8292), via the `pywebpush` library | M |
| IR-SW-08 | SMS gateway (simulated) | REST interface shaped like a real aggregator: `POST /sms {to, text, priority, idempotency_key}` | M |
| IR-SW-09 | CAP feed | OASIS CAP 1.2 XML | C |

### 5.3 Backend API (REST, JSON, versioned `/api/v1`)

| Endpoint | Access | Requirement |
|---|---|---|
| `GET /areas/{id}/risk` | Public | FR-14, FR-31 |
| `GET /risk/map?region=&hazard=` (GeoJSON) | Public | FR-13 |
| `GET /warnings/active?area=` or `?lat=&lon=` | Public | FR-30, FR-31 |
| `POST /subscriptions` · `DELETE /subscriptions/{token}` | Public | FR-32, PRV-06 |
| `GET /shelters/nearest?lat=&lon=&accessible=&limit=` | Public | FR-38, FR-39 |
| `POST /evacuation/route` | Public | FR-41..FR-44 |
| `POST /reports` | Public (rate-limited) | FR-37 |
| `POST /warnings` · `/{id}/approve` · `/reject` · `/cancel` · `/escalate` | Operator (scoped, MFA) | FR-20..FR-25 |
| `GET /warnings/{id}/recipients/preview` · `GET /deliveries/stats` | Operator | FR-53, FR-57 |
| `POST /warnings/{id}/ack` | Recipient token | FR-24 |
| `PATCH /shelters/{id}` · `POST /road-closures` · `PATCH /reports/{id}` | Operator / shelter manager | FR-43, FR-55, FR-56 |
| `/admin/*` (regions, stations, thresholds, templates, users, policies) | Admin | FR-63..FR-67 |
| `POST /sim/scenarios/{name}/play` | Admin, non-production only | FR-05 |
| `GET /health` · `GET /status` | Public | FR-48 |

**General API requirements:**
- **IR-API-01:** OpenAPI 3 specification generated and published.
- **IR-API-02:** Errors use RFC 9457 problem+json.
- **IR-API-03:** All timestamps in ISO 8601 UTC; the UI displays Nepal Time (UTC+05:45) **[F]**.
- **IR-API-04:** Geometry in GeoJSON, WGS84 (EPSG:4326).

### 5.4 Hardware and communication interfaces
- No hardware interfaces in the prototype; sirens are simulated through `ChannelAdapter`.
- **IR-COM-01:** All external communication uses HTTPS with TLS 1.2 or later.
- **IR-COM-02:** The channel adapter interface is `send(message, recipient) -> DeliveryResult{status, provider_id, error}`, so that real SMS, cell broadcast, IVR or siren adapters can replace the simulators.

---

## 6. Non-Functional Requirements

### 6.1 Performance (PF)
| ID | Requirement | Pri | Measurement |
|---|---|---|---|
| NFR-PF1 | Alert generation latency (valid observation stored → warning PROPOSED) ≤ 60 s at p95 **[T]**. | M | Instrumented timestamps, 100 runs |
| NFR-PF2 | Dispatch of 1,000 recipients (ACTIVE → handed to channel) ≤ 60 s **[T]**; CRITICAL dispatched first. Delivery to the handset depends on external networks; it is measured, not guaranteed. | M | Load test |
| NFR-PF3 | Public read API ≤ 1 s p95; route API ≤ 3 s p95 at 50 concurrent users **[T]**. | M | k6/Locust |
| NFR-PF4 | Citizen home page ≤ 300 KB compressed (excluding map tiles); interactive within 5 s on a throttled "slow 3G" profile **[T]**. | S | Lighthouse |
| NFR-PF5 | Dashboard realtime updates ≤ 5 s after the DB change **[T]**. | M | Timestamp comparison |

### 6.2 Availability (A)
| ID | Requirement | Pri | Measurement |
|---|---|---|---|
| NFR-A1 | Public endpoints ≥ 99 % available over a continuous 72-h test window **[T]**. A production target would be set by authorities and is not claimed here. | S | Uptime monitor |
| NFR-A2 | A static fallback page (FR-50) shall be independent of the backend and database. | S | Kill test |
| NFR-A3 | The backend shall be stateless, so that ≥ 2 instances can run. Scheduled jobs shall use DB advisory-lock leader election. | C | Two-instance test |
| NFR-A4 | No deployment while any area is at WARNING or above (maintenance freeze). | S | Deploy script check |

### 6.3 Reliability (R)
| ID | Requirement | Pri | Measurement |
|---|---|---|---|
| NFR-R1 | Only GOOD observations, or SUSPECT ones with reduced confidence, shall drive risk computation. | M | Fault injection |
| NFR-R2 | Adapter failures shall be isolated: 10 s timeouts, exponential backoff, circuit breaker. | M | Mock 500/timeout |
| NFR-R3 | Notification delivery shall be at-least-once with idempotency keys: no lost and no duplicate (warning version, recipient, channel). | M | Crash mid-batch test |
| NFR-R4 | After a restart, jobs resume and all areas are recomputed within ≤ 2 min **[T]**. | M | Restart test |
| NFR-R5 | Daily backups shall be in place; the restore procedure shall be documented and rehearsed once. | S | Drill record |

### 6.4 Usability and Accessibility (U)
| ID | Requirement | Pri | Measurement |
|---|---|---|---|
| NFR-U1 | Emergency screens shall have one primary action and plain language. ≥ 80 % of test users shall identify the correct action within 30 s **[T]**. | M | Usability test |
| NFR-U2 | Citizen pages shall conform to WCAG 2.2 AA. | M | axe-core + manual screen reader |
| NFR-U3 | Levels shall be conveyed by word, icon, colour and optional sound/vibration; never by colour alone. | M | Inspection |
| NFR-U4 | Nepali and English shall be complete for all citizen strings and templates. New languages shall be added via language packs without code change. | M | Dummy pack test |
| NFR-U5 | A "read aloud" (browser text-to-speech) option should exist for the action card. | S | Demo |
| NFR-U6 | Approving a warning shall take ≤ 3 clicks from the notification, with the evidence on the same screen. | S | Task analysis |
| NFR-U7 | Citizen interface SUS score ≥ 68 **[T]** (68 is the commonly cited SUS average). | S | SUS questionnaire |

### 6.5 Scalability (SC)
| ID | Requirement | Pri |
|---|---|---|
| NFR-SC1 | A region shall be added by configuration and data import only. | M |
| NFR-SC2 | A hazard shall be added through a `HazardModel` plug-in, configuration rows and templates, with no change to core tables or to the warning/notification modules. This shall be demonstrated with a landslide stub. | S |
| NFR-SC3 | A data source shall be added through one adapter class and one `data_sources` row. | M |
| NFR-SC4 | The scaling path to national volume (queue-based dispatch, operator broadcast, pgRouting/OSRM) shall be documented. | C |

### 6.6 Maintainability (M)
| ID | Requirement | Pri |
|---|---|---|
| NFR-M1 | Modules shall interact only through defined service interfaces. | S |
| NFR-M2 | Thresholds, policies, templates, languages, channels and regions shall be configuration, never hard-coded. | M |
| NFR-M3 | Line coverage ≥ 80 % on safety modules (validation, risk, warning state machine, routing filter) **[T]**. | M |
| NFR-M4 | Schema changes shall be made only via versioned SQL migrations. | M |
| NFR-M5 | Code style shall be enforced in CI: ruff/black for Python, ESLint/Prettier for TypeScript. | S |

### 6.7 Interoperability (I)
| ID | Requirement | Pri |
|---|---|---|
| NFR-I1 | Warnings shall be exportable as CAP 1.2. | C |
| NFR-I2 | Exchange shall use GeoJSON with WGS84 coordinates. | M |
| NFR-I3 | Channel adapters shall share a common interface (IR-COM-02). | M |
| NFR-I4 | Data adapters shall support both pull (HTTP/CSV) and push (webhook) ingestion. | S |
| NFR-I5 | OSM attribution shall be displayed (ODbL). | M |

### 6.8 Portability and Localization
| ID | Requirement | Pri |
|---|---|---|
| NFR-L1 | All persisted text shall be UTF-8. Dates shall be shown in the Gregorian calendar, with Bikram Sambat (BS) optional. | S (BS = C) |
| NFR-L2 | Numbers shall be displayable in Devanagari numerals in the Nepali UI. | C |
| NFR-L3 | The system shall be deployable to any PostgreSQL 15+ host with PostGIS (no Supabase-only SQL in core logic). | S |

---

## 7. Safety Requirements

> These are derived from the hazard and failure analysis (`docs/06`, failure scenarios F1–F20).
>
> **Verification rigour:** every SR needs ≥ 1 automated unit/property test **and** ≥ 1 end-to-end scenario test. Code changes to SR modules require 2 reviewers, one of them the Project Lead.

| ID | Safety requirement | Hazard / failure mitigated | Pri | Verification |
|---|---|---|---|---|
| SR-01 | No warning shall be silently dropped. Every target subscription of an ACTIVE warning shall reach a final delivery state (delivered, acked, or failed with a reason). Failed deliveries for WARNING or above shall be shown to operators. | F10, F11 | M | Channel failure scenario |
| SR-02 | WARNING requires ≥ 1 and CRITICAL requires ≥ 2 distinct authorized human approvals. The only exception is the policy-controlled, labelled precautionary path (FR-21). | F16, F17 | M | State machine tests |
| SR-03 | Routing shall never return a route intersecting an active WARNING/CRITICAL hazard zone, a closure or an unsafe bridge. If no safe route exists it shall return "no safe route" with fallback advice. | F12 | M | Property test (≥ 1,000 random origins) |
| SR-04 | Each route and shelter recommendation shall display its data timestamp and limitations. | F12, F14 | M | UI test |
| SR-05 | Shelters inside an active WARNING/CRITICAL zone, or marked full, closed or unsafe, shall never be recommended. | F13 | M | Test |
| SR-06 | Missing, stale or invalid data shall never by itself lower an area's level. It shall lower confidence and alert operators. | F4, F5, F6 | M | Gauge-outage scenario |
| SR-07 | No system-issued level shall be lower than an official warning for the same area and hazard. Every warning shall name its issuing authority. | F7 | M | Contradiction guard test |
| SR-08 | Confidence shall be shown with every risk display and warning. LOW-confidence CRITICAL proposals shall be highlighted to approvers together with their reasons. | F6, F8 | M | UI + API test |
| SR-09 | Cancellations and corrections shall reach every recipient of the original warning through the same channels. | F17 | M | Count-equality test |
| SR-10 | Every citizen screen and message shall state that the system is decision support and that on-site official instructions take precedence. | F18 | M | Content inspection |
| SR-11 | A forecast-only or ML-only signal shall not raise the level above WATCH. | F8, F19 | M | Test |
| SR-12 | Simulated data shall be flagged. In `exercise` mode every message shall be prefixed "EXERCISE – NOT A REAL WARNING". Simulated data shall be rejected in `live` mode. | F16, F17 | M | Mode test |

---

## 8. Security Requirements

| ID | Requirement | Pri | Verification |
|---|---|---|---|
| SEC-01 | Operator and admin accounts shall use MFA (TOTP). Approval actions require an MFA-verified session (`aal2`). | S (password + role scope is M) | Login tests |
| SEC-02 | Authorization shall be enforced in the API (role + area scope) **and** in the database (RLS). The service-role key shall exist only on the backend. | M | Forged JWT and wrong-scope tests; secret scan |
| SEC-03 | TLS 1.2+ for all traffic. Secrets only in environment variables or a secret store; never in Git. | M | gitleaks in CI |
| SEC-04 | Admin and operator roles shall be separate. Privileged configuration changes shall be audited. | M | Test |
| SEC-05 | No unauthenticated endpoint shall create, approve or cancel warnings. Warning endpoints shall be rate-limited. A user issuing more than N warnings per hour shall trigger an anomaly alert. | M | Penetration-test checklist (OWASP ASVS L1 subset) |
| SEC-06 | The report endpoint shall be rate-limited per IP/device. Unverified reports shall never alone trigger warnings. | M | Flood-of-reports test |
| SEC-07 | Login attempts shall be throttled after repeated failures. | S | Test |
| SEC-08 | Dependency scanning (pip-audit, npm audit) in CI; no known critical CVEs at release. | S | CI report |
| SEC-09 | Server-side input validation (Pydantic). Output encoding against XSS. Image uploads ≤ 5 MB, re-encoded, EXIF stripped. | M | Tests |

---

## 9. Privacy Requirements

> Basis: Nepal's Individual Privacy Act, 2075 (2018) **[F — team to review]**, plus privacy-by-design principles **[D]**.

| ID | Requirement | Pri | Verification |
|---|---|---|---|
| PRV-01 | Data minimisation: a subscription stores only area(s), language, channel endpoint and consent time. No name or ID number is required. | M | Schema inspection |
| PRV-02 | Device location shall be used transiently to resolve an area. It shall be stored only with explicit opt-in (location subscription, report or help request). | M | Code and DB inspection |
| PRV-03 | Phone numbers shall be encrypted at rest and looked up by salted hash. Operators see aggregates only, except for consented help requests. | S | DB inspection |
| PRV-04 | Disability/assistance data shall be voluntary, used only for assistance, visible only to scoped responders, and deletable. | M | RLS test |
| PRV-05 | Retention: personal fields in reports anonymised after 90 days; subscriptions expire after 12 months; audit personal data pseudonymised. Values are **[D]** and to be validated. | S | Retention job test |
| PRV-06 | A privacy notice in Nepali and English shall be shown at consent. Unsubscribe or delete shall take one action (link or "STOP"). | M | UI review |
| PRV-07 | No third-party analytics or advertising trackers on citizen pages. | M | Network inspection |
| PRV-08 | Report photos shall have EXIF stripped. Operators shall be advised not to publish identifiable images. | S | Test |

---

## 10. Data Requirements

### 10.1 Logical data entities
| ID | Entity | Key attributes | Owner module |
|---|---|---|---|
| DR-01 | Region / Area Unit | code, names (ne/en), hierarchy, geometry (MultiPolygon), population, vulnerability index, coverage flag | Admin |
| DR-02 | Station / Data Source | type, location, poll interval, staleness window, licence, upstream links + travel time | Data |
| DR-03 | Threshold | station, hazard, watch/warning/danger levels, rise rate, rainfall threshold, version, provenance, approver | Admin |
| DR-04 | Observation | source, station, variable, value, unit, observed_at, received_at, quality, raw, is_simulated | Data |
| DR-05 | Data Quality Event | kind (missing, stale, spike, flatline, range, conflict), opened/closed, detail | Data |
| DR-06 | Risk Assessment | area, hazard, level, confidence, reasons, inputs, computed_at, valid_until, engine version | Risk |
| DR-07 | Warning | series, version, areas, hazard, level, status, source (auto/manual/official), approvers, messages per language, validity | Warning |
| DR-08 | Subscription | areas, language, channels, endpoint, accessibility prefs, proxy label, consent, expiry | Notification |
| DR-09 | Delivery | warning, subscription, channel, status, attempts, error, timestamps, ack | Notification |
| DR-10 | Shelter | names, location, capacity, occupancy, status, accessibility, livestock, medical, contact, updated_by/at | Shelter |
| DR-11 | Road Closure / Hazard Zone | geometry, reason, source, validity window | Evacuation |
| DR-12 | Citizen Report / Incident | category, location, depth, photo, status, verifier | Reports |
| DR-13 | Audit Log | time, actor, action, entity, payload, prev_hash, hash | Audit |
| DR-14 | Profile / Role | user, role, area scope, MFA required | Auth |

### 10.2 Data quality requirements
| ID | Requirement | Pri |
|---|---|---|
| DR-Q1 | Every observation shall carry a quality flag from {GOOD, SUSPECT, BAD, MISSING}. | M |
| DR-Q2 | Area geometries shall be valid (`ST_IsValid`) and areas at the same hierarchy level shall not overlap (tolerance configurable). | M |
| DR-Q3 | Thresholds shall be monotonic: watch < warning < danger. | M |
| DR-Q4 | Every configured area shall be linked to ≥ 1 station or explicitly flagged "no monitoring". | M |
| DR-Q5 | Shelter occupancy older than a configured age (default 2 h) shall be shown as "may be outdated". | S |

### 10.3 Retention summary
| Data | Retention |
|---|---|
| Observations, assessments, warnings | Kept for analysis (non-personal) |
| Reports' personal fields | 90 days |
| Subscriptions | 12 months |
| Audit log | ≥ 5 years, pseudonymised (configurable) |

All values are **[D]**, to be validated with authorities.

---

## 11. Core vs. Configurable Requirements

| Category | Requirements | May a deployment change it? |
|---|---|---|
| **Core (safety invariants)** | FR-06..FR-08, FR-25, FR-28, FR-59, SR-01..SR-12, SEC-02, SEC-05, PRV-01, PRV-02 | **No.** Only the parameters inside them (e.g. number of approvers ≥ 1 for the highest level) |
| **Configurable (context)** | Country/admin hierarchy, area granularity, hazards enabled, thresholds, languages, channels and fallbacks, approval tiers and timeouts, auto-publish policies, poll intervals, retention periods, routing mode defaults, emergency numbers | **Yes**, through validated, versioned, audited configuration (FR-63..FR-67) |

Detailed per-dimension examples (countries, rural vs. urban, government structures) are in `docs/07` §2.

---

## 12. Use Case Summary

Full specifications, with actors, preconditions, triggers and main, alternative and exception flows, are in `docs/05`.

| UC | Name | Primary actor | Key requirements | Pri (4 wk) |
|---|---|---|---|---|
| UC-01 | Citizen receives flood warning | Citizen | FR-29, FR-30, FR-35, SR-01 | M |
| UC-02 | Citizen checks local risk level | Citizen | FR-13..FR-15, FR-31, FR-47 | M |
| UC-03 | Citizen requests evacuation guidance | Citizen | FR-41..FR-44, SR-03 | M |
| UC-04 | Citizen finds nearest shelter | Citizen | FR-38, FR-40, SR-05 | M |
| UC-05 | Citizen reports flooding | Citizen/Volunteer | FR-37, FR-56, SEC-06 | M |
| UC-06 | Authority monitors flood risk | Operator | FR-48, FR-51, FR-52, FR-57 | M |
| UC-07 | Authority issues emergency warning | Operator/Approver | FR-20, FR-22, FR-25, FR-28, FR-53 | M |
| UC-08 | Authority updates shelter availability | Shelter manager | FR-55 | M |
| UC-09 | System detects abnormal data | System | FR-06, FR-08 | M |
| UC-10 | System generates automatic risk assessment | System | FR-11, FR-12, FR-18, FR-26 | M |
| UC-11 | System handles unavailable data | System | FR-07, FR-15, SR-06 | M |
| UC-12 | System handles conflicting data | System/Operator | FR-09 | S |
| UC-13 | Administrator configures a region | Admin | FR-63..FR-67 | M (seed import) / S (UI) |

---

## 13. Prioritization and 4-Week Release Plan

### 13.1 Method
1. Each requirement is scored for safety contribution (35 %), core-to-research-question (25 %), stakeholder value (20 %) and feasibility in 4 weeks (20 %). MoSCoW is then applied.
2. **Override:** anything implementing a safety requirement is **Must**.
3. **Capacity rule:** Must items are capped at ~60 % of the team's capacity, about 4 people × 4 weeks × ~15 h/week ≈ 240 h **[A]**. Should items fill the rest, and Could items are done only if time remains.

### 13.2 Summary
| Priority | Count (approx.) | Content | Reasoning |
|---|---|---|---|
| **Must** | FR: 46 · NFR: 20 · SR: 12 · SEC: 6 · PRV: 5 | End-to-end flow for one pilot area: simulated data → validation → risk → proposal → approval → ne/en delivery (web push + SMS simulator) → citizen view → shelter + safe route → dashboard → audit | This is the minimum that answers the research question and demonstrates every safety requirement |
| **Should** | FR: 17 (+ NFR, SEC-01 MFA) | Conflict detection, auto-WATCH, timeout escalation, acks, proxy subscription, QR/location, assistance requests, filters, re-routing, SMS fallback, static fallback, evacuation progress, timeline, metrics, MFA, admin UI, offline report queue, landslide stub | Valuable but the system is still safe and demonstrable without them; scheduled for week 4 |
| **Could** | FR-04, FR-17, FR-58, FR-61, NFR-A3, NFR-SC4, NFR-I1 | GloFAS, ML advisory, CAP, replay, multi-instance | Extensibility showcases; low safety value per hour |
| **Won't (this release)** | — | Real SMS/cell broadcast/IVR, real DHM/BIPAD integration, sensors/sirens, native apps, languages beyond ne/en, full landslide/earthquake models, production operations | External agreements, cost or out of scope; interfaces are specified so they can be added later |

### 13.3 4-week schedule
| Week | Release goal | Requirements delivered |
|---|---|---|
| **Week 1: Foundations + elicitation** | Requirements baseline v1.0 signed. Schema, RLS and seed data live. Scenario player emits data. UI skeleton (ne/en) against a mock API. Interviews and questionnaire launched. | FR-03, FR-05, FR-10, FR-66, NFR-M4, SEC-02, SEC-03, IR-API-* |
| **Week 2: Core pipeline (R1)** | Data → risk → proposal → approval → delivery works end-to-end for one area. **Validation round 1** (walkthrough with proxies). | FR-01, FR-02, FR-06..FR-08, FR-11..FR-15, FR-18, FR-20, FR-22, FR-28, FR-29, FR-30, FR-31, FR-13, FR-59, SR-02, SR-06, SR-07 |
| **Week 3: Evacuation + dashboard + degraded mode** | Shelters, safe routing, closures, cancel/escalate, SMS simulator, dashboard, status page, offline cache. | FR-23, FR-25, FR-26, FR-33, FR-35, FR-37, FR-38, FR-40..FR-44, FR-47, FR-48, FR-51..FR-53, FR-55..FR-57, FR-63..FR-65, FR-67, SR-01, SR-03..SR-05, SR-08..SR-12 |
| **Week 4: Should items + validation + report (R2)** | Should items as capacity allows. **Validation round 2** (usability and comprehension tests). Full test run, traceability check, final report, demo. | Should list in §13.2; all NFR measurements; RTM 100 % for Must |

**Freeze rules:**
- **Feature freeze:** end of day 3 of week 4.
- **After the freeze:** only bug fixes, tests, documentation and the demo.

---

## 14. Verification and Validation

### 14.1 Verification (are we building the system right?)
| Requirement class | Primary method | Tooling |
|---|---|---|
| Functional logic (data, risk, warnings, routing) | Unit, property-based and scenario tests | pytest, hypothesis, scenario oracles |
| Database security (RLS) | Integration tests with role-specific JWTs | pytest against local Supabase (CLI/Docker) |
| UI behaviour | E2E tests | Playwright |
| Performance | Load tests | k6 or Locust |
| Accessibility | Automated + manual | axe-core, Lighthouse, NVDA/TalkBack |
| Security | Negative tests, scans | OWASP ZAP baseline, gitleaks, pip-audit/npm audit |
| Privacy, content, templates | Inspection | Checklists, DB inspection |

**Scenario test catalogue** (each is a scripted data timeline with an expected-outcome oracle):

| ID | Scenario | ID | Scenario |
|---|---|---|---|
| ST-01 | Normal day | ST-08 | Push channel failure |
| ST-02 | Gradual rise to WARNING | ST-09 | Shelter inside new hazard zone |
| ST-03 | Flash rise (rate-of-rise rule) | ST-10 | All routes cut |
| ST-04 | Gauge outage at WARNING | ST-11 | Configure second municipality |
| ST-05 | Oscillation around a threshold | ST-12 | Spoofed / unauthorized warning attempts |
| ST-06 | CRITICAL with absent approver | ST-13 | Exercise-mode drill |
| ST-07 | Gauge vs. volunteer-report conflict | ST-14 | Erroneous warning cancelled |

### 14.2 Validation (are we building the right system?)
| Activity | Participants | When | Output |
|---|---|---|---|
| Requirements walkthrough | Supervisor, DRR/NGO proxy, peers | End of week 1 | Review defects, baseline v1.0 |
| Scenario walkthrough of failure cases | Domain proxies | Week 2 | Accepted or rejected resolutions |
| Prototype demo (validation round 1) | Proxies for residents and operators | End of week 2 | Change requests |
| Usability + level-comprehension test (validation round 2) | ≥ 5 citizen proxies (incl. elderly/low-literacy where possible), ≥ 2 operator proxies | Week 4 | SUS, task success, comprehension % |
| Quality inspection (Appendix E) | Team + peer team | Weeks 1 and 4 | Checklist pass rate |

### 14.3 Evaluation metrics
| Metric | Definition | Target **[T]** |
|---|---|---|
| Warning generation latency | Observation → PROPOSED, p95 | ≤ 60 s |
| Dispatch time | ACTIVE → 1,000 handed to channels | ≤ 60 s |
| Classification correctness | Match with scenario oracle | 100 % (rules are deterministic, so any mismatch is a defect; this makes no claim about real hydrology) |
| False negatives | Safety scenarios without WARNING+ before peak | 0 |
| False positives | WARNING+ where the oracle has none | Reported and reviewed; no hard cap (trade-off C1) |
| Route validity | Routes intersecting excluded geometry | 0 |
| Shelter validity | Unsuitable shelters recommended | 0 |
| Availability | 72-h public endpoint uptime | ≥ 99 % |
| Delivery integrity | Final state reached; duplicates | 100 %; 0 |
| Usability | SUS; task success; comprehension | ≥ 68; ≥ 80 %; ≥ 80 % |
| Accessibility | axe critical violations | 0 |
| Requirements traceability | Must requirements traced back to a stakeholder and forward to a test | 100 % |
| Requirements consistency | Open conflicts | 0 |
| Requirements quality | Pass rate on Appendix E checklist | 100 % at baseline |

---

## 15. Traceability

The full matrix (Stakeholder → Goal → Requirement → Use Case → Component → Test) is in `docs/08` §3.

**Traceability rules (checked in CI by `scripts/rtm.py`):**
1. Every Must FR traces to ≥ 1 stakeholder need (STK), ≥ 1 use case or system process, ≥ 1 design component, and ≥ 1 test.
2. Every SR traces to ≥ 1 failure scenario, ≥ 1 unit/property test and ≥ 1 scenario test.
3. Every test references ≥ 1 requirement (no orphan tests).
4. Every goal G1–G8 has ≥ 1 Must requirement.

**Mechanics:**
- Tests are tagged `@pytest.mark.req("FR-42")` (backend) or `test("FR-42 …")` (Playwright).
- Commits and PR titles start with the requirement ID.

**Condensed trace of safety-critical requirements:**

| Requirement | STK | Goal | UC | Component | Tests |
|---|---|---|---|---|---|
| SR-01 / FR-30 | STK-01, 09 | G3.1 | UC-01 | Notification dispatcher | ST-08, IT-30 |
| SR-02 / FR-20 | STK-07, 12 | G3.2 | UC-07 | Warning manager + RLS | UT-20, ST-12 |
| SR-03 / FR-42 | STK-04 | G4 | UC-03 | Evacuation router | PT-42, ST-10 |
| SR-05 / FR-38 | STK-04 | G4 | UC-04 | Shelter module | UT-38, ST-09 |
| SR-06 / FR-07 | STK-15 | G6 | UC-11 | Processing + risk engine | ST-04 |
| SR-07 / FR-28 | STK-08 | G3.1 | UC-07 | Warning manager + DB index | UT-28, IT-28 |
| SR-09 / FR-25 | STK-07 | G3.1 | UC-07 | Warning manager + dispatcher | ST-14 |
| SR-12 | STK-12 | G7 | UC-07 | Warning manager | ST-13 |

---

## 16. Requirements Management and Change Control

| Aspect | Rule |
|---|---|
| **Storage** | This SRS (Markdown in Git) is the baseline. Optionally requirements are mirrored as YAML (`docs/requirements/*.yaml`) for the RTM script. |
| **Baselines** | v1.0 at end of week 1; v1.1 after validation round 1 (end of week 2); v2.0 final (week 4). |
| **Attributes tracked** | ID, statement, source, priority, rationale, acceptance criteria, verification method, owner, status (Proposed → Approved → Implemented → Verified), trace links. |
| **Change request** | GitHub issue labelled `change-request` stating: requirement IDs, proposed change, reason/source, impact (via trace links), safety impact (Y/N), effort, decision. |
| **Change Control Board** | Project Lead (chair) + the owner of the affected module. Meets at the twice-weekly sync. Changes with safety impact need the **whole team** plus re-running the affected SR scenario tests. |
| **Volatile requirements** | Thresholds, policies, templates and languages are designed as configuration (§11), so changing them is a configuration change, not a requirement change. |
| **Ambiguity log** | Terms such as "timely", "nearby" and "safe route" are recorded with their resolution (see `docs/09` §1.1). |

---

## 17. Assumptions, Dependencies, Constraints and Open Issues

### 17.1 Assumptions
| ID | Assumption | Affects | Validation plan |
|---|---|---|---|
| AS-01 | Flood lead times on the pilot river are hours, so a 60 s processing latency is adequate | NFR-PF1 | Domain-expert review |
| AS-02 | Many at-risk users have Android phones with intermittent data, and some have feature phones only | FR-35, NFR-PF4 | Questionnaire |
| AS-03 | Approvers may be unavailable at night | FR-21 | Official interviews |
| AS-04 | OSM road coverage in the pilot area is adequate for demo routing | FR-41..FR-44 | Map inspection in week 1 |
| AS-05 | Illustrative thresholds are acceptable for the prototype; real ones come from DHM | FR-11 | Stated as a limitation |
| AS-06 | Proxies (e.g. students from Terai districts, NGO staff) can represent residents for validation | §14.2 | Acknowledged limitation |
| AS-07 | Team capacity is ~15 h/person/week | §13 | Weekly tracking |

### 17.2 Dependencies
- Supabase, Vercel and the backend host (free tiers).
- Open-Meteo API.
- OSM data.
- Web Push support in target browsers. iOS needs the PWA installed to receive push **[F — Apple, iOS 16.4+]**.

### 17.3 Open issues (TBD register)
| ID | Issue | Owner | Due |
|---|---|---|---|
| TBD-01 | Choose the pilot river/municipality and confirm data availability | B | Week 1 day 2 |
| TBD-02 | Approval timeout and auto-publish policy defaults to confirm with a domain proxy | A | Week 2 |
| TBD-03 | Nepali wording of level names and actions to review with native speakers | D | Week 2 |
| TBD-04 | Census figures for literacy and disability, and NTA mobile penetration figures | B | Week 2 |
| TBD-05 | Retention periods to review against the Individual Privacy Act | A | Week 3 |

---

## Appendix A — Glossary

| Term | Definition |
|---|---|
| **Area Unit** | Smallest configured geographic unit for which risk is computed (ward or river reach) |
| **Approver** | Operator authorized to approve warnings for an area |
| **CAP** | Common Alerting Protocol (OASIS), international public-warning format |
| **CBEWS** | Community-Based Early Warning System |
| **Confidence** | HIGH, MEDIUM or LOW: the system's assessment of input data adequacy for a risk level |
| **DHM** | Department of Hydrology and Meteorology, Nepal |
| **Hazard zone** | Polygon in which a hazard is assessed or reported at a given level |
| **Hysteresis / hold time** | Minimum duration of consistently lower readings before de-escalation |
| **MFA** | Multi-factor authentication |
| **NDRRMA** | National Disaster Risk Reduction and Management Authority, Nepal |
| **Proposal** | System- or operator-created warning awaiting approval |
| **PWA** | Progressive Web App (installable, offline-capable web app) |
| **RLS** | Row-Level Security (PostgreSQL) |
| **Scenario oracle** | Expected outputs defined in advance for a scripted data timeline |
| **Stale** | No valid data received within the configured window |
| **SUS** | System Usability Scale |

## Appendix B — Risk Level Definitions [D]

| Level | Meaning | Citizen action (template basis) | Colour | Icon | Approval | Notification behaviour |
|---|---|---|---|---|---|---|
| **NORMAL** | No elevated flood risk detected | Stay informed | Green | ✓ circle | — | None |
| **WATCH** | Conditions may lead to flooding | Prepare: charge phone, pack go-bag, know your shelter, help elderly neighbours plan | Yellow | Eye | Auto (policy) or 1 | In-app; SMS opt-in |
| **WARNING** | Flooding likely in this area | Move valuables, livestock and vulnerable people to safety; be ready to evacuate | Orange | Triangle ! | 1 approver | Push + SMS |
| **CRITICAL / EVACUATE** | Flooding occurring or imminent | Evacuate now to the nearest safe shelter or high ground; do not cross flowing water | Red | Running person ↑ | 2 approvers | Push + SMS, repeated (≤ 2 reminders); cannot be muted |
| **UNKNOWN** | Insufficient data | Follow local authorities; data delayed | Grey | ? | — | Operators only |

**Rule set (flood plug-in, all thresholds configurable):**

| Rule | Logic |
|---|---|
| **R1–R3** | Water level vs. danger, warning and watch thresholds |
| **R4** | Rate of rise ≥ threshold for N readings: +1 level |
| **R5** | Upstream station at WARNING or above sets the downstream area to WATCH or above (WARNING if upstream is CRITICAL) |
| **R6** | 24-h rainfall ≥ threshold: WATCH or above |
| **R7** | Forecast alone: at most WATCH |
| **R8** | Missing/stale data: hold the last level, confidence LOW, never downgrade |
| **R9** | Final level = maximum of all rules; the vulnerability modifier may raise WATCH to WARNING |
| **R10** | De-escalate only after the hold time with GOOD data |

## Appendix C — Warning Message Specification

| Field | Required | Example (en) | Example (ne) |
|---|---|---|---|
| Header | M | "FLOOD WARNING" | "बाढी चेतावनी" |
| Level word + icon | M | "WARNING ⚠" | "चेतावनी ⚠" |
| Area | M | "Ward 5, Rajapur Municipality" | "राजापुर नगरपालिका, वडा ५" |
| Action | M | "Move livestock and elderly people to higher ground now." | *(native speaker to finalize — TBD-03)* |
| Issuer | M | "Issued by: Rajapur Municipality (approved)" | — |
| Issued / valid until | M | "Issued 14:05, valid until 20:00 NPT" | — |
| Confidence | M | "Confidence: High (river gauge data)" | — |
| More info | S | Short link / area code | — |
| Disclaimer | M | "Follow instructions of police and local officials." | — |
| Prototype/exercise tag | M (prototype) | "PROTOTYPE" / "EXERCISE" | — |

- **SMS length:** English GSM-7 ≤ 2 × 153 characters; Nepali UCS-2 ≤ 2 × 67 characters (so Nepali SMS use abbreviated templates).
- **Template governance:** linter + approval (FR-65).

## Appendix D — Conflict Resolutions Embedded in Requirements

| Conflict | Resolution | Requirements |
|---|---|---|
| C1 Early warning vs. false alarms | Tiered levels; stronger evidence and human approval for higher levels; confidence shown | FR-11, FR-15, FR-19, FR-20, SR-08 |
| C2 Automation vs. human authorization | Graduated autonomy + timeout escalation + labelled precautionary publication (policy) | FR-19..FR-21, SR-02 |
| C3 Privacy vs. location tracking | Area-based subscription; transient location; consented storage only | FR-34, PRV-01, PRV-02 |
| C4 Accuracy vs. speed | Bounded automated validation; SUSPECT data used with LOW confidence instead of waiting | NFR-PF1, NFR-R1, FR-15 |
| C5 Rich information vs. simple UI | Role-based views; progressive disclosure | IR-UI-01, FR-31, FR-51 |
| C6 Central vs. local authority | Official warnings set a floor; local operators may be more protective within scope | FR-28, SR-07, FR-66 |
| C7 Coverage vs. infrastructure | Channel-agnostic core; SMS; coverage flags; volunteers | FR-35, FR-49, NFR-I3 |
| C8 Frequent notifications vs. fatigue | Notify on change only; hysteresis; limited reminders; CRITICAL unmutable | FR-26, Appendix B |

Full analysis: `docs/06` §2.

## Appendix E — Requirement Quality Checklist (ISO/IEC/IEEE 29148)

For each requirement, the reviewer answers Yes/No:

1. **Necessary:** traces to a stakeholder need or failure scenario.
2. **Unambiguous:** one interpretation; no vague words ("fast", "user-friendly", "nearby") without definition.
3. **Singular:** states one capability.
4. **Verifiable:** has a measurable acceptance criterion and a verification method.
5. **Feasible:** achievable within 4 weeks and the stack, or explicitly deferred.
6. **Consistent:** no conflict with another requirement, or the conflict is resolved (Appendix D).
7. **Implementation-free:** states *what*, not *how* (except declared constraints).
8. **Traceable:** has a unique ID, source and links.
9. **Complete:** covers normal, alternative and failure behaviour where relevant.
10. **Honest:** numeric targets labelled **[T]**; facts labelled **[F]**; no claim of prevention or guaranteed safety.
