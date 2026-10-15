# 05 — Use Cases and User Stories

> Deliverables 20–21. Requirement IDs refer to `04-requirements.md`. Notation: **MF** main flow, **AF** alternative flow, **EF** exception flow.

## Use Case Overview

```
             ┌──────────────────────── AMHEWS ─────────────────────────┐
 Citizen ────┤ UC-01 Receive flood warning      UC-04 Find nearest shelter   │
 (Tourist,   │ UC-02 Check local risk level     UC-05 Report flooding        │
  Volunteer) │ UC-03 Request evacuation guidance                             │
             │                                                               │
 Authority ──┤ UC-06 Monitor flood risk         UC-08 Update shelter avail.  │
 Operator    │ UC-07 Issue emergency warning                                 │
             │                                                               │
 System  ────┤ UC-09 Detect abnormal data       UC-11 Handle unavailable data│
 (timer)     │ UC-10 Generate risk assessment   UC-12 Handle conflicting data│
             │                                                               │
 Admin   ────┤ UC-13 Configure a region                                      │
             └───────────────────────────────────────────────────────────────┘
 «include»: UC-03 → UC-04 ; UC-10 → UC-09 ; UC-07 → (approval) ; UC-01 ← UC-07/UC-10
```

---

### UC-01 Citizen receives flood warning
| Field | Content |
|---|---|
| **Actor** | Citizen (primary: subscribed resident; secondary: Notification channel, Approver) |
| **Preconditions** | Citizen has ≥ 1 subscription (area + channel + language). A warning for that area becomes ACTIVE. |
| **Trigger** | Warning Manager sets warning status ACTIVE (UC-07 or UC-10 path). |
| **MF** | 1. System selects subscriptions whose area intersects target areas. 2. System renders message in subscriber's language and channel format. 3. Dispatcher sends CRITICAL first, then WARNING, then WATCH. 4. Citizen device shows notification with level icon, area, action, valid-until. 5. Citizen opens it; app shows action card and "Find shelter" button. 6. Citizen taps "I'm safe" / "I need help" (acknowledge). 7. System records ack. |
| **AF** | A1 (step 4) Citizen has SMS only → receives compact SMS with short link/code. A2 (step 6) Citizen ignores → no ack; for CRITICAL, system re-sends after configured interval once (max 2 reminders). A3 Citizen is a proxy subscriber → message names whom it concerns ("for: Father's home, Ward 7"). |
| **EF** | E1 Push fails → fallback to SMS (FR-49), failure recorded. E2 All channels fail → delivery `failed`; operator dashboard shows failed count (SR-01). E3 Warning cancelled before delivery → delivery skipped, no all-clear sent to those who never got it. |
| **Postconditions** | Every targeted subscription has a delivery record in a final state; audit entries exist. |
| **Related req.** | FR-29, FR-30, FR-24, FR-35, FR-49, NFR-PF2, NFR-R3, SR-01 |

### UC-02 Citizen checks local risk level
| Field | Content |
|---|---|
| **Actor** | Citizen / Tourist |
| **Preconditions** | PWA reachable or cached. |
| **Trigger** | Citizen opens app/home page. |
| **MF** | 1. Citizen selects area (list/search) or grants location once, or scans area QR. 2. System resolves area. 3. System shows level (word+icon+colour), one-line action, confidence badge, last updated time, valid-until of any warning. 4. Citizen can tap "Why?" to see plain-language reasons (e.g. "River at Station X rising fast"). 5. Citizen can switch language or play audio. |
| **AF** | A1 Location denied → manual area selection. A2 Location outside configured regions → "No coverage here – follow local authorities" + national emergency numbers. |
| **EF** | E1 Offline → cached state with "Last updated hh:mm – may be outdated" (FR-47). E2 Area data stale → "Data delayed" badge and LOW confidence (SR-06, SR-08). |
| **Postconditions** | No personal data stored (unless subscription created). |
| **Related req.** | FR-13, FR-14, FR-15, FR-31, FR-34, FR-47, NFR-U1..U5, NFR-PR2, SR-10 |

