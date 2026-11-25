# AI Visual Disaster Detection

People photograph or upload what they see. A custom CNN reads the photo, a decision agent (DQN) advises on the
warning level, and an independent safety policy decides what may be **proposed**. A person with the approver role
reviews every incident and its suggested message before anything is sent to subscribers in the affected area.
Admins can also send their own messages to a district, city, province, the whole country or a map radius, now or at
a set time.

> **Status of the models.** The repository has no labelled photo dataset, so the shipped models are trained on
> **procedurally generated synthetic scenes** (`app/vision/synth.py`). The pipeline, metrics and integration are real,
> but accuracy on real photographs is **unknown**. Both models are therefore recorded as `validated_for_alerts = false`,
> and the agent runs in advisory (shadow) mode. Retrain on real photos (see *Training with a real dataset*) before relying
> on the detections. Evaluation numbers are in [vision-model-report.md](vision-model-report.md).

## 1. How it fits the existing system

| Existing part | Reused for |
|---|---|
| FastAPI app, `users` table, JWT roles (viewer < operator < approver < admin), TOTP MFA | Sign-in, authorisation; residents self-register as *viewer* |
| Warning approval workflow (`warnings` API) | Same principle: machines propose, approvers decide; CRITICAL needs an MFA session |
| Hash-chained `audit_log` | Every submission, analysis, proposal, approval, level change, send, close and opt-out |
| DHM rain gauges (`observations`), Open-Meteo grid (`weather_grid`), river `risk_assessments`, ACTIVE `warnings` | Independent evidence around the photo's place and time |
| `deployment_profile.policies.exercise_mode` | Messages are labelled EXERCISE while exercise mode is on |
| PostGIS | Radius queries (`ST_DWithin` on geography) |
| numpy re-implementations of trained nets (`app/ml/nets.py`) | Live inference without PyTorch in the API image |

New: `app/vision/*`, `app/api/visual.py`, `app/geo_nepal.py`, migration `0005_visual_disaster.sql`, four frontend
pages (`/visual`, `/alerts`, `/incidents`, `/broadcast`), header alert bell and review banner, resident sign-up.

## 2. Pipeline

```
photo (camera or upload)
  │ POST /observations      validate type/size/pixels · EXIF time (+offset) and GPS · sha256 + perceptual hash (duplicates)
  │                         · private storage · EXIF-free preview for reviewers
  │ user confirms / corrects the location on the map
  │ POST /analyze  ─────────▶ background task
  │                            1. CNN → 9 class probabilities (temperature-calibrated) + 160-d visual features
  │                            2. evidence: rain gauges ±15 km in [t−3 h, t+1 h] (measured), weather model (modelled),
  │                               nearest river gauge risk, ACTIVE warnings, other reports within 2 km / 6 h
  │                            3. agent state (50 values) → DQN → advised action
  │                            4. safety policy → level, risk, eligibility, suggested radius, reasons
  │                            5. save ai_predictions; if eligible → new or grouped disaster_incident (PROPOSED)
  │                               with a suggested message
  ▼
approver reviews (/incidents): photos, analysis, evidence, message, radius 1/3/5/10 km with subscriber counts
  │ POST /incidents/{id}/approve-send
  ▼
subscribers with consent whose saved location is inside the radius → in-app (+ push / SMS / e-mail if configured)
  dedup per incident × recipient × channel × level · cooldown · daily limit · delivery + acknowledgement records
```

### Image categories

normal · heavy_rain · urban_flooding · river_flooding · flash_flooding · road_waterlogging · rising_water · landslide · uncertain

### CNN (`app/vision/cnn.py`)

Trained from random (He) initialisation: no pretrained backbone, no YOLO or SAM.

`3×3 conv s2 (24) → [conv-BN-ReLU ×2, max-pool] × 3 (48, 96, 160) → global average pool (160-d features) → dropout → linear (9)`.

- **Size and input:** about 0.5 M parameters. Input resolution is set with `--img-size`, a multiple of 16; the default is 128.
- **Preprocessing:** orientation from EXIF, centre square crop, resize, then per-channel normalisation.
- **Augmentation:** random resized crop, flip, ±5° rotation, brightness, contrast and saturation jitter, darkening (night), fog, blur and sensor noise.
- **Class imbalance:** handled with class-balanced sampling plus label smoothing.
- **Confidence:** a softmax with a temperature fitted on the validation set, so a confidence of 0.8 means about 80 % correct.
- **Checkpoints:** saved every epoch, keeping the best by validation macro-F1, with early stopping.
- **Export:** BatchNorm is folded into the convolutions and the weights are run by `cnn_np.py` (numpy). A test checks it matches PyTorch.

