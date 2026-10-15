# 09 — Requirements Engineering Process and Ethical Considerations

> Section 15 and Deliverable 27.

## 1. RE Lifecycle Applied to This Project

```
 Elicitation ─► Stakeholder analysis ─► Analysis & modelling ─► Classification ─► Prioritization
      ▲                                                                                 │
      │                    (iterative, 2-week sprints; spec is a living baseline)        ▼
 Change mgmt ◄─ Requirements mgmt ◄─ Verification ◄─ Validation ◄─ Specification ◄─ Conflict resolution
```

| # | Activity | What we do | Techniques | Outputs |
|---|---|---|---|---|
| 1 | **Elicitation** | Gather needs from reachable stakeholders and proxies; study existing systems (DHM alerts, BIPAD, CBEWS projects) and post-event reports | **Interviews** (semi-structured: 1 municipal/DRR officer or NGO staff if reachable, DRR lecturer, 3–5 residents from flood-prone districts, 1 volunteer); **questionnaire** (online + paper, ne/en: phone type, channels, language, trust in alerts); **document analysis** (Acts, DHM bulletins, after-action reports); **observation** of existing alert apps/portals (system archaeology); **focus group** with Nepali students from Terai districts as resident proxies; **scenarios** ("2 a.m., river rising") | Interview notes, survey data, raw requirements log |
| 2 | **Stakeholder analysis** | Identify, classify, map power/interest, define viewpoints | Onion model, power–interest grid, RACI for warning authority | Doc 02 |
| 3 | **Analysis & modelling** | Turn raw needs into goals, obstacles, agents; detect ambiguity, gaps | **Goal modelling** (KAOS-lite goal tree, obstacle analysis), **use cases**, **state machine** for warnings, **context diagram**, **misuse cases** (attacker issues fake warning), **personas** | Docs 02, 03, 05, 06 |
| 4 | **Classification** | FR vs. NFR (ISO 25010 categories); safety/security/privacy; core vs. configurable; by component & goal | Tagging in YAML | Doc 04, 07 |
| 5 | **Prioritization** | MoSCoW with weighted scoring | Scoring workshop, $100 test with stakeholders for Should/Could | Doc 08 |
| 6 | **Conflict resolution** | Detect, analyse, negotiate, record | Conflict matrix, WinWin negotiation, decision records (ADRs) | Doc 06 §2 |
| 7 | **Specification** | Write requirements to IEEE 29148 quality attributes | Templates (EARS patterns for SRs: *"When ⟨trigger⟩, the system shall…"*, *"If ⟨unwanted condition⟩, then…"*), glossary, Gherkin criteria | Doc 04, 05 |
| 8 | **Validation** ("right requirements?") | Confirm with stakeholders that requirements reflect needs | **Reviews/walkthroughs** with domain proxies; **prototype demos** (paper → clickable Figma → working PWA); **scenario walkthroughs** of failure cases; **usability tests**; checklist inspection | Validation log, change requests |
| 9 | **Verification** ("requirements met?") | Show the built system satisfies requirements | Tests traced to requirement IDs; scenario oracles; inspection of RLS/privacy; analysis of logs | Test reports, RTM coverage |
| 10 | **Requirements management** | Baseline, version, trace | Requirements as YAML in Git; RTM generated in CI; unique stable IDs, never reused | RTM, baselines v0.1, v0.5, v1.0 |
| 11 | **Change management** | Control change, assess impact | Change request form (ID, reason, source, affected reqs via trace, safety impact, effort); weekly Change Control Board (PM, RE lead, tech lead, safety reviewer); any change touching SR-* requires safety re-review and re-run of scenario tests | Change log; updated baseline |

### 1.1 Ambiguity management
Maintain an **ambiguity log**. Examples found and resolved:

| Ambiguous term | Problem | Resolution |
|---|---|---|
| "timely warning" | Untestable | Split: NFR-PF1 (generation ≤ 60 s [T]) + lead time metric (doc 10) |
| "nearby shelter" | Straight-line vs. walkable? | Ranked by *safe-route* distance (FR-38) |
| "safe route" | Safe from what? | Excludes WARNING+ zones, closures, unsafe bridges; states limitations (SR-03/04) |
| "area" | District? Ward? Pixel? | Defined *Area Unit*, configurable granularity |
| "the authority" | Which one? | Nested authority & role scopes (C6, FR-66) |
| "real-time" | Seconds? Minutes? | Quantified per NFR |

