# 01 — Project Overview

> Deliverables 1–9: Title, Abstract, Background, Problem Statement, Motivation, Research Questions, Objectives, Scope, Out-of-Scope.
>
> **Labelling convention used in every document in this folder**
>
> | Tag | Meaning |
> |---|---|
> | **[F]** Verified fact | Stated by a cited primary/authoritative source (see `07-pilot-context-nepal-and-adaptive-design.md` §Facts Register). The team must re-check the figure against the source before submission. |
> | **[A]** Project assumption | Believed reasonable but not verified; must be validated during elicitation. |
> | **[D]** Design decision | A choice this project makes; it is a requirement or architecture decision, not a claim about the world. |
> | **[T]** Prototype acceptance target | A numeric target used only to accept/reject the *prototype* in a lab setting. It is **not** a real-world performance guarantee. |

---

## 1. Project Title

**Adaptive Multi-Hazard Early Warning and Evacuation Support System**
Short name: **AMHEWS** · Global by design · **First pilot deployment: Nepal** (prototype codename: *Sajag* — "alert/vigilant" in Nepali) **[D]**

## 2. Abstract

Floods, landslides and earthquakes threaten communities worldwide, and the hardest places to warn are those with steep terrain, seasonal extreme rainfall, uneven communication infrastructure and many languages. AMHEWS is a **country-agnostic** system: everything that differs between places comes from a configurable Deployment Profile. Its **first pilot deployment is Nepal**, which combines all of these difficulties **[F]** and is therefore a demanding testing ground. Software cannot prevent these hazards, but it can help reduce their human impact by shortening the time between a dangerous condition being observable in data and the moment an at-risk person knows what to do.

This project applies a full Requirements Engineering (RE) lifecycle to the design of an *adaptive* early warning and evacuation support system. The first hazard modelled is **riverine flooding**; the architecture is hazard-agnostic so that landslide and earthquake modules can be added later through configuration and plug-in components rather than redesign.

The work produces: a stakeholder analysis covering 24 stakeholder groups; personas; ~50 functional and ~45 non-functional requirements with acceptance criteria; dedicated safety, security and privacy requirements; 13 detailed use cases; a failure-mode analysis of 20 critical scenarios; an explicit analysis of 8+ stakeholder conflicts and their resolution; MoSCoW prioritization; and a bidirectional traceability matrix from stakeholder goal to test.

A semester-scale prototype (Python/FastAPI backend, Supabase/PostgreSQL+PostGIS database, Next.js/React frontend) uses simulated river-gauge and rainfall data plus public APIs to demonstrate threshold-based risk classification, a human-in-the-loop warning workflow, localized multilingual alerts, shelter lookup and hazard-aware evacuation routing, and degraded-mode operation. The system is explicitly positioned as **decision support** for authorities and communities — not as a guaranteed predictor and not as a replacement for official government warning channels.

## 3. Background (pilot context: Nepal)

The product is global; the background below describes the first pilot country.


- Nepal's territory rises from the low-lying Terai plains in the south to the Himalaya in the north over a short north–south distance; major river systems (Koshi, Gandaki/Narayani, Karnali, Mahakali) drain from the mountains into the Terai and on to India **[F]**.
- Most annual rainfall falls during the summer monsoon (roughly June–September) **[F]**, which is when most flood and landslide disasters occur **[F]**.
- Recent major events include the 2008 Koshi embankment breach, the August 2017 Terai floods, the June 2021 Melamchi flood, and the late-September 2024 floods and landslides affecting Kathmandu Valley and other regions **[F]**.
- Nepal already operates institutional early-warning capabilities: the **Department of Hydrology and Meteorology (DHM)** runs hydrological/meteorological stations, flood forecasting and SMS-based flood alerts; the **National Disaster Risk Reduction and Management Authority (NDRRMA)**, created under the *Disaster Risk Reduction and Management Act, 2074 (2017)*, coordinates DRR nationally and operates the **BIPAD** disaster information portal; community-based flood early warning systems (CBEWS) have been run with NGOs on several rivers **[F]**.
- **Implication [D]:** this project must *complement and interoperate with* existing official systems, not compete with them. A warning from this system must never contradict an official DHM/NDRRMA warning (see SR-07, FR-28).

## 4. Problem Statement

People in flood-exposed areas — in the Nepal pilot and in many similar regions worldwide — can receive warnings that are **late, too general, hard to understand, not actionable, or not received at all**, especially where connectivity is weak, literacy or language differs from the warning language, or the person has a disability **[A — to be validated through elicitation; supported qualitatively by post-event reviews]**. Authorities, in turn, must make high-stakes decisions (escalate? evacuate? which shelter? which road?) from fragmented data sources of uneven reliability, under time pressure.

The RE problem is therefore not "predict floods with ML", but:

> *What must a warning and evacuation-support system do, how well, and under which failure conditions, so that diverse stakeholders with conflicting needs receive timely, trustworthy, localized and actionable information — and how can we demonstrate that those requirements are complete, consistent, traceable and validated?*

## 5. Motivation

