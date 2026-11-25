# Visual model evaluation report

Generated 2026-11-25T01:29:29+00:00 by `python -m app.vision.train_all`. Dataset **synthetic-5a6b33220b** (3950 images).

> **Synthetic data only.** These numbers measure the pipeline on procedurally generated scenes. They say nothing about accuracy on real photographs. Both models are therefore recorded as *not validated for alerts*, and the decision agent runs in advisory (shadow) mode. Retrain with a real, labelled dataset (see docs/visual-disaster-detection.md) before relying on them.

## Image model (CNN, trained from random weights)

DisasterCNN 24-48-96-160 (from scratch), 527,521 parameters, input 128 px, best epoch 19, temperature 0.5.

| Split | Images | Accuracy | Macro-F1 | Flood/landslide recall | Flood/landslide precision | Calibration error (ECE) |
|---|---|---|---|---|---|---|
| Validation (held-out incidents) | 617 | 1.0 | 1.0 | 1.0 | 1.0 | 0.005 |
| Test (held-out locations) | 529 | 0.998 | 0.998 | 1.0 | 1.0 | 0.007 |

### Per class (test)

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| normal | 1.0 | 1.0 | 1.0 | 131 |
| heavy_rain | 1.0 | 1.0 | 1.0 | 42 |
| urban_flooding | 1.0 | 1.0 | 1.0 | 71 |
| river_flooding | 1.0 | 0.983 | 0.991 | 59 |
| flash_flooding | 1.0 | 1.0 | 1.0 | 32 |
| road_waterlogging | 1.0 | 1.0 | 1.0 | 57 |
| rising_water | 1.0 | 1.0 | 1.0 | 46 |
| landslide | 0.979 | 1.0 | 0.989 | 47 |
| uncertain | 1.0 | 1.0 | 1.0 | 44 |

### Confusion matrix (test; rows = true, columns = predicted)

| | normal | heavy_rain | urban_flooding | river_flooding | flash_flooding | road_waterlogging | rising_water | landslide | uncertain |
|---|---|---|---|---|---|---|---|---|---|
| **normal** | 131 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **heavy_rain** | 0 | 42 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **urban_flooding** | 0 | 0 | 71 | 0 | 0 | 0 | 0 | 0 | 0 |
| **river_flooding** | 0 | 0 | 0 | 58 | 0 | 0 | 0 | 1 | 0 |
| **flash_flooding** | 0 | 0 | 0 | 0 | 32 | 0 | 0 | 0 | 0 |
| **road_waterlogging** | 0 | 0 | 0 | 0 | 0 | 57 | 0 | 0 | 0 |
| **rising_water** | 0 | 0 | 0 | 0 | 0 | 0 | 46 | 0 | 0 |
| **landslide** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 47 | 0 |
| **uncertain** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 44 |

### Accuracy by lighting condition (test)

| Condition | Images | Accuracy |
|---|---|---|
| day | 212 | 1.0 |
| dusk | 67 | 1.0 |
| fog | 77 | 1.0 |
| night | 115 | 0.991 |
| overcast | 58 | 1.0 |

## Decision agent (DQN) in the simulated incident environment

Episodes are built from CNN outputs on validation / test images only. *Photo rule* = level taken straight from the photo class with the policy's confidence threshold.

| Split | Policy | Mean reward | Events detected | Warned before onset | Missed events | Mean delay (steps of 30 min) | False alarms (quiet episodes) | Repeated alerts / episode | Level changes / episode |
|---|---|---|---|---|---|---|---|---|---|
| validation | decision agent | 1.003 | 0.996 | 0.233 | 0.004 | 0.15 | 0.074 | 0.136 | 1.633 |
| validation | photo rule | -2.993 | 0.995 | 0.144 | 0.005 | 0.88 | 0.59 | 0.653 | 2.689 |
| test | decision agent | 0.995 | 0.997 | 0.264 | 0.003 | 0.09 | 0.079 | 0.152 | 1.681 |
| test | photo rule | -2.933 | 0.992 | 0.169 | 0.008 | 0.75 | 0.643 | 0.641 | 2.699 |

Agent mode: **advisory (shadow)**. Validation rule: validated only if trained on non-synthetic data with test macro-F1 ≥ 0.80 and flood/landslide recall ≥ 0.85; the agent additionally must not miss more events or raise more false alarms than the photo rule.
