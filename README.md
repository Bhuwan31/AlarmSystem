# AlarmSystem — Adaptive Multi-Hazard Early Warning and Evacuation Support System (AMHEWS)

A flood early-warning and evacuation-support system with **live satellite data, river sensors and sirens**, run by humans through an approval workflow.

- **Global by design:** works for any country or region. Everything country-specific (languages, authorities, administrative levels, time zone, laws, emergency numbers) comes from a configurable *Deployment Profile*.
- **First deployment: Nepal.** The goal is adoption by the Government of Nepal. Nepal is a demanding testing ground: monsoon floods, mountains, landslides that cut roads, uneven connectivity and many languages.
- **First hazard:** river floods. Landslides and earthquakes can be added later as plug-ins.

> **Public warnings and sirens are activated only by authorized people.** The system detects risk and proposes warnings; authorized officials approve them. It does not predict floods with certainty, does not guarantee safety, and does not replace national or local authorities (in Nepal: DHM, NDRRMA, local government). Until the government signs off, the system runs in exercise or shadow mode only.

## Requirements documentation
- **[presentation/AMHEWS-Requirements-Engineering.pptx](presentation/AMHEWS-Requirements-Engineering.pptx)** — the full requirements specification as a 53-slide deck: stakeholders, architecture, live data and hardware, 75 functional and 42 non-functional requirements, safety, security, privacy, use cases, failure scenarios, conflicts, 4-week plan, launch roadmap, traceability and evaluation.
- [docs/](docs/README.md) — supporting analysis notes.

## Live data and hardware

| Input | Source | What it gives |
|---|---|---|
| Satellite rainfall | NASA GPM IMERG | Rainfall over each catchment every 30 min, a few hours' delay |
| Satellite flood extent | Copernicus Sentinel-1 radar | Flooded areas every few days, through cloud |
| Flood forecasts, weather | GloFAS, Open-Meteo | River discharge forecasts, rainfall forecasts |
| National river and rain stations | Department of Hydrology and Meteorology (DHM) | Country-wide live river levels; needs a data-sharing agreement |
| Own river-gauge nodes (1–3 in the semester) | ESP32 + ultrasonic/radar level sensor + rain gauge, solar + battery, GSM/LTE or LoRa, MQTT over TLS | Live river level at the pilot site; 24 h offline buffer |
| Siren node (1 pilot) | GSM relay controller with local manual button | Sounds only on an approved warning (signed command); weekly silent self-test |

## Stack
| Layer | Technology |
|---|---|
| Database / Auth / Realtime / Storage | Supabase (PostgreSQL + PostGIS) |
| Backend | Python 3.12, FastAPI, APScheduler, OSMnx + NetworkX (routing) |
| Devices | ESP32 firmware, MQTT broker (Mosquitto / EMQX) |
| Frontend | Next.js (App Router, TypeScript), MapLibre GL, next-intl (any language; Nepal: Nepali/English), PWA |
| Hosting | Vercel (frontend), Render / Fly.io (backend), Supabase cloud; government hosting at launch |

## Plan
**Semester (4 weeks), Phase 0:**
- Live satellite and weather data.
- 1–3 own gauges.
- A siren pilot in test mode.
- The full warning workflow, citizen app and authority dashboard.
- Exercise mode only.

**After the semester:**

| Phase | What happens |
|---|---|
| 1. Partnership | Meet DHM, NDRRMA and a pilot municipality; sign a data-sharing agreement; connect the DHM feed; security review; real SMS gateway |
| 2. Shadow pilot (one monsoon) | The system runs alongside the official process with no public alerts; lead time and false alarms are compared; operators are trained |
| 3. Government launch | Authorities operate it on government hosting; sirens and cell broadcast go live district by district, then nationally |

## Run it locally

Requirements: Docker Desktop. Live DHM, Open-Meteo and map data need internet access.

The database is **Supabase** (hosted PostgreSQL with PostGIS):

1. `cp .env.example .env`, then put your project's **Session pooler** connection string in `DATABASE_URL`
   (Supabase → Connect → Session pooler; port 5432, add `?sslmode=require`).