### Decision agent (`app/vision/env.py`, `train_all.py`)

- **Actions:** NO_ALERT, MONITOR, ISSUE_WATCH, ISSUE_WARNING, ISSUE_CRITICAL_ALERT, REQUEST_ADDITIONAL_EVIDENCE.
- **State (50 values):**
  - From the photo: CNN class probabilities, confidence and entropy, plus 16 principal components of the CNN features.
  - Rain: gauge rain for 1 h and 24 h, and model rain for 24 h, each with a separate "available" flag (missing ≠ dry).
  - Rivers and warnings: river gauge level, and the level of any official warning.
  - History: reports nearby, the prior level nearby, and the evidence count.
  - Time: hour of day and season.
  - Reliability: whether the location was entered by hand, GPS accuracy, and image age.
  - Its own state: the current alert level and the steps since it last changed.

**Why a simulator.** A single photo is not a sequence of decisions. The agent learns in simulated incidents of 12 steps of 30 min each:

- **Scenarios:**
  - quiet: no hazard
  - nuisance: waterlogging that drains
  - rising urban flood
  - river flood
  - flash flood
  - landslide
  - stale: an old flood photo uploaded today
- **True level:** a hidden true level evolves through each scenario.
- **Photos:** each step brings a new photo with probability 0.6, or always after REQUEST_ADDITIONAL_EVIDENCE. 12 % of photos are wrong or unrelated.
- **Photo features:** real CNN outputs on images of the matching class from the split being used. Training uses augmented train images; validation and test episodes use only validation or test images.
- **Readings:** gauges, model rain and river levels are noisy and sometimes missing. Official warnings arrive 2 steps late.

**Reward per step:**

| Situation | Reward |
|---|---|
| Matches the true level | +0.3 (+0.05 when the true level is 0) |
| Missed danger | −0.5 × level gap (×1.5 for CRITICAL) |
| Public alert while nothing is happening | −0.4 × level |
| Re-raising to a level already issued for the same incident (duplicate notification) | −0.25 |
| Any level change (flicker) | −0.08 |
| Asking for more evidence | −0.05, plus −0.15 more while danger is present |
| Reaching WARNING up to 3 steps before the true level does | +0.6, once |

**Algorithm:** Double DQN, 50 → 128 → 128 → 6:

- experience replay of 60 k transitions and a target network synced every 1 000 steps
- ε-greedy exploration from 1 → 0.05 over 60 % of the episodes
- Huber Bellman loss, γ = 0.95
- fixed seeds and the best checkpoint by validation reward

It is compared with a *photo rule* baseline, which takes the level straight from the photo class.

### Safety policy (`app/vision/policy.py`)

Independent, deterministic and unit-tested. The models cannot bypass it.

- **Rain evidence:** a photo never confirms *current* rain, so `heavy_rain` is capped at WATCH. Missing weather data is reported as *unavailable*, never treated as confirmation.
- **Photo alone:** without corroboration (gauges, river gauge at WARNING+, or an official warning) the level is capped at **WARNING**.
- **CRITICAL** needs corroboration **and** a second report or an official warning.
- **Weather corroboration:**
  - *confirmed*: gauges measured ≥ 25 mm in 24 h or ≥ 7 mm in 1 h within 15 km.
  - *contradicted*: gauges measured < 5 mm and < 1 mm. This caps rain-driven classes at WATCH.
  - *supported_by_model*: no gauges, and the weather model shows heavy rain. This is **not** corroboration.
- **Blocked or capped photos:**
  - **Stale** (> 6 h old), **dated in the future** (> 10 min), or a **duplicate**: no alert.
  - **Location entered by hand or imprecise** (> 1 km), or an **upload without a capture time**: capped at WATCH unless corroborated.
- **Confidence:** below 0.60, a hazard class is only MONITOR. `uncertain` asks for more evidence.
- **Agent:** an agent that has not been validated is advisory only. A validated agent may lower the level by one, or ask for more evidence. It may never raise the level.
- **Suggested radius:** depends on type and level, for example road waterlogging 1 km, urban flooding 1/3/5 km and flash flooding 5/5/10 km. It widens near a gauged river or when an official warning is active. The approver chooses the final radius from 1, 3, 5 or 10 km.
- **Human review:** every alert is proposed to a person. Nothing is sent automatically.