### UC-03 Citizen requests evacuation guidance
| Field | Content |
|---|---|
| **Actor** | Citizen |
| **Preconditions** | Area is at WARNING or CRITICAL (guidance also available at other levels for planning). Road graph loaded. |
| **Trigger** | Citizen taps "Evacuate / Get route". |
| **MF** | 1. System obtains origin (GPS with consent, or map pin). 2. «include» UC-04 to choose shelter (default nearest suitable). 3. System removes hazard-zone edges, closures, unsafe bridges. 4. System computes primary and alternative routes. 5. System displays route, distance, estimated walking time, warnings on route, data timestamp, disclaimer. 6. Citizen starts navigation (map view; step list in text for screen readers). |
| **AF** | A1 Citizen chooses "accessible route" → step-free preference/penalties applied. A2 Citizen chooses vehicle mode. A3 Conditions change during evacuation → updated route pushed (FR-45). |
| **EF** | E1 No safe route → "No safe route found. Move to the highest floor or nearest high ground. Call 100/your ward." (FR-44, SR-03). E2 GPS accuracy > 100 m → ask user to confirm position on map (F14). E3 Offline → show cached shelter list and static map; no live routing. |
| **Postconditions** | Route request logged (without storing precise origin beyond session unless consent). |
| **Related req.** | FR-41..FR-46, SR-03, SR-04, NFR-PF3, NFR-PR2 |

### UC-04 Citizen finds nearest shelter
| Field | Content |
|---|---|
| **Actor** | Citizen |
| **Preconditions** | Shelters configured. |
| **Trigger** | Citizen taps "Shelters" or UC-03 step 2. |
| **MF** | 1. System gets origin. 2. Filters shelters: status open, capacity available, not inside active hazard zone. 3. Ranks by safe-route distance. 4. Shows top 3 with occupancy, last updated, facilities. 5. Citizen selects one → detail or route. |
| **AF** | A1 Filters (accessible, livestock, medical). A2 Citizen calls shelter contact. |
| **EF** | E1 No shelter available → nearest high-ground safe points (if configured) + authority contact. E2 Occupancy data older than threshold (e.g. 2 h) → "Occupancy may be outdated". |
| **Postconditions** | None persistent. |
| **Related req.** | FR-38..FR-40, SR-05 |

### UC-05 Citizen reports flooding
| Field | Content |
|---|---|
| **Actor** | Citizen / Community volunteer |
| **Preconditions** | — |
| **Trigger** | Citizen taps "Report". |
| **MF** | 1. Choose category (water rising, road flooded, bridge damaged, landslide, people trapped, other) via icons. 2. Location from GPS (consent) or map pin. 3. Optional water depth (pictogram: ankle/knee/waist/above), photo, text. 4. Submit. 5. System validates, rate-limits, stores as `new`, shows reference number. 6. Report appears on operator map (UC-06). |
| **AF** | A1 Verified volunteer → report marked "trusted source", higher weight in conflict checks (FR-09). A2 "People trapped" → creates high-priority incident immediately. |
| **EF** | E1 Offline → queued in PWA, auto-submitted later with original timestamp (FR-37). E2 Rate limit exceeded → polite message, emergency numbers shown. E3 Photo too large → compressed client-side. |
| **Postconditions** | Report stored; never by itself triggers a public warning (NFR-S6). |
| **Related req.** | FR-37, FR-56, FR-09, NFR-S6, NFR-PR8 |

### UC-06 Authority monitors flood risk
| Field | Content |
|---|---|
| **Actor** | Local/District operator |
| **Preconditions** | Logged in with MFA; scope assigned. |
| **Trigger** | Operator opens dashboard / receives realtime alert. |
| **MF** | 1. Dashboard shows map + area list (by level, vulnerability) + station hydrographs + data-health panel + pending approvals. 2. Operator inspects area: reasons, confidence, trend, reports nearby. 3. Operator views delivery stats/evacuation progress for active warnings. 4. Operator verifies/rejects reports. |
| **AF** | A1 Operator adds road closure (FR-43). A2 Operator opens timeline for area (FR-60). |
| **EF** | E1 Realtime connection lost → banner "Live updates paused", auto-reconnect, manual refresh. E2 Data source degraded → highlighted. |
| **Postconditions** | Actions audited. |
| **Related req.** | FR-48, FR-51, FR-52, FR-54, FR-56, FR-57, NFR-PF5 |

