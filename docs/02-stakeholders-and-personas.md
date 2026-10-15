# 02 — Stakeholder Analysis, Goals and Personas

> **Global product, Nepal pilot.** AMHEWS is designed for any country or region. Nepal is the **first pilot deployment (testing ground)**. Nepal-specific organisations, languages, laws and numbers in this document describe the pilot's *Deployment Profile* (FR-68), not limits of the product. See [REQUIREMENTS_ENGINEERING.md §1.2.1](../REQUIREMENTS_ENGINEERING.md).

> Deliverables 10–12. Tags: **[F]** fact, **[A]** assumption, **[D]** design decision (see `01-project-overview.md`).
>
> Note on official mandates: roles of government bodies below are summarized from the *Disaster Risk Reduction and Management Act, 2074 (2017)* and the *Local Government Operation Act, 2074 (2017)* **[F — verify wording against the Acts]**. Anything about *how* those bodies would use this system is **[A]** until confirmed by elicitation.

## 1. Stakeholder Classification

| Class | Stakeholders | Role w.r.t. system |
|---|---|---|
| **End users — at-risk public** | S1 Local residents, S2 Residents of flood-prone areas, S3 Farmers, S4 Elderly, S5 Children (via guardians/schools), S6 Persons with disabilities, S7 Tourists/visitors | Receive warnings, use guidance, submit reports |
| **Operators — authorities** | S8 Local government (Municipality / Rural Municipality / Ward), S9 District (DDRMC / DAO), S10 NDRRMA (national), S11 Nepal Police, S12 Armed Police Force, S13 Nepal Army, S14 Fire & emergency services, S15 Hospitals, S16 Search & rescue teams | Monitor, approve/issue warnings, coordinate response |
| **Partners** | S17 Relief orgs/NGOs (incl. Nepal Red Cross Society), S24 Community volunteers | Last-mile dissemination, shelter operations, reports |
| **Infrastructure & data providers** | S18 Telecom providers (e.g. NTC, Ncell) and regulator NTA, S19 Weather & hydrological authority (DHM), S20 Road/transport authorities (DoR, local roads), S23 Other data providers (OSM, satellite/forecast services, census/NSO) | Supply data or channels |
| **Builders & maintainers** | S21 System administrators, S22 Software developers | Configure, operate, evolve |
| **Indirect / regulators** | Media, Ministry of Home Affairs, Privacy/regulatory bodies, University examiners | Influence constraints |

## 2. Power–Interest Grid (for engagement planning) [A]

```
                 HIGH INTEREST
                      │
  Keep satisfied      │   Manage closely
  ─ Telecom (S18)     │   ─ NDRRMA (S10), DHM (S19)
  ─ Nepal Army (S13)  │   ─ Local gov (S8), District (S9)
  ─ Road auth (S20)   │   ─ Police/APF (S11,S12)
                      │   ─ Sys admins (S21)
LOW ──────────────────┼────────────────────── HIGH
POWER                 │                       POWER
  Monitor             │   Keep informed
  ─ Tourists (S7)     │   ─ Residents S1–S6 (low formal power,
  ─ Data providers    │     highest stake — treated as
    (S23)             │     "manage closely" by ethics decision [D])
                      │   ─ NGOs, volunteers, hospitals
                 LOW INTEREST
```

**[D] Ethical override:** At-risk residents have low formal power but the highest stake (life safety). They are elevated to "manage closely" for elicitation and validation.

## 3. Detailed Stakeholder Analysis

### 3.1 At-risk public

