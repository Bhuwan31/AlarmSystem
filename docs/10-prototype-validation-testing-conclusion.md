# 10 — Prototype Plan, Validation, Testing, Evaluation, Future Work, Limitations, Conclusion
> **Update:** the project now has **4 weeks**. The priorities and schedule in [REQUIREMENTS_ENGINEERING.md §13](../REQUIREMENTS_ENGINEERING.md) replaces the ones in this file where they differ.


> Deliverables 28–33 and section 19 (Evaluation). All numeric targets are **[T] prototype acceptance targets** in a simulated environment, not real-world guarantees.

## 1. Prototype Plan (one semester ≈ 14 weeks, team of 4–6 [A])

| Sprint (2 wk) | RE focus | Build focus (Supabase · FastAPI · Next.js) | Exit criteria |
|---|---|---|---|
| **S0** (wk 1–2) | Elicitation plan, ethics approval, stakeholder map, initial goals | Repo, CI, Supabase project, PostGIS, auth; Next.js skeleton with i18n (ne/en) | Baseline v0.1 of requirements; hello-world deployed |
| **S1** (wk 3–4) | Interviews/questionnaire; personas; use cases draft | Schema migrations; seed pilot region (wards, 3–5 simulated stations, shelters, OSM roads); scenario player; validation | FR-01/03/05/06 pass |
| **S2** (wk 5–6) | Requirements spec v0.5; conflict workshop; MoSCoW | Risk engine (R1–R10), staleness, confidence, risk map + citizen area view | ST-01..05 pass; FR-11..15 |
| **S3** (wk 7–8) | **Validation round 1** (paper/Figma + working map with proxies) | Warning state machine, approvals, contradiction guard, templates; dashboard approval queue | SR-02, SR-07, SR-09 tests pass |
| **S4** (wk 9–10) | Failure-scenario walkthroughs; safety review | Dispatcher (web push, SMS sim, email), delivery stats; shelters & safe routing (OSMnx/NetworkX) | SR-01, SR-03, SR-05; LT-01 |
| **S5** (wk 11–12) | **Validation round 2** — usability tests (≥ 5 citizens incl. low-literacy/elderly proxies; ≥ 2 operator proxies) | PWA offline, reports, status page, audit hash chain, admin config, Should items | UX-01..05; FR-47/48/59/63 |
| **S6** (wk 13–14) | RTM coverage, final evaluation, report | Hardening, landslide stub, CAP export, demo scenarios, static fallback | All Must reqs verified; report & demo |

**Demo script (final presentation):** play *Scenario "Monsoon night"*: rainfall rises → upstream gauge WARNING → downstream ward WATCH (auto) → WARNING proposal → approval → citizens receive ne/en alerts → gauge goes silent (level held, LOW confidence) → volunteer report conflicts → escalation to CRITICAL needs 2 approvers; one unavailable → timeout escalation → route requested; bridge closure added → re-route → shelter becomes full → alternative → water recedes → hysteresis → all-clear. Then show audit timeline and metrics.

**Team roles [A]:** RE lead / PM; backend (data + risk); backend (warnings + notifications); frontend citizen PWA + accessibility; frontend dashboard/admin + maps; QA/safety reviewer (rotating).

## 2. Scenario Catalogue (test oracles)

| ID | Scenario | Expected (oracle) |
|---|---|---|
| ST-01 | Normal monsoon day | All NORMAL; no proposals |
| ST-02 | Gradual rise to WARNING | WATCH → WARNING proposal ≤ 60 s after threshold |
| ST-03 | Flash rise (rate-of-rise) | Level jumps +1 via R4 before absolute threshold |
| ST-04 | Gauge outage at WARNING | Level held, LOW confidence, stale alert |
| ST-05 | Oscillation around threshold | ≤ 1 change per hold window |
| ST-06 | CRITICAL, approver absent | Escalation at timeout; precautionary publish if policy on |
| ST-07 | Conflict: gauge normal, verified reports of overtopping | Conflict event; conservative level; operator prompt |
| ST-08 | Push channel failure | SMS fallback; failures visible |
| ST-09 | Shelter inside new hazard zone | Shelter excluded |
| ST-10 | All routes cut | "No safe route" + fallback advice |
| ST-11 | Configure 2nd municipality | Works without code change |
| ST-12 | Spoofed warning attempt (no auth / wrong scope / single approver for CRITICAL) | All rejected; anomaly logged |
| ST-13 | Exercise mode drill | All messages prefixed EXERCISE |
| ST-14 | Erroneous warning cancelled | Correction to 100 % original recipients |