### UC-07 Authority issues emergency warning
| Field | Content |
|---|---|
| **Actor** | Operator (initiator), Approver(s) |
| **Preconditions** | MFA session; scope covers target areas. |
| **Trigger** | Operator decides to warn (from proposal or manually, e.g. embankment breach report). |
| **MF** | 1. Operator selects areas, hazard, level, template. 2. System fills message in ne/en; operator may edit. 3. System shows recipient preview (count per area/channel) and contradiction check. 4. Operator submits → PROPOSED. 5. Approver reviews evidence → approves (CRITICAL: second approver approves). 6. ACTIVE → UC-01. 7. Dashboard shows delivery progress. |
| **AF** | A1 Operator is also an approver for WARNING → may self-approve WARNING only if region policy allows; never CRITICAL. A2 Escalation of existing warning → new version supersedes. A3 Cancel → reason + all-clear (FR-25). |
| **EF** | E1 Contradiction with active/official warning → blocked with explanation (FR-28). E2 Second approver unavailable → timeout escalation (FR-21). E3 Approval rejected → reason recorded; initiator notified. E4 Exercise mode → "EXERCISE" prefix enforced (SR-12). |
| **Postconditions** | Warning ACTIVE or REJECTED; full audit trail. |
| **Related req.** | FR-20..FR-23, FR-25, FR-28, FR-29, FR-53, SR-02, SR-07, SR-09, NFR-S1, NFR-S5 |

### UC-08 Authority updates shelter availability
| Field | Content |
|---|---|
| **Actor** | Shelter manager (local operator / NGO staff with shelter role) |
| **Preconditions** | Assigned to shelter. |
| **Trigger** | Occupancy or status changes. |
| **MF** | 1. Open shelter (mobile-friendly form). 2. Update occupancy (+/− buttons) and/or status. 3. Save → timestamp, audit. 4. Citizen recommendations update immediately. |
| **AF** | A1 Mark "unsafe" (e.g. water entering) → system notifies users who were routed there in last N minutes with alternative shelter. A2 Bulk update via SMS keyword (Could, future). |
| **EF** | E1 Offline → form queued with warning "Not yet sent". E2 Occupancy > capacity → allowed with confirmation, status auto `full`. |
| **Postconditions** | Shelter record current. |
| **Related req.** | FR-40, FR-55, FR-45, SR-05 |

### UC-09 System detects abnormal environmental data
| Field | Content |
|---|---|
| **Actor** | System (Processing Layer); secondary: Operator, Admin |
| **Preconditions** | Station configured with plausible range, spike Δ, flatline N. |
| **Trigger** | New observation arrives. |
| **MF** | 1. Validate schema/units. 2. Range check. 3. Spike check vs. previous valid. 4. Flatline check. 5. Assign quality. 6. If SUSPECT/BAD → open quality event, notify operators of affected areas, show on data-health panel. 7. Risk engine uses GOOD (and SUSPECT with reduced confidence). |
| **AF** | A1 Spike confirmed by next readings (sustained rise) → reclassify as GOOD; this is a *real* rapid rise (rate-of-rise rule R4 applies). |
| **EF** | E1 Malformed payload → rejected, logged, counted toward source health. |
| **Postconditions** | Quality flag set; event recorded. |
| **Related req.** | FR-06, FR-08, FR-10, NFR-R1 |