2. Create the tables once (this also blocks Supabase's public REST API from reading them):
   ```bash
   docker compose build backend
   docker compose run --rm --no-deps backend python -m app.migrate
   ```
3. `docker compose up -d --build`

Without internet or Supabase, leave `DATABASE_URL` empty and run a local PostGIS instead:
`docker compose --profile localdb up -d --build`.

- Dashboard: http://localhost:3000 (click the globe for the full-screen 3D map)
- API docs: http://localhost:8000/docs
- First data arrives within about a minute; risk assessment runs every 2 minutes.

Optional satellite sources: put `EARTHDATA_TOKEN` (NASA GPM IMERG) or `INSAT_INBOX_DIR` (MOSDAC downloads) in `.env`, then enable the source:

```bash
docker compose exec db psql -U amhews -d amhews -c "update data_sources set enabled = true where code = 'gpm_imerg'"
```

### Try the warning workflow and a simulated gauge

```bash
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest
.venv/Scripts/python scripts/dev_token.py anjali approver --mfa
.venv/Scripts/python scripts/simulate_device.py gauge-001 --start 3.5 --rise 1.2
```

Register devices with `POST /api/v1/devices` (admin token), approve warnings with `POST /api/v1/warnings/{id}/approve`. CRITICAL needs two different approvers with MFA. Simulated readings only count while `exercise_mode` is on.

## What is built

| Part | Status |
|---|---|
| DHM live river (316) and rain (513) stations | Working, live |
| Open-Meteo weather grid (Nepal 0.5°, world 15°) | Working, live |
| NASA GPM IMERG satellite rain | Built, needs Earthdata token, untested with real data |
| INSAT-3D/3DR/3DS (MOSDAC) | Built, needs MOSDAC account + files, untested with real data |
| Validation, staleness, risk rules R1–R10, warning proposals | Working, unit-tested |
| Warning approval (1 / 2 approvers, MFA for CRITICAL), cancel, audit log (hash-chained, append-only) | Working, tested end to end |
| MQTT device gateway, device registry, signed siren commands | Working, tested with a simulated gauge and a live MQTT command |
| ESP32 gauge and siren firmware | Written, not yet compiled or bench-tested |
| Dashboard: light spinning globe, full-screen 3D map, live tables | Working |
| Map layers with details and filters: temperature, heatwave risk, humidity, rain forecast, cloud, animated wind flow, wind arrows, world rivers, Nepal rivers incl. cross-border, river and rain gauges, satellite rain, 3D terrain, border | Working |
| Click any place: fly there in 3D terrain + current temperature, humidity, pressure, air flow from surface to jet stream, 24 h outlook, heat status | Working |
| Operator login with two-factor, user management, policies, audit viewer | Working |
| Shelters, citizen "my area" page (Nepali / English) | Working |
| AI analyst (reviews all inputs every 30 min, posts findings on the Warnings page) and AI assistant chat | Built and tested against mock APIs; needs a free `GEMINI_API_KEY` or an `ANTHROPIC_API_KEY` |
| Weather card (hourly temperature / rain / wind, 8 days, any date since 1940) on the 3D map and the 30-day page; 30-day weather for any place + 59 world cities | Working |
| Machine learning: logistic regression, random forest, SVM, rain-only flood SVM, linear regression, XGBoost, LSTM, k-means, Isolation Forest, DQN agent (advisory) | Trained on 2019–2024 GloFAS + ERA5 data for 24 stations, scored on held-out 2023–2024 |
| AI visual disaster detection | Residents photograph or upload floods / landslides; a from-scratch CNN + DQN agent + safety policy propose an incident with a suggested message; an approver sends it to subscribers within 1–10 km. Admins can message a district, city, province, the whole country or a map radius, now or scheduled |
| Not built yet | Turn-by-turn safe routing (the public page links to OpenStreetMap directions); SMS / e-mail / push need provider keys (in-app alerts work out of the box) |

## Pages

| Page | Who | What it does |
|---|---|---|
| `/` Dashboard | everyone | Spinning globe, national conditions, river risk counts, warnings, heaviest rain, source health |
| `/map` 3D map | everyone | Full-screen globe: 14 layers with details and filters, click any place for 3D terrain + current weather |
| `/warnings` | approver to act | Active, proposed and past warnings; approve / reject / cancel; operators issue manual warnings |
| `/visual` Report a photo | signed-in residents | AI Visual Disaster Detection: take a photo (device clock + GPS) or upload one (EXIF time + GPS), confirm the place on a map, see the AI result |
| `/alerts` My alerts | signed-in residents | Alert inbox with acknowledgement; consent, home location, district and channels; opt-out |
| `/incidents` Visual incidents | operator to view, approver to act | Map of photo reports and incidents, review photos and evidence, edit the suggested message, choose 1/3/5/10 km, approve & send, escalate, close with all-clear, delivery records |
| `/broadcast` Area messages | approver | Message a district, city, province, the whole country or a map radius, now or at a set time |
| `/climate` 30-day weather | everyone | Any place in the world: weather card for any date, last 30 / next 16 days vs last year, world cities overview |
| `/ml` ML models | everyone | 30-day warning outlook per river, every model's call for today, evaluation on held-out years, river groups, faulty sensor readings |
| `/assistant` | signed-in staff | Ask the AI about conditions in any place; it checks live gauges, devices, satellite and weather data |
| `/rivers`, `/rain` | everyone | All live gauges: search, basin and risk filters, sorting |
| `/stations/[id]` | everyone | One gauge: level chart with watch / warning / danger lines, risk history and reasons, warnings, data problems |
| `/weather` | everyone | Conditions and heat status in main towns; hottest, coldest, windiest and wettest areas |
| `/shelters` | operator to edit | Shelter list with occupancy; add shelters; update status and occupancy |
| `/devices` | admin to register | Own gauges and sirens: status, battery, signal; siren self-test; register a device (secrets shown once) |
| `/sources` | everyone | Freshness of each data source and open data-quality events |
| `/audit` | admin | Hash-chained audit log with one-click tamper check |
| `/admin` | admin | Users and roles, safety policies (exercise mode, thresholds), two-factor set-up |
| `/login` | staff, residents | Email + password (+ authenticator code when two-factor is on); residents can create an account |
| `/public` | citizens | Nepali / English: flood risk near you, nearest open shelters, emergency numbers — no account needed |

The first admin account comes from `ADMIN_EMAIL` / `ADMIN_PASSWORD` in `.env` (only when no users exist). Change the password and set up two-factor after the first sign-in.

## Machine learning

All models are **advisory**: they are shown on `/ml` and never issue, approve or change a warning.

| Task | Models | Predicts |
|---|---|---|
| Classification | Logistic regression, random forest, SVM (RBF) | Flood level (NORMAL / WATCH / WARNING / CRITICAL) over the next 3 days |
| Binary classification | SVM on rain features only | Will the river reach WARNING in 3 days? (for places without a gauge) |
| Regression | Linear regression, XGBoost, LSTM | River flow 1 day and 3 days ahead |
| Clustering | k-means (k by silhouette) + PCA view | Groups of stations with similar rain and flow regimes |
| Anomaly detection | Isolation Forest | Suspicious readings from the real DHM gauges in our database |
| Reinforcement learning | Deep Q-Network (Double DQN) | Which warning level to show today, rewarded for early, correct warnings and penalised for misses, false alarms and flicker |
| 30-day outlook | the DQN agent, stepped day by day through the 51 GloFAS ensemble futures | Chance of each warning level on each of the next 30 days |

**Data.** Daily river discharge from GloFAS v4 (Copernicus) and ERA5 rainfall, 2019–2024, at 24 river stations from Koshi to
Mahakali (each snapped to the main river cell). Training years 2019–2022, test years 2023–2024 — a time split, so the scores
are for years the models never saw. Flood levels are each station's own flow percentiles (P90 / P97 / P99.5). GloFAS is a
model of river flow driven by real weather, not a gauge record; retraining on DHM's historical gauge data is the next step.
The Isolation Forest uses our own gauge readings.

**Inputs** (25 per day): the river's own flow and its changes; rain over the last 1 / 3 / 7 / 30 days; forecast rain for the
next 1 / 3 / 7 days and how uncertain that forecast is; combined flow of the model stations upstream (e.g. Arun, Tamor,
Sunkoshi and Tamakoshi for the Sapta Koshi); soil moisture of the top metre (ERA5); temperature, warmth and snowfall at a
headwater point ~40 km north of the station (snow and glacier melt); time of year; today's level. There are no archived
forecasts to learn the uncertainty from, so in training the forecast is the real rain times random noise of a known size,
and that size is the uncertainty input; live, it is the spread of the 51-member ECMWF rain ensemble.

**Retrain** (downloads data once into `backend/ml_data/`, then about 2½ hours on a laptop CPU, mostly the DQN):

```
docker compose --profile ml run --rm ml-train
docker compose up -d --build backend
```

Training runs in its own image with PyTorch; the backend runs the exported models with numpy, scikit-learn and XGBoost.
Results are in `backend/app/ml/artifacts/metrics.json`.

## Alerts to residents' phones

Approved warnings (and their all-clears), approved photo incidents and area messages go to every subscribed resident in
the area: in the app's inbox, and on their phone through the free **ntfy** app (Android / iOS). No hosting or SMS
account is needed, so it also works when the system runs on one computer.

1. On the phone, install **ntfy** and subscribe to a private topic name.
2. In the app, **My alerts**: set your location, tick **Phone notification (free ntfy app)**, enter the same topic,
   save, then **Send a test to my phone**.
3. `.env` needs `NOTIFY_EXTERNAL_ENABLED=true` (with `false`, sending is only simulated and recorded).

CRITICAL alerts use ntfy's highest priority. Messages pass through the public server https://ntfy.sh unless
`NTFY_SERVER` points to your own. SMS (`TWILIO_*`), e-mail (`SMTP_*`) and web push (`VAPID_*`) work the same way once
their providers are configured.

## AI visual disaster detection

A resident photographs or uploads a scene; the system records when (camera clock or EXIF, with timezone) and where
(GPS or EXIF, else picked on a map), then:

1. **Image model**: a custom CNN trained from random weights; 9 categories, calibrated confidence.
2. **Evidence**: rain gauges near the photo at that time, the weather model, the nearest river gauge, active
   warnings and other reports. Missing data is never treated as confirmation.
3. **Decision agent**: a DQN trained in a simulated incident environment. It advises NO_ALERT / MONITOR / WATCH /
   WARNING / CRITICAL / ask for more evidence.
4. **Safety policy**: explicit rules, for example a photo alone is capped at WARNING, and CRITICAL needs corroboration
   and a second report. Stale, duplicate and future-dated photos are blocked.
5. **Incident + suggested message**: an approver reviews it, picks the radius (1/3/5/10 km) and presses Send.
   Consenting subscribers inside the radius get it in-app, plus push / SMS / e-mail if configured. Alerts are
   deduplicated and rate-limited, with delivery and acknowledgement tracking.

The shipped models are trained on **synthetic** scenes only (no labelled photo dataset is bundled). They are marked
*not validated*, and the agent runs in advisory mode until retrained on real photos. Full documentation: training,
dataset preparation, API, database, environment variables and deployment are in
[docs/visual-disaster-detection.md](docs/visual-disaster-detection.md). Evaluation:
[docs/vision-model-report.md](docs/vision-model-report.md).

## AI analyst and assistant

Both work with **Google Gemini** (free tier) or **Claude** (paid, strongest), or any OpenAI-compatible API, using the same read-only tools over the live database (gauges, rain, satellite rain, weather grid, devices, data quality, warnings, place lookup).

- **Analyst:** runs every `AI_INTERVAL_S` seconds (default 30 min on Claude, 3 h on Gemini's free tier) and on demand ("Run now" on the Warnings page, operator). It records findings with severity, confidence, evidence and a suggested action, plus an overall level and data gaps.
- **Assistant:** `/assistant` page. Ask in English or Nepali about any place; it looks the place up and checks nearby gauges and weather. Limited to `AI_CHAT_PER_HOUR` questions per user.
- **Drafted messages for risk areas:** for every WATCH, WARNING or CRITICAL finding about a real hazard (not a data gap), the analyst drafts a message for residents of that area (5 / 10 / 15 km around it by level). Approvers hear an alert tone and see a banner on every page; on **Area messages** they edit the level, radius, title and text, then **Send now**, **Schedule** or **Reject**. Rejected drafts stay in the History (who, when, why) and can still be edited and sent later; sent messages show the approver, time, recipients and the AI's original text if it was edited. A repeat finding updates the waiting draft instead of adding another. `AI_PROPOSE_MESSAGES=false` turns drafting off. Browsers only play sound after the approver has clicked the page once; the banner has a mute button.
- **Busy model:** if the main model is overloaded, the run restarts on a lighter one (`AI_FALLBACK_MODEL`, default `gemini-flash-lite-latest` for Gemini).
- **Advisory only.** The AI cannot issue, approve or cancel warnings or trigger sirens, and nothing it drafts reaches anyone until an approver presses Send. An operator can turn a finding into a normal proposal, which then needs the usual human approval.

To switch it on, add **one** key to `.env` and run `docker compose up -d backend`:

| Key | Cost | Get it |
|---|---|---|
| `GEMINI_API_KEY` | Free tier (daily request limits; Google may use free-tier data to improve its models) | https://aistudio.google.com/apikey |
| `ANTHROPIC_API_KEY` | Pay as you go; used first when set | https://console.anthropic.com |

Other OpenAI-compatible services (Groq, OpenRouter, a local Ollama): set `AI_PROVIDER=openai_compat`, `AI_BASE_URL`, `AI_API_KEY` and `AI_MODEL`. To control spend or free-tier usage, raise `AI_INTERVAL_S`, lower `AI_EFFORT`, or set `AI_ENABLED=false` (the assistant and "Run now" keep working). Offline checks (no key, no credits): copy `backend/tests/ai_mock_check.py` (Claude) or `ai_gemini_mock_check.py` (Gemini path) into the container with `docker compose cp` and run them with `docker compose exec backend python /app/<file>`.

## Map data credits
Open-Meteo (CC BY 4.0) · DHM Nepal · © OpenStreetMap contributors (ODbL, Nepal rivers via `scripts/build_rivers.py`) · Natural Earth (world rivers, borders) · OpenFreeMap basemap · AWS Terrain Tiles (elevation)

## Repository layout
```
backend/     FastAPI app (adapters, processing, risk, warnings, devices, API) + tests + scripts
firmware/    ESP32 gauge and siren node code
frontend/    Next.js operations dashboard with 3D globe
supabase/    migrations (schema, RLS) and seed data
docs/        supporting analysis
presentation/ requirements specification deck
```
