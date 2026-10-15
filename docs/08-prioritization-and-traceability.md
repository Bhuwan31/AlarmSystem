# 08 — Requirements Prioritization and Traceability
> **Update:** the project now has **4 weeks**. The priorities and schedule in [REQUIREMENTS_ENGINEERING.md §13](../REQUIREMENTS_ENGINEERING.md) replaces the ones in this file where they differ.


> Deliverables 24–25.

## 1. Prioritization Method

**MoSCoW**, applied *after* a lightweight scoring so the decisions are defensible:

| Criterion | Weight | Scale |
|---|---|---|
| Safety contribution (prevents a Sev-4 failure in doc 06) | 0.35 | 0–3 |
| Core to research question / demo of RE concepts | 0.25 | 0–3 |
| Stakeholder value (number & vulnerability of stakeholders served) | 0.20 | 0–3 |
| Feasibility in semester (inverse of effort/risk) | 0.20 | 0–3 |

Rule of thumb: score ≥ 2.2 → Must; 1.6–2.2 → Should; 1.0–1.6 → Could; external-dependency or out-of-scope → Won't. **Override rule:** any requirement realising a Safety Requirement (SR-*) is Must regardless of effort. *Must* items are capped at ~60 % of estimated effort so the prototype is deliverable (DSDM guidance).

## 2. Classification and Reasoning

### Must Have (prototype fails without them)
| Group | IDs | Reasoning |
|---|---|---|
| Data ingest, validation, staleness, scenario player, provenance | FR-01..03, 05..08, 10 | No trustworthy risk without valid data; scenario player is the only data source & the test oracle |
| Risk computation, map, explainability, confidence | FR-11..15 | Core research question; explainability is an RE/safety theme |
| Warning lifecycle: propose, approve (1/2 persons), timeout, edit, escalate, cancel+correction, hysteresis, contradiction guard, templates | FR-18, 20..23, 25, 26, 28, 29 | Demonstrates safety, conflict resolution (C1, C2, C6, C8) |
| Citizen receive/view/instructions/SMS/report | FR-30, 31, 33, 35, 37 | End-to-end value to at-risk people |
| Shelters & safe routing incl. closures and no-safe-route | FR-38, 40..44 | Evacuation support is in prototype scope; SR-03/05 |
| Offline cache, status page | FR-47, 48 | Degraded operation is a key objective |
| Dashboard monitor, list, manual alert, shelter update, report triage, delivery stats | FR-51..53, 55..57 | Authority stakeholder needs |
| Audit log | FR-59 | Accountability/SO-15 |
| Admin config (regions, thresholds w/ 2-person, templates, users, policies) | FR-63..68 | Adaptive design is in title |
| All SR-01..SR-12; core NFRs (PF1–3, R1–4, U1–4, SC1–3, M2–4, I2–3, I5, S1–6, S9, PR1–4, PR6–7) | — | Safety, security, privacy baselines |

### Should Have (important; included if time allows, planned for sprint 5–6)
FR-09 (conflict detection), FR-16 (vulnerability ranking), FR-19 (auto-publish WATCH), FR-24 (ack), FR-27 (expiry reminders), FR-32 (proxy subscription), FR-34 (location/QR), FR-36 (assistance), FR-39 (filters), FR-45 (re-route push), FR-46 (route warnings), FR-49 (SMS fallback), FR-50 (static fallback), FR-54 (evacuation progress), FR-58 (CAP), FR-60 (timeline), FR-62 (metrics); NFR-PF4–5, A1, A2, A4, R5, U5–6, M1, I1, I4, S7–8, PR5, PR8.
*Reasoning:* high value, but the system is still demonstrably safe without them, or they depend on Must features being finished first.

### Could Have
FR-04 (GloFAS), FR-17 (advisory ML), FR-61 (what-if replay), NFR-A3 (multi-instance), NFR-SC4 (1 M subscriber design note).
*Reasoning:* nice demonstrations of extensibility; low safety contribution or high effort.

### Won't Have (this prototype)
| Item | Reasoning |
|---|---|
| Real SMS/cell broadcast/IVR integration | Requires operator/regulator agreements and cost; interface is specified (NFR-I3) |
| Real DHM/BIPAD live integration | Access not guaranteed; adapters specified (NFR-I4) |
| Physical sensors/sirens | Out of scope |
| Native mobile apps | PWA sufficient |
| Full landslide/earthquake models | Only a stub to prove extensibility |
| Additional languages beyond ne/en | Architecture supports; translation quality needs native reviewers |
| Production 24/7 operations, HA SLA | Out of scope |

## 3. Requirements Traceability Matrix (critical requirements)

Stakeholder → Goal → Requirement → Use Case → Design Component (doc 03 §3 numbering) → Test/Validation.
Test IDs: **UT** unit, **IT** integration, **ST** scenario (scripted flood), **UX** usability, **SEC** security, **REV** review/inspection, **LT** load.