### UC-10 System generates automatic risk assessment
| Field | Content |
|---|---|
| **Actor** | System (Risk Engine) |
| **Preconditions** | Area–station links and thresholds configured. |
| **Trigger** | New valid observation, timer (every 5 min), config change. |
| **MF** | 1. Determine affected areas. 2. Build input snapshot (latest valid readings, rate, upstream, rainfall, forecast, reports). 3. «include» UC-09 results (quality). 4. Apply rules R1–R9; compute level, confidence, reasons. 5. Apply hysteresis R10. 6. Store assessment. 7. If level ≥ WATCH and differs from active warning → create/update proposal (FR-18/FR-23). 8. Publish realtime update. |
| **AF** | A1 Level unchanged → only refresh `computed_at`. A2 Level decreases → de-escalation proposal after hold time. |
| **EF** | E1 Engine exception for one area → that area marked UNKNOWN with alert to admins; other areas continue. |
| **Postconditions** | Every area has a fresh assessment or explicit UNKNOWN. |
| **Related req.** | FR-11, FR-12, FR-14, FR-15, FR-18, FR-26, NFR-PF1 |

### UC-11 System handles unavailable data
| Field | Content |
|---|---|
| **Actor** | System (Health Monitor) |
| **Preconditions** | Staleness windows configured. |
| **Trigger** | No valid data from a source within its window, or adapter errors. |
| **MF** | 1. Mark source/station stale; open quality event. 2. Hold last valid level for dependent areas (never downgrade, SR-06); confidence LOW. 3. Use alternative sources if linked (upstream, rainfall). 4. Notify operators and admin. 5. Citizen views show "Data delayed". 6. On recovery, close event, recompute. |
| **AF** | A1 Stale while area was NORMAL and no other signals → level UNKNOWN shown to operators; citizens see "Normal (data delayed)". A2 Prolonged outage (> configured, e.g. 3 h) during monsoon → prompt operators to obtain manual gauge readings (volunteer SOP). |
| **EF** | E1 All sources down → system-wide degraded banner; manual operations SOP. |
| **Postconditions** | Outage window recorded for post-event analysis. |
| **Related req.** | FR-07, FR-15, FR-48, SR-06, NFR-R2 |

### UC-12 System handles conflicting data
| Field | Content |
|---|---|
| **Actor** | System; Operator (resolver) |
| **Preconditions** | ≥ 2 linked sources for an area. |
| **Trigger** | Disagreement beyond tolerance (e.g. gauge NORMAL, multiple verified reports of overtopping; or two gauges inconsistent with travel time). |
| **MF** | 1. Raise conflict event with both values. 2. Apply conservative rule: use the higher-risk interpretation for level, LOW confidence (safety bias). 3. Present conflict to operator with evidence side-by-side. 4. Operator resolves: trust A / trust B / dispatch verification. 5. System records decision; recompute. |
| **AF** | A1 Conflict from unverified reports only → no level change; operator prompted to verify. |
| **EF** | E1 Operator unavailable → conservative rule persists; escalate after timeout. |
| **Postconditions** | Conflict event closed with resolution and actor. |
| **Related req.** | FR-09, FR-15, FR-56, SR-06, SR-08 |

### UC-13 Administrator configures a region
| Field | Content |
|---|---|
| **Actor** | Administrator; second approver |
| **Preconditions** | Admin with MFA. |
| **Trigger** | New municipality joins pilot. |
| **MF** | 1. Create region (names ne/en, timezone, policies). 2. Upload boundaries GeoJSON → validate geometry, hierarchy. 3. Add population/vulnerability attributes (CSV). 4. Add stations and thresholds, link to areas with travel times. 5. Import road network (OSM extract) and shelters. 6. Select languages/templates and channels. 7. Run configuration validation (every area linked to ≥ 1 station or flagged "no monitoring"; thresholds ordered watch < warning < danger; templates complete). 8. Submit → second approver approves → region `active` (or `exercise`). |
| **AF** | A1 Clone from existing region template. A2 Activate in `exercise` mode first. |
| **EF** | E1 Validation errors → listed, cannot activate. E2 Threshold source unknown → must enter provenance note. |
| **Postconditions** | Region live; config version recorded. |
| **Related req.** | FR-63..FR-67, NFR-M2, NFR-S4, NFR-SC1 |

---

## User Stories

Format: *As a ⟨role⟩, I want ⟨goal⟩ so that ⟨benefit⟩.* Acceptance in Gherkin for key stories.