## 3. API (`/api/v1/visual-disaster`)

The full OpenAPI schema is at `http://localhost:8000/docs`. Roles: *any* = any signed-in account.

| Method & path | Role | Purpose |
|---|---|---|
| `POST /observations` (multipart) | any | `file`, `image_source` = camera\|upload, `capture_timestamp` (camera, ISO-8601 with offset), `client_tz_offset_min`, `latitude`, `longitude`, `gps_accuracy_m`, `location_source` = device_gps\|manual. Returns the observation with the extracted EXIF time/GPS, `duplicate_of` and `suggested_location`. Limits: 10 MB, 20 photos per user per hour, JPEG/PNG/WebP only, at most 40 MP. |
| `POST /analyze` | owner / operator | `{observation_id, latitude?, longitude?, location_source?, gps_accuracy_m?}` confirms or corrects the location and queues the analysis (202). |
| `GET /observations[?mine&status&limit]` | any (own) / operator (all) | Observations with their latest analysis. |
| `GET /observations/{id}` | owner / operator | One observation; poll this for the analysis result. |
| `GET /observations/{id}/image` | owner / operator | The reviewer copy: a re-encoded JPEG without EXIF/GPS. The original file is never served. |
| `GET /incidents[?status]` | operator | Incidents with subscriber counts and notification counts. |
| `GET /incidents/active` | public | Approved ACTIVE incidents (no photos, no reporter data). |
| `GET /incidents/{id}` | operator | Photos, analyses, subscribers per radius option, delivery summary, history, channel configuration. |
| `POST /incidents/{id}/verify` | approver | `{decision: confirm\|reject, note}`. |
| `POST /incidents/{id}/approve-send` | approver (CRITICAL: MFA) | `{level, radius_km ∈ 1/3/5/10, title, body, channels[]}` approves and notifies. `{distance}` in the body is replaced for each recipient. |
| `POST /incidents/{id}/level` | approver | `{level, note}` escalates or downgrades. |
| `POST /incidents/{id}/close` | approver | `{note, send_all_clear}`. |
| `GET /incidents/{id}/notifications` | approver | Per-recipient delivery and acknowledgement records. |
| `GET /alerts` · `GET /alerts/unread` · `POST /alerts/{id}/ack` · `POST /alerts/read-all` | any | My inbox. |
| `GET /alerts/all` | approver | Delivery totals per incident or broadcast and channel. |
| `GET` / `PUT` / `DELETE /subscription` | any | Consent, home location, district/province, channels, phone, e-mail. DELETE opts out and erases the location and phone number. |
| `POST /broadcasts/preview` · `POST /broadcasts` · `GET /broadcasts` · `POST /broadcasts/{id}/cancel` | approver (CRITICAL: MFA) | Area messages. `target_type` = country\|province\|district\|city\|point, with `target_value`, `latitude`/`longitude`/`radius_km`, `level` = INFO\|WATCH\|WARNING\|CRITICAL, `title`, `message`, `send_at`, `valid_until`. |
| `GET /geo/areas` · `GET /geo/locate` | public | 7 provinces, 77 districts and 22 cities; nearest district to a point. |
| `GET /channels` · `GET /push/public-key` · `POST /push/subscribe` | public / any | Channel availability; Web Push registration. |
| `GET /model/status` | public | Model versions, validation flags, agent mode, dataset version, test metrics and training runs. |
| `POST /api/v1/auth/register` | public | Resident self-registration (viewer role), limited to 20 per IP per hour. |

Example analysis (inside `GET /observations/{id}` → `analysis`):

```json
{ "classification": "urban_flooding", "visual_confidence": 0.93, "risk_level": "HIGH", "alert_level": "WARNING",
  "recommended_action": "ISSUE_WARNING", "agent_action": "ISSUE_WARNING",
  "location": {"latitude": 27.695, "longitude": 85.307}, "analysis_timestamp": "2026-07-14T10:12:03+00:00",
  "weather_correlation": "unavailable", "alert_eligible": true,
  "reasons": ["Not yet corroborated by rain gauges, river gauges or an official warning: capped at WARNING.", "..."] }
```

## 4. Database (migration `0005_visual_disaster.sql`, additive only)