| ID | Stakeholder | Goals | Responsibilities | Information needs | Concerns | Constraints | Potential conflicts |
|---|---|---|---|---|---|---|---|
| S1 | **Local residents** | Stay safe; protect family & property; avoid unnecessary evacuation | Follow official guidance; prepare go-bag; help neighbours | Is my area at risk? What should I do now? Where do I go? How long is it valid? | False alarms disrupt life; scams/fake alerts; data misuse | Variable phone type, data balance, literacy, language | vs. authorities (they want fewer, authoritative alerts; residents want early, frequent info); privacy vs. location tracking |
| S2 | **Residents of flood-prone areas** (riverbanks, Terai lowlands, informal settlements) | Earliest possible warning; know safe route at night | Act on Watch (prepare), Warning (move valuables/vulnerable), Critical (evacuate) | Upstream river level trend, time-to-impact estimate, nearest high ground | Alert fatigue; theft of property if they leave; losing livestock | May lack smartphone, power at night; may live in non-mapped settlements **[A]** | vs. false-alarm minimisation (they accept more false alarms) |
| S3 | **Farmers** | Protect crops, livestock, stored grain; plan field work | Move livestock/stock early | Multi-day forecast; river trend; whether to irrigate/harvest | Economic loss from unnecessary evacuation | Often in fields, away from phone; seasonal labour migration **[A]** | Want long-lead low-certainty info that authorities may not want to publish |
| S4 | **Elderly** | Get help early; clear simple instructions | Prepare, ask for assistance | Simple voice/large text; who will help me? | Can't read small text; can't walk far/steep route | Lower smartphone use **[A]**; mobility limits | Need *earlier* warnings than general population (longer evacuation time) |
| S5 | **Children** (via parents, schools) | Be with safe adult; school safety | Schools run drills, follow school safety plan | School-zone alerts; reunification point | Separation from family | Not direct app users; mediated by schools/guardians | School authorities vs. parents on who decides dismissal |
| S6 | **Persons with disabilities** (visual, hearing, mobility, cognitive) | Perceive warning; accessible route & shelter; assistance | Register assistance need (voluntary) | Alerts in multiple modalities; accessible shelter info; step-free route | Exclusion; disclosure of disability data | Assistive tech availability; dependency on carers | Need registry of vulnerable people (privacy conflict) |
| S7 | **Tourists & visitors** (domestic & foreign, trekkers, rafters) | Understand alert without local knowledge | Follow guide/hotel instructions | English (and other) alerts for *where they are now*; no local SIM? | Not subscribed; unfamiliar levels | Roaming/no local SIM; unknown address | Location-based push (needs location) vs. privacy minimisation |

### 3.2 Authorities and response

| ID | Stakeholder | Goals | Responsibilities | Information needs | Concerns | Constraints | Potential conflicts |
|---|---|---|---|---|---|---|---|
| S8 | **Local government** (Municipality / Rural Municipality, Ward offices; Local DRRM Committee) | Protect residents; run evacuation; manage shelters | Local preparedness & response under Local Gov. Operation Act **[F]**; ward-level dissemination | Ward-level risk; which households/vulnerable people; shelter status; resources | Being blamed for wrong/late alerts; no staff at night | Limited IT staff/budget **[A]**; varying capacity across 753 local levels **[F for count]** | vs. district/national on *who issues* alerts (centralized vs. local control) |
| S9 | **District authorities** (District Disaster Management Committee, District Administration Office, CDO) | Coordinate across municipalities; deploy security forces | District coordination; chairs DDMC **[F]** | Multi-municipality picture; escalation needs; resource requests | Conflicting data from municipalities | Communication with remote wards | vs. local on authority; vs. national on thresholds |
| S10 | **NDRRMA** (national) | National situational awareness; policy; consistency of warnings | National DRR coordination, NEOC linkage, BIPAD portal **[F]** | Aggregated risk; trend; resource gaps; standard alert formats | Fragmented systems; non-standard alerts; reputational risk | Must integrate with existing BIPAD & govt systems | vs. local customisation (wants national standards) |
| S11 | **Nepal Police** | Public order; evacuation assistance; traffic control | First response, road control **[A on exact division of duties]** | Where to deploy; road closures; crowd movement | Unclear chain of command; outdated maps | Radio-first comms in field **[A]** | Need precise people-location data (privacy) |
| S12 | **Armed Police Force** | Disaster rescue (incl. water rescue) | SAR deployment | Severity, location, access routes, boat launch points | Late request; unsafe access | Assets limited, prepositioned | Competes for same routes as evacuees |
| S13 | **Nepal Army** | Large-scale rescue, airlift, logistics | Deployed on govt request | Scale, access, helipad/landing points, isolated communities | Unclear requests; duplicate tasking | Formal request chain | Command independence vs. shared dashboard |
| S14 | **Fire & emergency services** | Rapid local response | Rescue, pumping | Incident locations, flooded roads | Overload; false reports | Few units outside cities **[A]** | Citizen report volume vs. triage capacity |
| S15 | **Hospitals** | Continuity of care; mass-casualty readiness; protect own facility | Patient evacuation if facility at risk | Is the hospital or its access road at risk? Expected casualties | Facility flooding; staff can't reach | Critical-power dependencies | Hospital as shelter vs. treatment priority |
| S16 | **Search-and-rescue teams** | Find & rescue trapped people | SAR ops | Precise location of trapped persons, water depth, routes | Location accuracy; unsafe dispatch | Field connectivity | Need real-time location tracking (privacy) |

### 3.3 Partners, providers and builders

