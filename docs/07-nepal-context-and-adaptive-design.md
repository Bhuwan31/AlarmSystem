# 07 — Nepal-Specific Considerations and Adaptive Design

> Sections 11–12 of the brief. Every statement is tagged **[F]** verified fact (with source in the Facts Register), **[A]** project assumption, or **[D]** design decision.
>
> **Verification rule for the team:** before submission, open each source in §3 and confirm the exact figure/wording; replace secondary sources (news, Wikipedia) with the primary source (NSO report, Act text, DHM page) where possible.

## 1. Nepal-Specific Analysis

| Characteristic | Verified facts [F] | Assumptions to validate [A] | Design decisions [D] |
|---|---|---|---|
| **Mountainous geography** | Elevation rises from the Terai lowlands to the Himalaya within a short north–south span (F1). | Steep terrain reduces GPS accuracy in valleys and makes some routes impassable after landslides. | GPS accuracy check & manual pin (F14); routes carry confidence; multi-hazard: landslide closures feed flood routing. |
| **Terai flood-prone areas** | Major rivers (Koshi, Gandaki/Narayani, Karnali, Mahakali, plus Rapti, Bagmati, Kamala etc.) flow south into the Terai (F1). Large historical Terai floods: Koshi embankment breach 2008, August 2017 Terai floods (F5). | Flat terrain = longer flood duration, larger inundation extents; lead times on large rivers are hours, not minutes. | Pilot area in Terai; upstream-lead rule R5; shelter attributes for livestock. |
| **Remote rural communities** | Most local levels are rural municipalities (460 of 753) (F3). | Many remote wards have poor connectivity and long travel time to services. | Coverage-limited flag per area; volunteer & siren channels in design; earlier WATCH. |
| **Monsoon rainfall** | Majority of annual rainfall falls in the summer monsoon (~June–September) (F2). | Most flood warnings will cluster in this window → operator load peaks. | Maintenance freeze (NFR-A4); seasonal configuration (e.g. more frequent polling in monsoon). |
| **River systems** | DHM operates a hydrological station network and publishes real-time river levels with warning/danger thresholds on its hydrology portal (F4). | API access for third parties may require agreement. | Adapter interface; thresholds stored with provenance; simulated feeds in prototype. |
| **Landslide-prone areas** | Late-Sept 2024 monsoon rains caused floods and landslides; highways out of Kathmandu blocked by landslides; ≥ 148 deaths reported by 29 Sept 2024 (later official tolls higher — verify with NDRRMA/BIPAD) (F6). | Landslides frequently cut evacuation roads during floods. | Road closures as first-class input; landslide hazard stub for extensibility. |
| **Unequal communication infrastructure** | — (team to source from NTA MIS report: mobile & broadband penetration by province) (F8 to obtain) | Urban areas have 4G; remote areas may have 2G/no coverage; networks congest during events. | Multi-channel, SMS-first for WARNING+; PWA lightweight. |
| **Mobile-phone availability** | NTA publishes subscription statistics (F8 to obtain). **Caution:** subscription penetration >100 % ≠ individual ownership (multi-SIM). | Many households share phones; elderly/women/poor less likely to own smartphones. | Proxy subscriptions (FR-32); SMS; community intermediaries. |
| **Internet limitations** | (F8 to obtain) | Mobile data cost is a barrier for low-income users. | ≤ 300 KB initial load; offline cache; SMS needs no data. |
| **Local government structure** | Federal structure: 7 provinces, 77 districts, 753 local levels (6 metropolitan, 11 sub-metropolitan, 276 municipalities, 460 rural municipalities), 6,743 wards (F3). Local governments have disaster-management functions under the Local Government Operation Act 2074 (F7). NDRRMA established under DRRM Act 2074 (2017) (F7). | Capacity varies greatly between municipalities. | Area hierarchy configurable (province→district→municipality→ward); scoped roles; nested authority (C6). |
| **Language diversity** | 2021 census: 124 mother tongues; Nepali is mother tongue of 44.86 % and spoken as second language by a further ~46 %; 21 languages have >100,000 speakers (F9). | Maithili, Bhojpuri, Tharu, Tamang, Newar etc. are priority additional languages in Terai/valley pilots. | Nepali + English mandatory; language packs; icon-based messages; audio. |
| **Digital literacy** | (F10 to obtain: census 2021 literacy rate) | Low digital literacy among elderly and some rural groups. | One action per screen; icons; audio; volunteer mediation; usability tests with low-literacy participants. |
| **Road accessibility** | Sept 2024: highways out of Kathmandu blocked by landslides (F6). | OSM coverage of rural footpaths is incomplete. | Route confidence; footpath mode; manual closures; "no safe route" fallback. |
| **Vulnerable populations** | (F11 to obtain: census disability prevalence) | Elderly-headed households increase due to labour migration abroad. | Proxy subscriptions; assistance requests; accessible shelter filters; vulnerability index. |
| **Existing systems** | DHM flood forecasting & SMS alerts; NDRRMA's BIPAD portal; community-based flood EWS projects (F4, F7). | They will not be replaced; integration is via feeds/CAP. | SR-07 official precedence; CAP export; interop adapters. |