| Table | Holds |
|---|---|
| `visual_observations` | One row per photo: who submitted it, where it is stored, hashes, capture and upload time, location and accuracy, sources, extracted EXIF, duplicate link, processing status and incident. |
| `ai_predictions` | Class, probabilities, confidence, the agent's action and Q-values, the policy's action, risk, alert level, eligibility, weather correlation, evidence, reasons and model version. |
| `disaster_incidents` | Type, status, location, district and province, radius (affected and suggested), level (current and suggested), report count, proposed and sent message, verification, approval, closing, exercise flag. |
| `emergency_notifications` | One row per recipient × channel: channel, status, level, text, distance, error, sent / read / acknowledged times. Unique indexes stop duplicates. |
| `area_broadcasts` | Admin messages: target, level, text, send time, valid-until, status and recipients. |
| `alert_subscriptions` | Consent, home location, district, province, channels and contacts. |
| `push_subscriptions` | Web Push endpoints. |
| `model_training_runs` | Version, dataset version, parameters, validation and test metrics, checkpoint, validated flag. |

Apply to an existing database:

```bash
MSYS_NO_PATHCONV=1 docker compose exec -T db psql -U amhews -d amhews -f /docker-entrypoint-initdb.d/0005_visual_disaster.sql
```

A fresh database applies it automatically.

## 5. Training

Synthetic data, the default; this took about 80 min on a laptop CPU (about 40 min for the image model, about 40 min for the agent):

```bash
docker compose --profile ml run --rm ml-train python -m app.vision.train_all
```

It writes:

- `backend/app/vision/artifacts/` (`cnn.npz`, `dqn.npz`, `vision_meta.json`, `vision_metrics.json`)
- `backend/app/vision/artifacts/vision-model-report.md` (copy it to `docs/`; the training container only mounts `backend/`)
- one `model_training_runs` row per model
- checkpoints in `backend/ml_data/vision/checkpoints/<stamp>/`

Then rebuild the API image so it includes the new artifacts:

```bash
docker compose up -d --build backend
```

Options:

- `--img-size`, `--epochs`, `--batch`, `--lr`, `--patience`
- `--dqn-episodes`
- `--seed` (reproducible runs)
- `--dataset <prepared folder>`

### Training with a real dataset

1. **Collect and label photos.** Put them under one folder with a `manifest.csv` (columns `path,label,incident_id,location_id,condition,source,license`), or use one sub-folder per class. Every photo needs its **source and licence**. Use `incident_id` for shots of the same event and `location_id` for the place, so near-identical shots never cross splits.
2. **Prepare a versioned split.** The test set holds out whole locations and the validation set holds out whole incidents. Exact duplicates are dropped.

   ```bash
   docker compose --profile ml run --rm ml-train python -m app.vision.dataset --name real --source /app/ml_data/vision/raw
   ```

3. **Train on the prepared folder:**

   ```bash
   docker compose --profile ml run --rm ml-train python -m app.vision.train_all --dataset ml_data/vision/datasets/real-<hash>
   ```

Mixing real and synthetic sources is allowed by passing more than one `--source`.

**Validation gate.** A model is marked `validated_for_alerts` only if it was trained on non-synthetic data and its test results reach macro-F1 ≥ 0.80 and flood/landslide recall ≥ 0.85. The agent additionally must not miss more events or raise more false alarms than the photo rule. Even then, every alert still needs human approval.

Public photo collections exist for flooding and landslides. Check each one's licence before use. They are not bundled here because downloading third-party datasets needs your decision.

## 6. Notifications

| Channel | Needs | Without it |
|---|---|---|
| In-app inbox (+ a browser notification while the app is open) | nothing | always on |
| E-mail | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS` | recorded as `skipped_unconfigured` |
| SMS | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM` (Twilio REST). For a local SMS gateway, add a sender in `notify._send_sms`. | `skipped_unconfigured` |
| Web Push | `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`, plus `pip install pywebpush` in the backend image and a service worker in the frontend | `skipped_unconfigured` |

External channels are **simulated** (recorded as `simulated`, nothing sent) until `NOTIFY_EXTERNAL_ENABLED=true`. This lets the whole flow be tested with simulated users first.

Deduplication and limits:

- **One message per recipient, channel and level for each incident.** This is enforced by the database.
- **Cooldown:** a repeat at the same or a lower level is suppressed. Only an escalation goes out again. Set with `NOTIFY_COOLDOWN_MIN`.
- **Daily limit:** `NOTIFY_MAX_PER_DAY` per recipient. CRITICAL messages are never rate-limited.
- **All-clear:** a closing all-clear is sent only to people who were warned.

## 7. Environment variables (new)

| Variable | Default | Meaning |
|---|---|---|
| `VISUAL_STORAGE_DIR` | `/data/visual` | Private photo store (the `visual_data` docker volume). |
| `VISUAL_MAX_UPLOAD_MB` | 10 | Maximum upload size. |
| `VISUAL_UPLOADS_PER_HOUR` | 20 | Photos per user per hour. |
| `VISUAL_GROUP_KM` / `VISUAL_GROUP_HOURS` | 2 / 6 | Reports this close in space and time join one incident. |
| `ALLOW_SELF_REGISTRATION` | true | Residents can create viewer accounts. |
| `NOTIFY_EXTERNAL_ENABLED` | false | Actually send SMS, e-mail and push (otherwise they are simulated). |
| `NOTIFY_MAX_PER_DAY` / `NOTIFY_COOLDOWN_MIN` | 10 / 30 | Rate limit and cooldown. |
| `SMTP_*`, `TWILIO_*`, `VAPID_*` | empty | Channel providers (see above). |

## 8. Deployment

```bash
MSYS_NO_PATHCONV=1 docker compose exec -T db psql -U amhews -d amhews -f /docker-entrypoint-initdb.d/0005_visual_disaster.sql
docker compose --profile ml run --rm ml-train python -m app.vision.train_all
docker compose up -d --build backend frontend
```

Run these in order:

1. Apply the migration (only for an existing database; a new one applies it automatically).
2. Train, or copy trained artifacts into `backend/app/vision/artifacts/`.
3. Rebuild the backend and frontend.

Photos live in the `visual_data` volume, owned by the non-root API user. Back it up with the database.

The browser camera needs a **secure context**: `localhost`, or HTTPS in production.

## 9. Tests

The `docker compose --profile ml run ...` commands in this section use the `ml-train` image, which has PyTorch and mounts `./backend`.

- **Unit and integration** (`backend/tests/test_visual.py`):
  - **Uploads:** image validation, EXIF time with and without a timezone, EXIF GPS and accuracy, the preview has no EXIF, perceptual duplicates, preprocessing.
  - **Models:** numpy CNN and agent equal PyTorch; the state vector marks missing weather as unavailable; simulator rewards and episodes; model unavailable.
  - **Rules and geography:** every safety-policy rule, the radius logic, weather correlation, time checks, the gazetteer.
  - **Notifications:** message text, channel choice, distribution with dedup and simulated / unconfigured channels, cooldown and the daily limit.
  - **Access:** authentication and roles on the endpoints, including the MFA requirement for CRITICAL.

  ```bash
  docker compose --profile ml run --rm ml-train sh -c "pip install -q pytest && python -m pytest -q tests"
  ```

- **End-to-end** (`backend/tests/e2e_visual.py`): runs against the live stack with simulated users at known distances and deletes them afterwards. It covers:
  - EXIF upload and camera upload, then CNN → agent → policy → incident
  - duplicate detection, and grouping a second report into the same incident
  - nothing sent before approval
  - approve & send at 3 km: only consenting residents inside the radius are notified
  - dedup on a re-send, CRITICAL refused without MFA, then escalation
  - inbox and acknowledgement
  - a district broadcast and a scheduled point broadcast
  - close with all-clear, opt-out, and the audit trail

  ```bash
  docker compose --profile ml run --rm ml-train python -m tests.e2e_visual
  ```

- **Frontend:** `npx tsc --noEmit` and `npx eslint src`. There is no automated browser test of camera capture yet. The camera needs a real device, or Playwright with a fake media stream.

## 10. Known limits and next steps

- **Real photos:** accuracy on real photos is unknown until the models are trained and validated on a real, licensed dataset.
- **District membership:** it is what the resident chose. District polygons are not loaded yet; add official boundaries to target exact borders.
- **Device clock:** camera capture time comes from the device clock, which a user can change. The capture-time and age checks limit the damage but cannot prove the time.
- **Push:** Web Push needs VAPID keys, `pywebpush` and a service worker. Until then, browser notifications only work while the app is open.
- **Photo files:** they are not yet pruned automatically. Add a retention job that matches your data-protection policy.