| ID | Stakeholder | Goals | Responsibilities | Information needs | Concerns | Constraints | Potential conflicts |
|---|---|---|---|---|---|---|---|
| S17 | **Relief orgs / NGOs** (e.g. Nepal Red Cross, CBEWS NGOs) | Deliver relief; support CBEWS | Shelter ops, relief distribution, community training | Shelter occupancy & needs; vulnerable groups | Duplicated effort; data sharing rules | Donor-driven project cycles | Want broad data access vs. privacy limits |
| S18 | **Telecom providers / NTA** | Network stability; regulatory compliance | Carry SMS/cell-broadcast if agreed | Message volume, priority, geo-target | Network overload during disasters; liability | Capacity, regulatory approval | High-volume alerts vs. network capacity |
| S19 | **DHM** (weather & hydrology) | Accurate forecasts used correctly; single authoritative voice on hydromet warnings | Official hydromet observations/forecasts and flood warnings **[F]** | How their data is used/displayed | Misinterpretation; contradicting official bulletins | Data licensing/access terms **[A]** | **Key conflict:** system must not issue hydromet warnings that contradict DHM |
| S20 | **Road/transport authorities** (Dept. of Roads, local road units) | Road safety; accurate closure info | Close/reopen roads | Where evacuation traffic is directed | Routing traffic onto damaged roads | Closure data often not machine-readable **[A]** | Evacuation route vs. closures for repair |
| S21 | **System administrators** | Reliable, secure operation | Configure, monitor, backup, user management | System health, data freshness, audit trail | Account compromise; 3 a.m. outages | Small team | Security hardening vs. ease of emergency access |
| S22 | **Software developers** (student team) | Deliver a working, defensible prototype on time | Build, test, document | Clear, prioritized, testable requirements | Scope creep; unclear requirements | 1 semester, 4–6 students **[A]**, free-tier services | Feature wishes vs. timeline |
| S23 | **Data providers** (OSM, Open-Meteo, GloFAS/Copernicus, HDX, NSO census) | Correct attribution; fair use | Provide data under licence | Usage, attribution | Licence violations; overuse of APIs | Rate limits, licence terms (e.g. ODbL for OSM) **[F]** | Polling frequency vs. rate limits |
| S24 | **Community volunteers** (CBEWS gauge readers, ward volunteers, youth clubs) | Protect community; be trusted | Read gauges, relay warnings door-to-door, help vulnerable | What to tell whom; who needs help | Being blamed; personal safety | Volunteer time; basic phones | Their manual reports vs. automated data (whom to trust?) |

## 4. Consolidated Stakeholder Goals (goal model)

Goals are refined top-down (KAOS-style). Each leaf goal is realized by requirements in `04-requirements.md`.

```
G0  Reduce human impact of floods (casualties, injuries, evacuation delay, misinformation)
├── G1  Know the risk early           (Monitoring)            → FR-01..FR-10
│    ├── G1.1 Ingest timely, valid data
│    └── G1.2 Detect anomalies / missing data
├── G2  Assess risk per area, transparently (Risk knowledge)  → FR-11..FR-17
├── G3  Warn the right people, correctly (Dissemination)      → FR-18..FR-37
│    ├── G3.1 Never contradictory, never silently dropped
│    ├── G3.2 Human authority for high-impact alerts
│    └── G3.3 Understandable by all (language, literacy, disability)
├── G4  Enable safe action (Preparedness & response)          → FR-38..FR-46
│    ├── G4.1 Safe shelter
│    └── G4.2 Safe route
├── G5  Coordinate authorities                                → FR-51..FR-58
├── G6  Keep working when infrastructure fails                → FR-47..FR-50, NFR-A*
├── G7  Protect trust: security, privacy, accountability      → NFR-S*, NFR-P*, FR-59..FR-62
└── G8  Adapt to new regions, hazards, languages              → FR-63..FR-67, NFR-M*
```

**Obstacles (anti-goals) analysed in `06-failures-conflicts-risk.md`:** missed warning, false warning, delayed warning, spoofed warning, unsafe route, full/closed shelter, misunderstanding, fatigue.

## 5. Personas

> Personas are **composite, fictional** archetypes built from stakeholder analysis **[A]**. They must be validated/refined with real elicitation data (interviews/focus groups) before final submission.

### P1 — Sita Tharu, 38, rice farmer, Bardiya district (Terai)
- **Context:** Lives ~300 m from a river embankment with husband, two children, mother-in-law (72, limited mobility), two buffaloes. Shared Android phone with low data balance; strong Tharu & Nepali speaking, reads Nepali slowly.
- **Goals:** Enough time to move mother-in-law and animals; know which school building is open as shelter.
- **Frustrations:** "Last year the warning came on the radio after the water was in the courtyard." Many alerts in English. Mobile data runs out.
- **Needs →** voice/IVR or SMS in Nepali (Tharu desirable), Watch-level "prepare" message hours earlier, shelter that accepts livestock nearby, works without data.
- **Key requirements:** FR-30, FR-33, FR-35, FR-40, FR-47, NFR-U3, NFR-U5.

### P2 — Ram Bahadur Karki, 74, retired teacher, ward in Kathmandu Valley near a river
- **Context:** Lives alone; uses a basic feature phone; wears glasses; hard of hearing; son works abroad.
- **Goals:** Someone to tell him early and help him leave.
- **Needs →** loud/repeated alerts, SMS with simple text, volunteer assistance flag, son can subscribe remotely to father's area.
- **Key requirements:** FR-32 (proxy subscription), FR-36 (assistance request), NFR-U2.