## 2. Adaptive Design: Core vs. Configurable Requirements

**Principle [D]:** *Safety invariants are core and non-configurable; context (geography, hazards, languages, channels, governance, thresholds) is configuration.* This keeps adaptability from eroding safety.

### 2.1 Core requirements (identical everywhere; cannot be disabled)

| Core requirement | IDs |
|---|---|
| Data validation and staleness detection | FR-06..FR-08, NFR-R1 |
| Data loss never lowers risk; confidence shown | SR-06, SR-08 |
| One active warning per area/hazard; no contradiction with official warnings | FR-28, SR-07 |
| Human approval required at least for the highest level (number of approvers configurable ≥ 1) | SR-02 (core), FR-20 (configurable count) |
| Cancellation always sends correction to same recipients | FR-25, SR-09 |
| Safe routing filter; shelters in hazard zones excluded | SR-03, SR-05 |
| Audit log | FR-59 |
| Security baseline (MFA, RBAC, TLS) and privacy baseline (minimisation, consent) | NFR-S1..S3, NFR-PR1..PR2 |
| Decision-support disclaimer | SR-10 |
| Exercise-mode labelling | SR-12 |

### 2.2 Configurable requirements

| Dimension | What is configured | Example: Bardiya (Terai, rural) | Example: Kathmandu (urban) | Example: another country |
|---|---|---|---|---|
| **Country** | Admin hierarchy names/levels, timezone, emergency numbers, legal disclaimers, official-warning source | Province–District–RM–Ward | Same | e.g. State–District–Block–Village |
| **Province/district/city** | Boundaries, scope of operators | Bardiya district | Kathmandu Metropolitan City | — |
| **Rural vs. urban** | Default routing mode (walk vs. vehicle), shelter types, coverage flags, volunteer channel | Walk; livestock shelters; volunteer relay | Walk/vehicle; buildings as vertical refuge | — |
| **Hazard types** | Enabled hazards, model plug-ins, thresholds, levels, templates | Flood | Flood + landslide (stub) | Cyclone, tsunami |
| **Languages** | Enabled language packs, default per area | ne, en, Tharu | ne, en, Newar | Local |
| **Communication tech** | Channels and fallbacks, SMS segment limits, siren endpoints | SMS-first, siren, volunteer | Push + SMS | Cell broadcast |
| **Infrastructure level** | Poll intervals, offline cache size, static fallback, max payload | Small payloads | Normal | — |
| **Government structure** | Roles, approval tiers, number of approvers per level, timeouts, auto-publish policies | Ward→RM→District | Ward→Metro→District | Per national law |
| **Population density** | Area unit granularity (ward vs. river reach), dispatch rate limits, shelter capacity planning | Reaches/wards | Wards/blocks | — |
| **Thresholds** | Per station, versioned, with provenance, two-person approval | — | — | — |