## 3. Validation Strategy ("Are we building the right system?")

| Method | With whom | What is validated | Evidence |
|---|---|---|---|
| Requirements review/walkthrough | DRR lecturer, NGO/municipal proxy, peers | Correctness, completeness, feasibility, domain fit of FR/NFR/SR | Review minutes, defects found |
| Inspection checklist (IEEE 29148) | Team + peer team | Each requirement: unambiguous, verifiable, singular, consistent, traceable | Checklist results, ambiguity log |
| Scenario walkthroughs | Domain proxies | Failure handling and conflict resolutions are acceptable | Signed-off scenario cards |
| Prototyping (paper → Figma → PWA) | Residents/proxies, operators | Message comprehension, level understanding, workflow fit | Usability findings, change requests |
| Level comprehension test | ≥ 10 participants **[T]** | Users choose correct action for each level from message card | % correct per level |
| Goal coverage analysis | Team | Every goal G1–G8 realised; every obstacle mitigated or explicitly assigned to non-software agent | Goal/obstacle table |

## 4. Testing Strategy ("Are we building the system right?")

| Level | Scope | Tools | Focus |
|---|---|---|---|
| Unit | Validation rules, risk rules, hysteresis, state machine, contradiction guard, template linter, routing filter, hash chain | pytest, hypothesis (property-based), coverage | NFR-M3 ≥ 85 % on safety modules **[T]** |
| Integration | API ↔ Supabase (RLS!), adapters with recorded responses, dispatcher idempotency | pytest + local Supabase (CLI/Docker), respx | Auth/scope negative tests |
| Scenario / system | ST-01..ST-14 end-to-end with scenario player | pytest orchestrator; Playwright for UI assertions | Oracle match; latencies |
| Fault injection | Kill adapters, DB unavailability, dispatcher crash, stale sources | Toxiproxy or mocks; process kill | NFR-R*, SR-01, SR-06 |
| Performance/load | 50 concurrent users; 1,000-recipient fan-out | k6 or Locust | NFR-PF1..3 |
| Security | AuthZ bypass, forged JWT, rate limits, XSS, secrets | OWASP ZAP baseline, gitleaks, pip-audit/npm audit, manual ASVS subset | NFR-S* |
| Accessibility | Citizen pages | axe-core (Playwright), Lighthouse, manual screen reader (NVDA/TalkBack) | NFR-U2 |
| Usability | Tasks UC-01..05 (citizens), UC-06..08 (operators) | Think-aloud, SUS questionnaire | NFR-U1; SUS ≥ 68 **[T]** (68 is the commonly cited SUS average) |
| Localization | ne/en strings, Devanagari rendering, SMS lengths | Snapshot tests, native reviewers | NFR-U4, FR-35 |
| Regression | Every PR | GitHub Actions; requirement-tagged tests; RTM coverage report | No orphan Must reqs |

## 5. Evaluation Criteria