| ID | Story | Req | Pri |
|---|---|---|---|
| US-01 | As a riverside resident, I want a warning in my own language (pilot: Nepali) on my phone when my ward is at risk, so that I can move my family early. | FR-30 | M |
| US-02 | As a feature-phone user, I want warnings by SMS, so that I get them without internet. | FR-35 | M |
| US-03 | As a son working abroad, I want to subscribe to my father's ward, so that I can call him when danger rises. | FR-32 | S |
| US-04 | As a citizen, I want to see why my area is at risk, so that I can trust the warning. | FR-14 | M |
| US-05 | As a citizen with low literacy, I want icons and audio, so that I understand the warning without reading. | NFR-U3, U5 | M |
| US-06 | As a wheelchair user, I want only accessible shelters and step-free routes, so that I can actually reach safety. | FR-39 | S |
| US-07 | As a farmer, I want a "prepare" alert hours ahead, so that I can move livestock and grain. | FR-19 | S |
| US-08 | As a tourist, I want to scan a QR at my guesthouse to get English alerts for this area. | FR-34 | S |
| US-09 | As a volunteer gauge reader, I want to submit readings offline, so that they reach the municipality when signal returns. | FR-37 | M |
| US-10 | As a ward focal person, I want a proposed warning with evidence, so that I can approve quickly but responsibly. | FR-18, FR-20 | M |
| US-11 | As an approver, I want to see who will receive a warning before I send it, so that I don't alert the wrong area. | FR-53 | M |
| US-12 | As an operator, I want to cancel a wrong warning and send a correction to the same people, so that confusion is minimized. | FR-25 | M |
| US-13 | As a district duty officer, I want delivery and acknowledgement stats, so that I know where to send door-to-door teams. | FR-54, FR-57 | M |
| US-14 | As a shelter manager, I want to update occupancy in two taps, so that people aren't sent to a full shelter. | FR-55 | M |
| US-15 | As a police officer, I want to mark a road closed, so that evacuation routes avoid it. | FR-43 | M |
| US-16 | As an admin, I want to know immediately when a gauge goes silent, so that we don't mistake silence for safety. | FR-07, FR-48 | M |
| US-17 | As an admin, I want to configure a new municipality from files, so that the system can expand without developers. | FR-63 | M |
| US-18 | As NDRRMA, I want warnings exported in CAP, so that they can feed national systems. | FR-58 | S |
| US-19 | As an analyst, I want a timeline of a past event, so that we can learn what went wrong. | FR-60 | S |
| US-20 | As a citizen, I want an "I need help" button, so that rescuers know where I am. | FR-24, FR-36 | S |
| US-21 | As DHM, I want the system never to contradict our official warning, so that the public hears one voice. | FR-28, SR-07 | M |
| US-22 | As a citizen, I want my location not stored, so that I'm not tracked. | NFR-PR2 | M |
| US-23 | As a developer, I want to add a landslide model as a plug-in, so that the system grows without rewriting it. | NFR-SC2 | M |
| US-24 | As a trainer, I want an exercise mode, so that drills never look like real warnings. | SR-12 | S |

**Gherkin examples**

```gherkin
Feature: Two-person approval for evacuation warnings  (FR-20, SR-02)
  Scenario: Same approver cannot approve twice
    Given a CRITICAL warning proposal for Ward 5
    And approver "anjali" has approved it
    When "anjali" approves it again
    Then the system rejects the action with "second distinct approver required"
    And the warning status remains PROPOSED

Feature: Data loss never lowers risk  (SR-06)
  Scenario: Gauge stops while at WARNING
    Given Ward 3 is at WARNING based on station ST-01
    When ST-01 sends no data for longer than its staleness window
    Then Ward 3 remains at WARNING
    And its confidence is LOW
    And operators of Ward 3 receive a "data stale" alert

Feature: Safe routing  (SR-03)
  Scenario: Only route crosses flooded bridge
    Given bridge B-12 is flagged unsafe
    And the only path from point P to Shelter S crosses B-12
    When a citizen requests a route from P to S
    Then the system returns "no safe route" with fallback advice
    And no route geometry crosses B-12
```