| Stakeholder | Goal | Requirement | Use case | Component | Test / Validation |
|---|---|---|---|---|---|
| S19 DHM, S21 Admin | G1.1 | FR-01 ingest levels | UC-10 | 1 Adapters | IT-01 ingest rate; ST-all |
| S22 Devs | G1.1 | FR-05 scenario player | UC-10 | 1 Adapters | UT-05 timeline replay |
| S19, S21 | G1.2 | FR-06 validation | UC-09 | 2 Processing | UT-06a..e range/unit |
| S21, S8 | G1.2 | FR-07 staleness | UC-11 | 2, 13 | ST-04 gauge outage |
| S19 | G1.2 | FR-08 anomaly flags | UC-09 | 2 | UT-08 spike/flatline |
| S19, S24 | G1.2 | FR-09 conflict | UC-12 | 2, 3 | ST-07 conflict scenario |
| S8, S9 | G2 | FR-11 compute level | UC-10 | 3, 4 | ST-01..ST-10 oracle match |
| S2 | G2 | FR-12 ≤ 60 s recompute | UC-10 | 3 | LT-01 latency |
| S10 | G2 | FR-14 evidence | UC-02, UC-06 | 3, 11 | IT-14 reproducibility |
| S8 | G2 | FR-15 confidence | UC-11 | 3 | ST-04 |
| S8 | G3 | FR-18 proposal | UC-10 | 5 | ST-02 |
| S8–S10 | G3.2 | FR-20 / SR-02 approvals | UC-07 | 5, 12 (RBAC), DB RLS | UT-20 state machine; SEC-03 forged role |
| S2, S9 | G3.2 | FR-21 timeout escalation | UC-07 E2 | 5 | ST-06 approver absent |
| S1 | G3.1 | FR-25 / SR-09 cancel + correction | UC-07 A3 | 5, 10 | IT-25 count equality |
| S1, S8 | G3 | FR-26 hysteresis | UC-10 A2 | 3 | ST-05 oscillation |
| S10, S19 | G3.1 | FR-28 / SR-07 no contradiction | UC-07 E1 | 5 + DB index | UT-28; IT-28 DB constraint |
| S1, S6, S7 | G3.3 | FR-29 complete templates | UC-01 | 5, 12 | UT-29 linter; REV-02 language review |
| S1–S7 | G3 | FR-30 localized delivery | UC-01 | 10 | IT-30 1,000 subs in/out area |
| S1 | G3, G7 | SR-01 no silent drop | UC-01 E2 | 10, 9 | ST-08 channel failure |
| S2, S4 | G3, G6 | FR-35 SMS | UC-01 A1 | 10 | UT-35 segment length ne/en |
| S1, S24 | G1 | FR-37 reports offline | UC-05 | 8, 9 | IT-37 offline queue |
| S1 | G4.1 | FR-38 / SR-05 shelters | UC-04 | 7 | UT-38 ranking; ST-09 shelter in zone |
| S1, S20 | G4.2 | FR-42 / SR-03 safe routing | UC-03 | 6 | Property test PT-42 (random origins, 0 intersections) |
| S20, S11 | G4.2 | FR-43 closures | UC-03, UC-06 | 6, 9 | IT-43 |
| S1 | G4.2 | FR-44 alternative / no route | UC-03 E1 | 6 | ST-10 isolated area |
| S2 | G6 | FR-47 offline cache | UC-02 E1 | 8 | IT-47 DevTools offline; UX-05 |
| S21 | G6 | FR-48 status page | UC-11 | 13 | ST-04 |
| S8, S9 | G5 | FR-51 dashboard | UC-06 | 9 | IT-51 realtime ≤ 5 s; UX-03 operators |
| S8 | G5 | FR-53 manual alert + preview | UC-07 | 9, 5 | IT-53 preview = deliveries |
| S8, S17 | G5 | FR-55 shelter update | UC-08 | 7, 9 | IT-55 |
| S8, S10 | G5, G7 | FR-57 delivery stats | UC-06 | 10, 9 | IT-57 |
| S10, S21 | G7 | FR-59 audit hash chain | all | 11 | UT-59 tamper detection |
| S21 | G8 | FR-63 configure region | UC-13 | 12 | ST-11 add 2nd municipality |
| S19, S21 | G8 | FR-64 threshold 2-person | UC-13 | 12 | UT-64 |
| S21 | G7 | NFR-S1 MFA | UC-06, UC-07 | Auth | SEC-01 |
| S21 | G7 | NFR-S2 RLS + API authz | all ops | DB, API | SEC-02 scoped access |
| S1 | G7 | NFR-PR2 location not stored | UC-02, UC-03 | 8, API | REV-04 DB inspection |
| S6 | G3.3 | NFR-U2 WCAG 2.2 AA | UC-01..05 | 8 | UX-02 axe + screen reader |
| S1 | G3.3 | NFR-U1 one action / comprehension | UC-01, UC-02 | 8 | UX-01 comprehension ≥ 80 % [T] |
| S1–S24 | G2 | SR-06 data loss ≠ downgrade | UC-11 | 3 | ST-04 |
| S22 | G8 | NFR-SC2 hazard plug-in | — | 3 (HazardModel) | IT-SC2 landslide stub without core migration |
| S8 | G7 | SR-12 exercise mode | UC-07 E4 | 5, 10 | UT-SR12 prefix enforced |

**Coverage rules (checked by script on the requirements spreadsheet/YAML):** every Must FR has ≥ 1 use case or system process, ≥ 1 component, ≥ 1 test; every SR has ≥ 1 ST test and ≥ 1 UT/PT; every test references ≥ 1 requirement (no orphan tests); every stakeholder goal G1–G8 has ≥ 1 Must requirement.

**Recommended tooling [D]:** keep requirements as YAML in `docs/requirements/*.yaml` (id, text, priority, source, rationale, acceptance, traces) and generate this matrix + coverage report with a small Python script in CI; test functions are tagged with requirement IDs (`@pytest.mark.req("FR-42")`) so the backward trace is automatic.