**Configuration safety [D]:** configuration is validated (e.g. watch < warning < danger; every area has monitoring or a "no monitoring" flag; templates complete), versioned, two-person approved, and can be tested by **replay** (FR-61) before activation.

## 3. Facts Register (sources)

| ID | Fact | Source (verify; prefer primary) | Status |
|---|---|---|---|
| F1 | Physiography (Terai to Himalaya); major river systems | Government of Nepal, Survey Department / DHM publications; any standard physical geography of Nepal | To cite primary |
| F2 | Monsoon (≈ June–Sept) delivers majority of annual rainfall | DHM climate publications (dhm.gov.np); World Bank Climate Change Knowledge Portal – Nepal | To cite primary |
| F3 | 7 provinces, 77 districts, 753 local levels (6/11/276/460), 6,743 wards | Ministry of Federal Affairs & General Administration; summarised in [Wards and electoral divisions of Nepal (Wikipedia)](https://en.wikipedia.org/wiki/Wards_and_electoral_divisions_of_Nepal); [Open Data Nepal – local bodies & wards per district](https://opendatanepal.com/dataset/total-number-of-local-bodies-and-wards-per-district-of-nepal/resource/8a52101b-4e22-435f-ba55-f2bd688799e5) | Checked via secondary sources |
| F4 | DHM hydrological network, real-time river levels with warning/danger levels, flood forecasting & SMS alerts | hydrology.gov.np; dhm.gov.np | To verify on site |
| F5 | 2008 Koshi breach; 2017 Terai floods; 2021 Melamchi flood | NDRRMA/BIPAD event records; post-disaster reports (e.g. ICIMOD, UN OCHA ReliefWeb) | To cite primary |
| F6 | Late-Sept 2024 floods & landslides: ≥ 148 deaths reported by 29 Sept, ≥ 34 in Kathmandu, highways blocked | [NPR, 29 Sept 2024](https://www.npr.org/2024/09/29/g-s1-25324/death-toll-in-nepal-flooding-reaches-at-least-100-dozens-still-missing) (AP reporting); final toll: BIPAD/NDRRMA | Checked (news); final figure to verify |
| F7 | DRRM Act 2074 (2017) establishes NDRRMA; Local Government Operation Act 2074 assigns DRM functions to local governments; BIPAD portal | Nepal Law Commission (lawcommission.gov.np); bipadportal.gov.np | To cite Act text |
| F8 | Mobile/internet subscription penetration | Nepal Telecommunications Authority MIS reports (nta.gov.np) | **To obtain** |
| F9 | 124 mother tongues; Nepali 44.86 % mother tongue, +46.2 % second language; 21 languages >100k speakers | NSO, NPHC 2021 *National Report on Caste/Ethnicity, Language & Religion*; summarised in [Languages of Nepal](https://en.wikipedia.org/wiki/Languages_of_Nepal), [NepJOL: Status of mother tongues in 2021 census](https://www.nepjol.info/index.php/jofns/article/view/71780), [Nepali Times – Decoding diversity](https://nepalitimes.com/decoding-diversity) | Checked via secondary sources |
| F10 | Literacy rate (census 2021) | NSO, NPHC 2021 National Report | **To obtain** |
| F11 | Disability prevalence (census 2021) | NSO, NPHC 2021 | **To obtain** |
| F12 | Devanagari SMS requires UCS-2 encoding (70 chars/segment, 67 when concatenated) | 3GPP TS 23.038 | General technical fact |
| F13 | CAP 1.2 is the OASIS/ITU-T X.1303 standard for public warnings | OASIS CAP 1.2 spec | General technical fact |
| F14 | WMO/UNDRR "Early Warnings for All" four pillars | wmo.int / undrr.org EW4All | To cite |
| F15 | Individual Privacy Act 2075 (2018) | Nepal Law Commission | To review sections |
