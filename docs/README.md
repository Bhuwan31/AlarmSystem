# AMHEWS — Requirements Engineering Documentation

**Adaptive Multi-Hazard Early Warning and Evacuation Support System** — global by design, first pilot deployment: Nepal
Prototype stack: Supabase (PostgreSQL + PostGIS, Auth, Realtime, Storage) · Python FastAPI · Next.js/React PWA.

> Decision support only. This is not an official warning system and doesn't guarantee prediction or safety.
> Tags used throughout: **[F]** verified fact · **[A]** assumption · **[D]** design decision · **[T]** prototype acceptance target.

> **Main requirements document:** [../REQUIREMENTS_ENGINEERING.md](../REQUIREMENTS_ENGINEERING.md), the consolidated SRS for the 4-week prototype.

## Deliverable map

| # | Deliverable | File |
|---|---|---|
| 1–9 | Title, Abstract, Background, Problem, Motivation, Research questions, Objectives, Scope, Out-of-scope | [01-project-overview.md](01-project-overview.md) |
| 10–12 | Stakeholder analysis, Goals, Personas | [02-stakeholders-and-personas.md](02-stakeholders-and-personas.md) |
| 13 | System context | [02 §6](02-stakeholders-and-personas.md), [03](03-architecture.md) |
| 14 | High-level architecture, data model, API, risk rules, state machine, tech trade-offs | [03-architecture.md](03-architecture.md) |
| 15–19 | Functional, Non-functional, Safety, Security, Privacy requirements | [04-requirements.md](04-requirements.md) |
| 20–21 | Use cases (13), User stories (24) | [05-use-cases-and-user-stories.md](05-use-cases-and-user-stories.md) |
| 22, 23, 26 | Failure scenarios (20), Conflicts (11), Risk analysis | [06-failures-conflicts-risk.md](06-failures-conflicts-risk.md) |
| §11–12 | Pilot context (Nepal), Adaptive / global design, Facts register | [07-pilot-context-nepal-and-adaptive-design.md](07-pilot-context-nepal-and-adaptive-design.md) |
| 24–25 | MoSCoW prioritization, Traceability matrix | [08-prioritization-and-traceability.md](08-prioritization-and-traceability.md) |
| §15, 27 | RE process, Ethics | [09-re-process-and-ethics.md](09-re-process-and-ethics.md) |
| 28–33 | Prototype plan, Validation, Testing, Evaluation, Future work, Limitations, Conclusion | [10-prototype-validation-testing-conclusion.md](10-prototype-validation-testing-conclusion.md) |

## Requirement ID scheme
- `FR-01..FR-68` functional · `NFR-PF/A/R/U/SC/M/I` non-functional · `SR-01..SR-12` safety · `NFR-S1..S9` security · `NFR-PR1..PR8` privacy
- `UC-01..UC-13` use cases · `US-01..US-24` user stories · `F1..F20` failure scenarios · `C1..C11` conflicts · `ST-01..ST-14` scenario tests
- Stakeholders `S1..S24`, goals `G0..G8`, personas `P1..P8`, facts `F1..F15` in the Facts Register (doc 07 §3)

## Open items before submission
1. Verify every **[F]** against its primary source (doc 07 §3). Facts F8, F10 and F11 still need figures from NTA and the NSO census 2021.
2. Replace persona assumptions with findings from real interviews and the questionnaire.
3. Confirm the approval timeouts, retention periods and auto-publish policies with a domain expert.