### P3 — Anjali Shrestha, 29, Ward Disaster Focal Person, Municipality
- **Context:** Uses laptop at office, smartphone in field; responsible for 4 wards; not an IT specialist; on-call during monsoon.
- **Goals:** Trusted picture of which wards are at risk; quick, safe way to issue/approve a warning; know shelter occupancy.
- **Frustrations:** Data from different WhatsApp groups contradicts; fears issuing a wrong evacuation order.
- **Needs →** approval workflow with clear evidence, template messages, preview of who will receive, undo/cancel with correction message, audit log that protects her.
- **Key requirements:** FR-20, FR-21, FR-25, FR-27, FR-53, SR-02.

### P4 — Inspector Bikash Thapa, 41, District Police / DEOC duty officer
- **Context:** Works at District Emergency Operation Centre during events; coordinates with APF/Army.
- **Goals:** Know where to deploy, which roads are closed, where calls for help are clustered.
- **Needs →** map of incidents and citizen reports with verification status, road closures layer, evacuation progress counts.
- **Key requirements:** FR-52, FR-54, FR-56, FR-57.

### P5 — Emma Müller, 31, foreign trekker/rafter in Western Nepal
- **Context:** No Nepali; tourist SIM or Wi-Fi only; staying in guest houses.
- **Goals:** Understand any alert where she is now.
- **Needs →** English UI, location-based (consented) alerts or QR-code area subscription at guesthouses, universal icons.
- **Key requirements:** FR-31, FR-34, NFR-U4, NFR-PR2.

### P6 — Kamal Bishwakarma, 23, community volunteer & gauge reader (CBEWS)
- **Context:** Reads a staff gauge manually; has smartphone; volunteers for youth club.
- **Goals:** His readings are trusted and reach decision-makers; tells neighbours what to do.
- **Needs →** quick structured report form that works offline, acknowledgement, verified-reporter status.
- **Key requirements:** FR-37, FR-08, FR-56.

### P7 — Nisha Gurung, 26, system administrator (municipal IT or project ops)
- **Goals:** Configure a new municipality in a day; sleep at night.
- **Needs →** region/threshold configuration UI with validation, data-source health dashboard, MFA, audit logs, backup/restore.
- **Key requirements:** FR-63..FR-67, NFR-S1..S4, NFR-M2.

### P8 — Hari Prasad Yadav, 45, wheelchair user, Saptari (Terai)
- **Goals:** Step-free route & accessible shelter, a carer alerted at the same time.
- **Needs →** accessibility filter on shelters, carer/proxy notification, assistance request routed to volunteers.
- **Key requirements:** FR-39, FR-36, FR-32.

## 6. System Context

```
                     ┌───────────────────────────── EXTERNAL DATA ────────────────────────────┐
                     │ DHM hydro/met (future API)  Open-Meteo forecast  GloFAS flood forecast │
                     │ Simulated gauges/rain       OSM roads & POIs     Admin boundaries (HDX)│
                     │ Population (census/WorldPop) Road closures (manual/Dept. of Roads)     │
                     └───────────────┬─────────────────────────────────────────────────────────┘
                                     │ pull / push (adapters)
 ┌──────────────┐  reports  ┌────────▼────────────────────────────────┐  alerts   ┌───────────────────┐
 │ Citizens,    │──────────►│                                         │──────────►│ Channels:         │
 │ volunteers,  │◄──────────│        AMHEWS (system boundary)   │           │ Web push / PWA    │
 │ tourists     │ risk,     │                                         │           │ SMS gateway (sim) │
 └──────────────┘ guidance  │  ingest → validate → assess → propose   │           │ Email             │
                            │  → approve → disseminate → log          │           │ Siren/IVR (sim)   │
 ┌──────────────┐ approve,  │  shelters · routing · dashboards        │           │ CAP feed (future) │
 │ Local/Dist./ │ issue,    │                                         │           └───────────────────┘
 │ National ops │──────────►│                                         │  CAP/JSON  ┌──────────────────┐
 │ Police/APF/  │◄──────────│                                         │──────────►│ BIPAD / NEOC     │
 │ Army/Fire    │ situation │                                         │  (future)  │ (interop target) │
 └──────────────┘           └─────────────────▲───────────────────────┘           └──────────────────┘
                                              │ configure, monitor
                                       ┌──────┴───────┐
                                       │ Admins       │
                                       └──────────────┘
```

**Boundary decisions [D]:** The system *does not* own gauges, sirens, telecom networks or the legal authority to order evacuation. It owns: data validation, risk computation, warning workflow, message composition, dissemination orchestration, evacuation guidance, logs.