1. **Human impact** — Warnings that arrive earlier and are understood are widely associated in DRR literature with reduced loss of life (e.g., WMO/UNDRR "Early Warnings for All" initiative frames people-centred end-to-end EWS around four pillars: risk knowledge, monitoring & forecasting, dissemination & communication, preparedness & response) **[F]**. This project's requirements are organized around those four pillars **[D]**.
2. **RE is the hard part** — In safety-critical public-warning systems, failures frequently stem from requirements issues (ambiguous thresholds, unclear authority, untested degraded modes, warnings people don't understand) rather than from code defects **[A — common position in safety/RE literature; cite e.g. Leveson, *Engineering a Safer World*, 2011]**.
3. **Educational value** — The domain naturally forces engagement with conflicts (early vs. accurate), uncertainty, safety, ethics, privacy and change — the core topics of an RE course.

## 6. Research Questions

**Core RQ:** How can an adaptive, globally deployable software-based early warning and evacuation support system reduce the human impact of floods by providing timely, reliable, localized and actionable risk information to communities and emergency authorities — evaluated through a first pilot deployment in Nepal?

| # | Theme | Supporting research question | Answered mainly in |
|---|---|---|---|
| RQ1 | Early detection | Which publicly available or simulatable data signals (river level, rate of rise, upstream rainfall, forecast discharge) give the most useful lead time, and how should their freshness and reliability be specified? | 03, 04 (FR-01..FR-10) |
| RQ2 | Risk assessment | How should risk be specified so that it is explainable, auditable and configurable per area (hazard × exposure × vulnerability), rather than a black box? | 03 §Risk engine, FR-11..FR-17 |
| RQ3 | Warning generation | What rules govern creation, escalation, de-escalation and cancellation of warnings so that warnings are never contradictory or silently dropped? | FR-18..FR-29, SR-* |
| RQ4 | Communication | Which channels and message formats maximize reception and correct comprehension across languages, literacy levels and disabilities? | FR-30..FR-37, NFR-U* |
| RQ5 | Evacuation | How should shelter and route recommendations be constrained so the system never recommends a route or shelter known to be unsafe? | FR-38..FR-46, SR-03..SR-05 |
| RQ6 | Accessibility | What requirements ensure persons with disabilities, elderly, children and low-literacy users can perceive and act on warnings? | NFR-U*, personas |
| RQ7 | Reliability | What availability, freshness and fault-tolerance requirements are proportionate for a semester prototype vs. a production system? | NFR-A*, NFR-R* |
| RQ8 | False alarms | How can the requirement set balance missed-warning risk against warning fatigue, and how is that trade-off made explicit and measurable? | 06 §Conflicts C1, C8 |
| RQ9 | System failures | Which failure modes are credible and what detection/mitigation/recovery requirements do they generate? | 06 §Failure scenarios |
| RQ10 | Conflicting requirements | Which stakeholder conflicts exist and which RE techniques resolve them defensibly? | 06 §Conflicts |
| RQ11 | Limited infrastructure | How should the system degrade gracefully under loss of internet, mobile network or power? | FR-47..FR-50, 03 §Degraded modes |
| RQ12 | Safety-critical | Which requirements are safety requirements, and how are they verified to a higher standard? | 04 §Safety |
| RQ13 | Privacy & security | How can location-based alerting be achieved with minimal personal-data collection and protection against spoofed warnings? | 04 §Security, §Privacy |
| RQ14 | Validation | How can requirements be validated with stakeholders who are hard to reach, and verified in a prototype using simulated scenarios? | 09, 10 |

## 7. Project Objectives (measurable)

Objectives are split into **system objectives** (what the designed system should achieve; targets marked **[T]** apply to the prototype in a simulated test environment only) and **project/RE objectives** (what the team delivers).

### 7.1 System objectives

| ID | Objective | Measure (prototype) |
|---|---|---|
| SO-1 | Detect potential flood risk as early as available data allows | Risk level change computed within **≤ 60 s [T]** of a qualifying observation being ingested |
| SO-2 | Estimate risk for specific geographic areas | Risk computed per configured **Area Unit** (ward or river reach); 100 % of configured units have a current level or an explicit `UNKNOWN/STALE` state |
| SO-3 | Classify risk into 4 levels: **Normal / Watch / Warning / Critical-Evacuate** (+ explicit `Unknown`) | 100 % of scripted scenarios produce the level defined by the scenario oracle |
| SO-4 | Localized alerts | 0 alerts delivered to subscribers outside the targeted area polygon(s) in test runs **[T]** |
| SO-5 | Clear action instructions | Every Warning/Critical message contains: hazard, area, level, action, time issued, issuer, valid-until; comprehension ≥ 80 % in a usability test **[T]** |
| SO-6 | Recommend nearby shelters | Top-3 open shelters with capacity returned in ≤ 3 s **[T]** |
| SO-7 | Recommend safer routes | 0 recommended routes intersect an active hazard polygon or closed segment in the test suite **[T]** |
| SO-8 | Account for closures, bridges, water levels | Route engine consumes closure + hazard layers; updated route within ≤ 60 s of a closure being recorded **[T]** |
| SO-9 | Support multiple stakeholders | Role-specific views for ≥ 4 roles (citizen, local authority, district/national operator, admin) |
| SO-10 | Any language via language packs (pilot: Nepali + English) | 100 % of citizen-facing strings and templates available in every configured language; English fallback |
| SO-17 | Global by design | All country-specific values come from a Deployment Profile (FR-68); a second test profile works without code change |
| SO-11 | Accessibility & low literacy | WCAG 2.2 AA on citizen pages (automated + manual check); icon+colour+text+audio redundancy for levels |
| SO-12 | Unreliable connectivity | Citizen app shows last-known risk, shelters and instructions offline (PWA cache); SMS fallback path demonstrated (simulated gateway) |
| SO-13 | Minimize false alarms, prioritize safety | False-negative rate **= 0** on the scripted safety-critical scenarios; false-positive rate reported and reviewed (no hard target, see Conflict C1) |
| SO-14 | Authority dashboards | Map + area list + pending approvals + delivery stats + shelter occupancy on one dashboard |
| SO-15 | Logs for post-event analysis | 100 % of warning lifecycle events and risk-level changes in an append-only, tamper-evident audit log |
| SO-16 | Extensible to more hazards | Adding a hazard type requires: a hazard config record + a risk-rule plug-in; **no schema migration of core tables** (demonstrated with a stub "landslide" hazard) |

### 7.2 Project / RE objectives

| ID | Objective | Measure |
|---|---|---|
| PO-1 | Complete stakeholder analysis | 24 stakeholder groups analysed on 6 dimensions |
| PO-2 | Specified requirements | Every FR/NFR has ID, statement, source stakeholder, priority, rationale, acceptance criterion |
| PO-3 | Traceability | 100 % of *Must* requirements traced forward to design + test and backward to a stakeholder goal |
| PO-4 | Validation | ≥ 1 review with a domain proxy (DRR lecturer/NGO/municipal officer if reachable) + ≥ 5 citizen usability sessions |
| PO-5 | Quality of spec | Requirements review checklist (IEEE 29148 attributes) passed; ambiguity log closed |

## 8. Scope (Prototype)

**In scope [D]:**

1. **Hazard:** riverine flood (one pilot river basin — recommended: a simulated reach modelled on a Terai river such as the West Rapti or Karnali at Chisapani, using *simulated* gauge data shaped on public historical patterns).
2. **Data:** simulated river-level and rainfall streams (scenario player); public weather forecast API (e.g. Open-Meteo); optional public flood forecast (GloFAS via Open-Meteo Flood API); OpenStreetMap roads; public admin boundaries (e.g. HDX/Survey Department datasets); seeded shelter list.
3. **Risk engine:** transparent, rule/threshold-based classification with configurable thresholds per gauge and per area, rate-of-rise rule, data-quality gating, and confidence flag.
4. **Warning workflow:** auto-proposal → human approval (two-person rule for Critical) → dissemination → acknowledgement → update/escalation → cancellation; contradiction prevention.
5. **Notification:** web push, in-app, email (dev), **simulated SMS gateway** and simulated siren/loudspeaker endpoint; message templates in every configured language (pilot: Nepali and English) with icons.
6. **Evacuation:** shelter lookup by distance/capacity/accessibility; hazard-aware routing on an OSM road graph with closures and flooded segments removed; alternative route.
7. **Citizen PWA:** risk map, current level, instructions, shelters, route, report conditions (with photo optional), offline cache, accessibility features.
8. **Authority dashboard:** monitoring map, approvals queue, manual alert, shelter management, incident/report triage, delivery stats.
9. **Admin:** region/area configuration, thresholds, templates, users/roles, data-source registry.
10. **Audit/event log** and **degraded-mode** behaviour.
11. **Multi-hazard extensibility:** a stub landslide hazard config to prove the extension point.

## 9. Out of Scope

| Item | Why out of scope |
|---|---|
| Physical sensors, sirens, gauges | Course timeframe/cost; simulated endpoints instead |
| Control of dams, gates, embankments or any physical infrastructure | Safety and authority — not a software team's mandate |
| Replacing DHM/NDRRMA/local government as the warning authority | Legal mandate sits with government (DRRM Act 2074) **[F]**; system is decision support |
| Guaranteeing flood prediction or human safety | Scientifically and ethically impossible to guarantee |
| Hydrodynamic/hydrological modelling or ML forecasting as a core deliverable | Not an RE objective; optional "Could" stretch (FR-17) with strict guardrails |
| Real telecom integration (real SMS, Cell Broadcast) | Requires operator agreements; simulated gateway with production interface spec instead |
| Production-grade national deployment, 24/7 operations, SLA | Beyond a university project |
| Real personal data of citizens | Synthetic users only in prototype |
| Earthquake early warning (seconds-scale seismic detection) | Different physics and latency class; only listed as future extension |
| Native Android/iOS apps | PWA covers the prototype need |