| Criterion | Metric (definition) | Prototype target **[T]** / justification |
|---|---|---|
| Warning generation latency | Time from valid observation stored → PROPOSED (p95) | ≤ 60 s — small relative to multi-hour lead times on large rivers **[A]**; easily measured |
| Notification dispatch time | ACTIVE → all messages handed to channel (1,000 recipients) | ≤ 60 s; *handset delivery* reported but not targeted (external networks) |
| Risk classification accuracy | % of (area, time step) matching scenario oracle | 100 % on scripted scenarios — rules are deterministic, so any mismatch is a defect. **No claim about real-world hydrological accuracy.** |
| False-negative rate | Scenario events with no WARNING+ before oracle peak | 0 on safety scenarios |
| False-positive rate | WARNING+ issued where oracle says none | Reported per scenario set; reviewed, not hard-capped (Conflict C1) |
| Lead time | First WATCH/WARNING time before simulated peak | Reported; compare rule sets via replay |
| Route recommendation validity | % routes not intersecting excluded geometry | 100 % (SR-03), property test over ≥ 1,000 random origins |
| Shelter recommendation validity | % results open, with capacity, outside hazard zones | 100 % |
| System availability | Uptime of public endpoints over 72 h test | ≥ 99 % (free-tier realistic) |
| Data processing reliability | % injected faults correctly flagged; % valid readings stored | 100 % of injected fault types flagged; ≥ 99 % stored |
| Delivery reliability | % recipients with final delivery state; duplicates | 100 % final state; 0 duplicates |
| Usability | SUS score; task success; time-to-correct-action | SUS ≥ 68; ≥ 80 % task success |
| Accessibility | axe critical violations; manual screen-reader task success | 0 critical; all core tasks completable |
| Level comprehension | % correct action per level | ≥ 80 % |
| Requirements completeness | % goals with realising reqs; % obstacles mitigated/assigned; TBDs remaining | 100 %; 100 %; 0 TBD in Must |
| Requirements consistency | Conflicts open in conflict matrix; contradictory pairs | 0 unresolved |
| Requirements traceability | % Must reqs traced backward (stakeholder/goal) and forward (component/test) | 100 % |
| Requirements quality | % reqs passing 29148 checklist | ≥ 95 % first pass, 100 % at baseline v1.0 |
| Change stability | # change requests per sprint; % touching SRs | Reported (indicator of volatility) |

## 6. Future Extensions
1. **Landslide module** (rainfall intensity–duration thresholds, slope/susceptibility layers) using the existing `HazardModel` interface; landslide closures feed flood routing.
2. **Glacial lake outburst flood (GLOF)** monitoring integration where official sensors exist.
3. **Earthquake** — not early warning in prototype; post-event shelter/route/coordination support and, if national EEW exists, CAP ingestion.
4. **Real channels:** SMS aggregator, **cell broadcast** with telecom operators, IVR voice calls in local languages, community radio, siren controllers.
5. **Official integrations:** DHM real-time feeds, BIPAD/NEOC CAP exchange, road authority closure feeds.
6. **More languages** (Maithili, Bhojpuri, Tharu, Tamang, Newar…) with community translation workflow.
7. **Advisory ML/hydrological forecasting** with calibration and rigorous evaluation; still bounded by SR-11.
8. **Household preparedness plans**, drill scheduling, school safety module.
9. **Offline mesh / Bluetooth relay** and USSD interface for feature phones.
10. **Multi-country deployment** using the configuration model (doc 07).

## 7. Limitations
- **Simulated data:** risk logic validated against *scripted* scenarios, not real hydrological events; scenario oracles encode the team's assumptions.
- **Thresholds** in the prototype are illustrative; real ones must come from DHM/authorities.
- **No real dissemination:** SMS/siren are simulated; real-world delivery rates, network congestion and handset behaviour are untested.
- **Limited stakeholder access:** many requirements are validated with proxies; persona and assumption tags must be revisited with real stakeholders.
- **OSM data quality** may limit routing validity in rural areas.
- **Behavioural response** (whether people act on warnings) is outside what a prototype can evaluate.
- **Scale:** architecture supports a pilot, not national load without the changes listed in doc 03 §9.
- **Legal/institutional integration** (who may legally issue which warning through this system) requires government decision.
- **No guarantee:** the system cannot guarantee prediction accuracy or safety.

## 8. Conclusion
The project reframes flood early warning in Nepal as a **requirements problem under uncertainty** rather than a prediction problem. By grounding the system in a stakeholder and goal analysis, treating failure scenarios as first-class sources of requirements, making stakeholder conflicts explicit and resolving them through graduated autonomy, nested authority, tiered warning levels and privacy-by-design, and separating non-negotiable safety invariants from configurable context, the design answers the core research question in a testable way: *timely, reliable, localized and actionable* information is achieved through quantified latency targets, data-quality gating that never mistakes silence for safety, area-level targeting, multilingual action-first messages, human-authorized warnings and hazard-aware evacuation guidance — all traceable from stakeholder to test.

The semester prototype (Supabase + FastAPI + Next.js) demonstrates these requirements end-to-end with simulated data. Its value is not to replace DHM, NDRRMA or local authorities, but to show how a rigorously engineered decision-support system could complement them and reduce the human impact of floods — while honestly stating what software cannot do.
