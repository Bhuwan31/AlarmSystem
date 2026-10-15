# 06 — Failure Scenarios, Conflicting Requirements, Risk Analysis

> Deliverables 22, 23, 26. Severity and probability are **qualitative project estimates [A]** to be reviewed with domain experts — not measured statistics.
>
> **Severity:** 4 Catastrophic (likely loss of life) · 3 Critical (serious injury/large-scale harm or loss of trust) · 2 Major (degraded service, recoverable) · 1 Minor.
> **Probability (during a monsoon season, real deployment):** H High · M Medium · L Low.
> **Risk class** = Severity × Probability → **Intolerable / Undesirable / Tolerable with mitigation (ALARP) / Acceptable**.

## 1. Failure Scenario Analysis (FMEA-style)

| # | Scenario | Cause | Impact | Sev | Prob | Detection | Mitigation (prevent/reduce) | Recovery | Responsible | Related req. |
|---|---|---|---|---|---|---|---|---|---|---|
| F1 | Internet connection fails (user side or operator side) | Fibre/backbone cuts, landslides on cable routes, power loss to ISP | Citizens can't load app; operators can't reach dashboard | 3 | H | Client offline events; dashboard heartbeat; uptime monitor | PWA offline cache; SMS channel; dashboard usable over mobile data; static CDN fallback | Auto-sync on reconnect; operators follow manual SOP (phone/radio) meanwhile | Sys admin, Local gov | FR-47, FR-49, FR-50 |
| F2 | Mobile network fails | Tower damage/power, congestion | Push & SMS not delivered | 4 | M | Delivery failures spike per area | Multi-channel: sirens/loudspeakers (simulated), volunteers door-to-door, community radio; early WATCH to give time before networks fail | Re-send queued messages when network recovers; operator sees undelivered areas | Telecom, Local gov, Volunteers | FR-57, SR-01, FR-19 |
| F3 | Electricity fails | Grid outage | Phones die; local servers/routers fail; operators offline | 3 | H | Device battery; ops heartbeat | Cloud hosting (no on-prem dependency); low-power PWA; advice to keep phones charged on WATCH; operator power banks/UPS (SOP) | Cloud continues; operators reconnect | Local gov, Sys admin | NFR-A2, FR-33 |
| F4 | Weather API unavailable | Provider outage, rate-limit, API change | Loss of rainfall/forecast input → reduced lead time | 2 | M | Adapter errors; staleness | Circuit breaker; cached last forecast with age; second provider optional; never downgrade | Auto-resume; backfill | Sys admin, Developers | FR-07, NFR-R2, SR-06 |
| F5 | River-level data unavailable | Gauge/telemetry failure, flood damage to gauge (common at peak) | Primary signal lost exactly when needed | 4 | M | Staleness detection | Hold last level (SR-06), LOW confidence, upstream & rainfall fallback, request volunteer manual readings | Close quality event; recompute | DHM, Volunteers, Sys admin | FR-07, FR-09, UC-11 |
| F6 | Source provides incorrect data | Sensor drift, calibration, wrong unit, debris | False alarm or missed flood | 4 | M | Range/spike/flatline checks; cross-source comparison | Validation (FR-06/08); confidence; human approval for WARNING+ | Mark source SUSPECT; operator overrides; recalibration | DHM, Data providers | FR-06, FR-08, NFR-R1 |
| F7 | Conflicting sources | Different locations/time, faulty sensor, false reports | Confusion, wrong level | 3 | M | Conflict detection | Conservative rule + LOW confidence + operator resolution; official warning precedence | Resolution recorded | Operators | FR-09, UC-12, SR-07 |
| F8 | False positive (predicts flood that doesn't occur) | Conservative thresholds, bad data, local hydraulics | Unnecessary evacuation, cost, fatigue, trust loss | 2–3 | H | Post-event metrics | Tiered levels (WATCH vs. WARNING), human approval, hysteresis, confidence display, threshold tuning via replay | All-clear message; post-event review | Operators, DHM | FR-26, FR-61, FR-62, SR-08 |
| F9 | False negative (fails to detect flood) | No gauge on that tributary, flash flood/GLOF/landslide-dam outburst faster than data, bad thresholds | Casualties | 4 | M | Citizen reports; post-event metrics | Upstream/rainfall rules; citizen/volunteer reports; manual warnings (FR-53); explicit "no monitoring" areas shown; message that absence of warning ≠ safety | After-action review; threshold changes via change management | DHM, Operators, Developers | FR-09, FR-37, FR-53, SR-10 |
| F10 | Warning delayed | Approver unavailable, queue backlog, slow job | Less time to evacuate | 4 | M | Latency metrics; approval timer | Auto-publish WATCH; Critical timeout escalation (FR-21); priority queue; latency SLO alerts | Escalate; post-event review | Operators, Sys admin | FR-21, NFR-PF1, NFR-PF2 |
| F11 | Warning not delivered | Channel failure, invalid push endpoint, SMS gateway down, phone off | People unaware | 4 | M | Delivery records; failure stats | Multi-channel fallback; retries; operator visibility of undelivered areas → door-to-door/siren | Re-send; manual dissemination | Sys admin, Telecom, Volunteers | SR-01, FR-49, FR-57 |
| F12 | Evacuation route blocked | Flooding, landslide, collapsed bridge, traffic | People trapped en route | 4 | M | Closures entered; citizen reports | Hazard-aware routing; alternative route; route warnings; re-route push; "no safe route" fallback | Re-route | Road auth, Police, Operators | FR-42..FR-45, SR-03, SR-04 |
| F13 | Shelter unavailable | Full, flooded, closed, not opened | People sent to unusable place | 3 | M | Shelter updates; reports | Real-time status; exclude in hazard zones; show staleness of occupancy | Notify users routed there; alternative | Local gov, NGOs | FR-55, SR-05 |
| F14 | GPS inaccurate | Indoor, canyon terrain, low-end devices | Wrong area/route | 3 | M | Reported accuracy radius | Ask user to confirm on map if accuracy > 100 m; area chosen explicitly for subscriptions | User corrects position | Developers | UC-03 E2, FR-34 |
| F15 | Server crash during emergency | Load spike, bug, provider outage | No new warnings, dashboards down | 4 | L–M | Uptime monitor, health checks | ≥ 2 instances; load tests; maintenance freeze; static fallback; at-least-once dispatcher | Auto-restart, recompute in ≤ 2 min; manual SOP | Sys admin | NFR-A1..A4, NFR-R3, NFR-R4 |
| F16 | Cyberattack creates false warning | Credential theft, API abuse, insider | Panic, harmful evacuation, loss of trust | 4 | L | Anomaly detection, audit | MFA, RBAC+RLS, two-person rule for CRITICAL, rate limits, no unauthenticated write, signed messages | Immediate cancel + correction; revoke credentials; incident response | Sys admin, NDRRMA | NFR-S1..S6, SR-02 |
| F17 | Admin/operator issues incorrect warning by mistake | Wrong area, wrong level, wrong template, drill sent live | Confusion, unnecessary evacuation | 3 | M | Recipient preview, second approver, citizen feedback | Preview; two-person CRITICAL; contradiction guard; exercise-mode enforcement | Cancel with correction to same recipients | Operators | FR-25, FR-53, SR-09, SR-12 |
| F18 | Users misunderstand levels | Jargon, colour-only cues, language | Wrong action (too little or too much) | 3 | H | Usability tests; ack "need help" patterns | Action-first messages; icons; consistent 4 levels; drills/education; local languages | Clarifying follow-up message | Developers, Local gov, NGOs | FR-29, FR-33, NFR-U1..U5 |
| F19 | Warning fatigue from false alarms | Too many alerts / too sensitive | People ignore real warning | 4 | M | False-alarm rate; ack rate decline | Hysteresis; WATCH not pushed loudly (in-app/opt-in); max reminders; post-event threshold tuning; transparent reasons | Public communication after false alarm | Operators, DHM | FR-26, FR-62, Conflict C1/C8 |
| F20 | No communication in remote mountain areas | No coverage, terrain | Community never gets digital warning | 4 | H | Coverage map per area | Mark areas "digital coverage limited"; integrate community-based EWS (volunteers, sirens, radio); earlier lead time to reach intermediaries | Post-event follow-up | Local gov, Volunteers, NGOs | FR-16, FR-63 (coverage attribute), NFR-I3 |

### 1.1 Risk matrix (before → after mitigation) [A]

```
 Probability →        L                   M                         H
 Severity 4   F16→Tol     F2,F5,F6,F9,F10,F11,F12,F15,F19     F20
              (Undes.)    (Intolerable → ALARP)               (Intolerable → ALARP; residual remains high)
 Severity 3               F7,F13,F14,F17                      F1,F3,F18
                          (Undesirable → Tolerable)           (Undesirable → ALARP)
 Severity 2               F4                                  F8
```

**Residual risk statement:** F9 (missed flash floods) and F20 (no coverage) cannot be reduced to "acceptable" by software alone. The requirements therefore explicitly *communicate* this limitation (SR-10, coverage flags) and depend on non-software measures (community EWS, sirens, radio). This is a key RE finding: **some safety goals must be assigned to human/organizational agents, not to the software** (agent responsibility assignment in KAOS).

### 1.2 Fault tree (top event: "Person in hazard zone not warned in time")

```
                     [Person not warned in time]
                                 │ OR
      ┌──────────────────┬───────┴─────────┬──────────────────────┐
 [Hazard not       [Warning not       [Warning not          [Warning not
  detected]         issued in time]    delivered]            understood/acted on]
   │ OR              │ OR               │ OR                    │ OR
   ├ no sensor       ├ approver absent  ├ network down         ├ language
   ├ data stale      ├ dispatcher lag   ├ not subscribed       ├ jargon/levels
   ├ bad thresholds  ├ contradiction    ├ phone off/no power   ├ fatigue
   └ flash flood     │  block (wrongly) └ wrong area targeting └ disability barrier
     faster than data└ system crash
 Mitigations:  SR-06, FR-09, FR-37 | FR-21, NFR-PF1/2, NFR-A* | FR-49, SR-01, F20 non-SW | NFR-U*, FR-26, FR-29
```

---

## 2. Conflicting Requirements

| # | Conflict | Stakeholders | Why it is real | Resolution (requirement outcome) | RE technique used |
|---|---|---|---|---|---|
| C1 | **Early warning vs. false alarms** | Residents/farmers (want early) vs. authorities/DHM (want accurate, avoid fatigue) | Earlier = less data = more uncertainty | **Tiered levels**: WATCH is early & low-cost (prepare), WARNING/CRITICAL require stronger evidence + human approval; confidence shown; FN treated as worse than FP for safety-critical scenarios (SO-13), FP rate *monitored and tuned* rather than hard-capped | Goal refinement & obstacle analysis (KAOS); scenario walk-throughs; stakeholder negotiation (WinWin) |
| C2 | **Automated warnings vs. human authorization** | Residents (speed) vs. authorities (legal mandate, accountability) | Approvers may be unavailable at night; automation may be wrong | **Graduated autonomy**: WATCH auto (policy), WARNING 1 approver, CRITICAL 2 approvers, with **timeout escalation** and optional *precautionary auto-publish* clearly labelled — a configurable region policy decided by the authority, not by developers | Risk-based prioritization; policy-as-configuration; trade-off analysis with authorities; documented decision rationale (DRL) |
| C3 | **Privacy vs. location tracking** | Citizens/NGO privacy concerns vs. SAR/police wanting live locations | Location helps rescue but enables surveillance | **Area-based** subscriptions by default; location used on-device; stored only with explicit, purpose-specific consent ("I need help"); retention limits | Privacy-by-design, PIA (privacy impact assessment), misuse cases |
| C4 | **Accuracy vs. speed** | Engineers/DHM vs. residents | More validation & confirmation takes time | Validation is automated & bounded (≤ 60 s **[T]**); conservative use of SUSPECT data with LOW confidence instead of waiting; human approval time bounded by timeout | Quantified NFRs; Quality Function/attribute trade-off (ATAM-lite) |
| C5 | **Rich information vs. simple UI** | Authorities/analysts vs. low-literacy/elderly users | Detailed hydrographs confuse public | **Role-based views**: citizen = one level + one action + "why?" on demand; operator = full evidence. Progressive disclosure. | Personas; prototyping & usability testing; card sorting |
| C6 | **Centralized control vs. local authority** | NDRRMA/DHM (consistency) vs. municipalities (local knowledge, constitutional local powers) | Both have mandates **[F: local governments have DRM functions under Local Gov. Operation Act]** | **Nested authority**: national/official warnings set a floor (SR-07); local operators may issue *more* protective local warnings for their scope; region policies configurable; all warnings show issuing authority | Stakeholder workshops; viewpoint-oriented RE; RACI matrix |
| C7 | **Maximum coverage vs. limited infrastructure** | Equity goal vs. budget/infra realities | Smartphone app reaches only connected users | **Channel-agnostic core**, multi-channel adapters (push, SMS, siren, volunteer relay); coverage-limited areas flagged; equity metric tracked (share of at-risk population reachable by ≥ 1 channel) | Goal-oriented analysis; adding agents (volunteers) to responsibility model |
| C8 | **Frequent notifications vs. fatigue** | Anxious residents/media vs. alert-fatigue risk | Every update notified = noise | Push only on **level change** or action change; WATCH updates in-app; hysteresis; max reminders; user-adjustable verbosity *except* CRITICAL (cannot be muted) | Usability evaluation; scenario simulation with counts of messages |
| C9 | **Openness of data vs. security** | NGOs/researchers want open feeds vs. admins fear spoofing/misuse | Public data aids coordination | Public read-only feeds (CAP/JSON) of *published* warnings; internal data (reports, vulnerability) role-restricted | Misuse cases; data classification |
| C10 | **Volunteer reports vs. sensor data** | Volunteers (local truth) vs. technical staff (instrument trust) | Each can be wrong | Both are inputs with explicit trust levels; conflicts surfaced (UC-12), operator decides; verified volunteers weighted higher | Conflict detection requirement; trust modelling |
| C11 | **Feature richness vs. semester timeline** | Stakeholders vs. student team | Finite capacity | MoSCoW (doc 08); Won't-have list explicit | Prioritization, timeboxing |

### 2.1 How RE techniques resolve conflicts (process)

1. **Detect** — conflicts surfaced through viewpoint analysis (each stakeholder group's requirements recorded separately), a *conflict matrix* (requirements × requirements: conflicts / supports / independent), and NFR trade-off review.
2. **Analyse** — classify: *data conflict* (facts disagree → get evidence), *interest conflict* (goals differ → negotiate), *value conflict* (ethics → apply explicit principle: life safety first), *structural* (authority → follow legal mandate).
3. **Negotiate** — WinWin workshop with representatives; use scenarios ("At 2 a.m. the river rises; approver unreachable — what should happen?") to make abstract conflicts concrete.
4. **Decide & record** — Decision record (ADR-style) with options, rationale, stakeholders consulted, and the requirement IDs changed. Example: *ADR-004 Graduated autonomy for warnings* (C2).
5. **Make configurable when legitimately context-dependent** — e.g. auto-publish policy differs by region (doc 07).
6. **Validate** — test resolution in prototype scenarios and usability sessions; re-open if stakeholders reject.

---

## 3. Project Risk Analysis (risks to the *project*, not the system)

| ID | Risk | Prob | Impact | Mitigation | Owner |
|---|---|---|---|---|---|
| PR1 | Limited access to real stakeholders (officials, at-risk residents) | H | H | Use proxies (DRR lecturers, NGO staff, students from the pilot's flood-prone districts), literature, published post-event reports; label persona assumptions | RE lead |
| PR2 | No access to official DHM real-time API | M | M | Simulated data designed from public historical patterns; adapter interface ready | Data lead |
| PR3 | Scope creep (multi-hazard, ML, native apps) | H | H | MoSCoW; change control board (weekly); Won't-have list | PM |
| PR4 | Routing on OSM data incomplete in rural areas (incl. the Nepal pilot) **[A]** | M | M | Pilot in an area with acceptable OSM coverage; show route confidence; manual path edits | Dev |
| PR5 | Pilot-language (Nepali) quality and Devanagari rendering issues | M | M | Native speakers review all strings; Noto Sans Devanagari font; UCS-2 SMS length tests | UX |
| PR6 | Free-tier limits (Supabase/hosting) | M | L | Small data volumes; scenario playback at demo time only | Dev |
| PR7 | Ethical risk: prototype mistaken for real system | L | H | "PROTOTYPE – NOT AN OFFICIAL WARNING SYSTEM" banner; synthetic subscribers only; no real SMS | PM |
| PR8 | Team member unavailability | M | M | Pair ownership of modules; documentation | PM |
| PR9 | Over-claiming accuracy in report | M | H | Use [F]/[A]/[D]/[T] tags; peer review | RE lead |