### 1.2 Requirements under uncertainty and change
- **Volatile requirements are identified up front** (thresholds, policies, languages, channels, data sources) and *designed as configuration*, so change does not require redevelopment.
- **Assumption register** (all [A] tags) reviewed each sprint; a falsified assumption triggers a change request.
- **Uncertainty in the domain is made explicit in requirements** (confidence, staleness, LOW-confidence highlighting) instead of hidden.

### 1.3 Proposed semester elicitation instruments (summary)
- *Resident interview guide (ne/en, 20 min):* past flood experience; how warning was received; trust; phone/channel; language; what action they'd take at each level (test level comprehension with mock cards); privacy comfort with location.
- *Official/NGO interview guide (45 min):* current warning chain; who authorizes; night-time process; data they trust; what a dashboard must never do; shelter management practice.
- *Questionnaire:* 15 closed + 3 open questions; target ≥ 30 responses.
- **Ethics approval:** obtain university research-ethics approval before human-participant research; informed consent; no collection of identifying data beyond necessity.

## 2. Ethical and Social Considerations

> **Positioning statement (to appear in UI, docs and presentation):**
> *This system provides early-warning information and decision support. It does not predict floods with certainty, does not guarantee safety, and does not replace official warnings or instructions from government authorities, police or emergency services. The absence of a warning does not mean an area is safe.*

| Issue | Analysis | Requirement / design response |
|---|---|---|
| **False alarms** | Cost to livelihoods (farmers, daily-wage workers), fatigue, trust erosion; disproportionately affects poor who cannot afford lost days | Tiered levels; human approval for WARNING+; transparent reasons; post-event review published; FP metrics (FR-62) |
| **Missed warnings** | Most severe harm; cannot be eliminated (flash floods, unmonitored tributaries) | Conservative rules; citizen reports; explicit "no monitoring" disclosure; SR-10 disclaimer; community EWS retained |
| **Responsibility for incorrect recommendations** | Who is accountable — developers, operator, authority, data provider? | Human approval for high-impact warnings places decision with mandated authority; audit trail shows evidence available at the time; routes/shelters carry limitations; developers responsible for verified correct implementation of specified rules; data providers' quality flags recorded |
| **Privacy** | Location and disability data are sensitive | Minimisation, consent, retention limits (NFR-PR*) |
| **Surveillance concerns** | Emergency systems can be repurposed for tracking (function creep) | Purpose limitation in requirements; no continuous tracking; access audit; data not shared for non-DRR purposes |
| **Digital exclusion** | App-only systems exclude poor, elderly, women with less phone access, remote communities | Channel-agnostic design; SMS; proxy subscriptions; volunteer/siren integration; equity metric (reachability) |
| **Accessibility** | Disabled people have higher disaster mortality risk **[A — widely reported in DRR literature; cite UNDRR survey 2013/2023]** | WCAG 2.2 AA; multimodal alerts; accessible shelters & routes; assistance requests |
| **Language barriers** | Nepali is mother tongue of under half the population [F9] | ne+en mandatory; language packs; icons; audio; native-speaker review |
| **Algorithmic bias** | Thresholds/data density favour well-monitored (often urban/richer) areas; OSM gaps in poor/rural areas yield worse routes | Coverage & confidence shown per area; vulnerability modifier can *raise* priority; evaluate metrics per area type (urban/rural) |
| **Vulnerable communities** | Informal settlements may be unmapped; migrants may lack local SIMs | Area-code/QR subscription; community volunteers; operator manual areas |
| **Transparency** | People trust warnings they understand | "Why?" explanations; open, documented rules; public CAP feed |
| **Human oversight** | Automation bias: approvers rubber-stamping proposals | Evidence displayed at approval; LOW-confidence highlight; approval requires viewing evidence; post-event review of approval decisions |
| **Public trust** | Fake warnings or contradictions destroy credibility quickly | Security controls; single-voice rule (SR-07); corrections to same recipients; exercise labelling |
| **Research ethics (project)** | Interviews with disaster-affected people risk re-traumatisation | Trauma-informed questions, voluntary participation, ethics approval, right to withdraw |
