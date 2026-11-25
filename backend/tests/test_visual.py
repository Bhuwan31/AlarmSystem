"""Visual disaster detection: image validation, EXIF time/GPS, duplicates, CNN and agent numpy forwards, simulator,
safety policy, radius suggestion, recipients and notification rules, gazetteer and endpoint authorisation."""
import asyncio
import io
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from PIL import Image

from app.geo_nepal import DISTRICTS, PROVINCES, canonical_district, haversine_km, nearest_district, place_label
from app.vision import cnn_np, imageio, notify, policy
from app.vision import state as S
from app.vision.classes import ACTIONS, CLASSES
from app.vision.context import correlation, time_checks

NPT = timezone(timedelta(hours=5, minutes=45))


def _jpeg(w=320, h=240, exif: bytes | None = None, colour=(90, 110, 140)) -> bytes:
    buf = io.BytesIO()
    yy, xx = np.mgrid[0:h, 0:w]                         # smooth photo-like structure so the perceptual hash is meaningful
    a = np.stack([colour[0] + 80 * np.sin(xx / w * 5), colour[1] + 60 * np.cos(yy / h * 4), colour[2] + 40 * np.sin((xx + yy) / w * 3)], -1)
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    img.save(buf, "JPEG", **({"exif": exif} if exif else {}))
    return buf.getvalue()


# ---------------------------------------------------------------------------------------------------------- uploads
def test_validation_accepts_jpeg_png_webp_and_rejects_others():
    for fmt in ("JPEG", "PNG", "WEBP"):
        buf = io.BytesIO()
        Image.new("RGB", (100, 100), (1, 2, 3)).save(buf, fmt)
        assert imageio.validate(buf.getvalue(), 10_000_000).size == (100, 100)
    buf = io.BytesIO()
    Image.new("RGB", (100, 100)).save(buf, "GIF")
    with pytest.raises(imageio.ImageRejected, match="unsupported format"):
        imageio.validate(buf.getvalue(), 10_000_000)
    with pytest.raises(imageio.ImageRejected, match="not a readable image"):
        imageio.validate(b"%PDF-1.4 not an image", 10_000_000)
    with pytest.raises(imageio.ImageRejected, match="larger than"):
        imageio.validate(_jpeg(), 100)
    with pytest.raises(imageio.ImageRejected, match="too small"):
        imageio.validate(_jpeg(40, 40), 10_000_000)
    with pytest.raises(imageio.ImageRejected, match="empty"):
        imageio.validate(b"", 10)


def test_exif_capture_time_with_offset_and_gps_are_extracted():
    when = datetime(2026, 7, 14, 16, 5, 9, tzinfo=NPT)
    data = _jpeg(exif=imageio.exif_bytes_for_test(27.7008, 85.3001, when, accuracy_m=6.5))
    _, info = imageio.inspect(data, 10_000_000)
    assert info.capture_time == when and info.capture_time.utcoffset() == timedelta(hours=5, minutes=45)
    assert info.capture_time_source == "exif"
    assert info.gps == pytest.approx((27.7008, 85.3001), abs=1e-4)
    assert info.gps_accuracy_m == pytest.approx(6.5)


def test_exif_without_offset_uses_uploader_timezone_and_says_so():
    img = Image.new("RGB", (100, 100))
    ex = Image.Exif()
    ex.get_ifd(0x8769)[0x9003] = "2026:07:14 10:00:00"
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=ex.tobytes())
    _, info = imageio.inspect(buf.getvalue(), 10_000_000, client_tz=NPT)
    assert info.capture_time == datetime(2026, 7, 14, 10, 0, tzinfo=NPT) and info.capture_time_source == "exif_assumed_tz"
    _, info2 = imageio.inspect(buf.getvalue(), 10_000_000, client_tz=None)
    assert info2.capture_time is None                                 # no timezone known → no capture time, not a guess


def test_no_exif_means_no_time_and_no_gps():
    _, info = imageio.inspect(_jpeg(), 10_000_000)
    assert info.capture_time is None and info.gps is None and info.capture_time_source == "unknown"


def test_preview_strips_gps_metadata():
    data = _jpeg(exif=imageio.exif_bytes_for_test(27.7, 85.3, datetime.now(NPT)))
    img = imageio.validate(data, 10_000_000)
    prev = Image.open(io.BytesIO(imageio.preview_jpeg(img)))
    assert not prev.getexif().get_ifd(0x8825)


def test_duplicate_detection_with_perceptual_hash():
    a = Image.open(io.BytesIO(_jpeg()))
    b = Image.open(io.BytesIO(_jpeg())).resize((300, 225))                 # re-sized copy of the same photo
    c = Image.new("RGB", (320, 240), (10, 200, 30))
    for y in range(0, 240, 12):
        c.paste((0, 0, 0), (0, y, 320, y + 3))
    assert imageio.hamming(imageio.dhash(a), imageio.dhash(b)) <= 4
    assert imageio.hamming(imageio.dhash(a), imageio.dhash(c)) > 10


def test_preprocessing_shape_and_normalisation():
    x = imageio.to_array(Image.new("RGB", (640, 480), (124, 116, 104)), 128)
    assert x.shape == (3, 128, 128) and x.dtype == np.float32
    assert np.allclose(x, 0, atol=0.02)                                   # the mean colour maps to ~0


# ---------------------------------------------------------------------------------------------------------- models
def test_numpy_cnn_matches_torch_with_batchnorm_folded():
    torch = pytest.importorskip("torch")
    from app.vision.cnn import DisasterCNN, export
    torch.manual_seed(0)
    m = DisasterCNN()
    with torch.no_grad():                                                  # non-trivial BN statistics
        for mod in m.modules():
            if isinstance(mod, torch.nn.BatchNorm2d):
                mod.running_mean.uniform_(-0.2, 0.2)
                mod.running_var.uniform_(0.5, 1.5)
                mod.weight.uniform_(0.5, 1.5)
                mod.bias.uniform_(-0.1, 0.1)
    m.eval()
    x = torch.randn(1, 3, 64, 64)
    with torch.no_grad():
        ref_logits, ref_emb = m(x)
    w = export(m)
    logits, emb = cnn_np.forward(w, x[0].numpy())
    assert np.allclose(logits, ref_logits[0].numpy(), atol=1e-3)
    assert np.allclose(emb, ref_emb[0].numpy(), atol=1e-3)


def test_numpy_agent_matches_torch():
    torch = pytest.importorskip("torch")
    from app.ml.nets import mlp_forward
    from app.vision.train_all import QNet
    torch.manual_seed(1)
    q = QNet().eval()
    s = torch.randn(4, S.STATE_DIM)
    with torch.no_grad():
        ref = q(s).numpy()
    assert ref.shape == (4, len(ACTIONS))
    assert np.allclose(mlp_forward({k: v.numpy() for k, v in q.state_dict().items()}, s.numpy()), ref, atol=1e-5)


def test_state_vector_marks_missing_weather_as_unavailable_not_dry():
    p = np.full(len(CLASSES), 1 / len(CLASSES), dtype=np.float32)
    e = np.zeros(S.EMBED_K, dtype=np.float32)
    none = S.build(p, e, {})
    dry = S.build(p, e, {"gauge_rain_1h": 0.0, "gauge_rain_24h": 0.0})
    i = S.STATE_NAMES.index("gauge_rain_available")
    assert none.shape == (S.STATE_DIM,) and none[i] == 0 and dry[i] == 1


def _pool():
    from app.vision.env import Pool
    rng = np.random.default_rng(0)
    probs, emb = {}, {}
    for k, c in enumerate(CLASSES):
        p = np.full((20, len(CLASSES)), 0.02, dtype=np.float32)
        p[:, k] = 1 - 0.02 * (len(CLASSES) - 1)
        probs[c], emb[c] = p, rng.normal(size=(20, S.EMBED_K)).astype(np.float32)
    return Pool(probs, emb)


def test_simulator_rewards_follow_the_design():
    from app.vision.env import VisualIncidentEnv
    env = VisualIncidentEnv(_pool(), seed=3)
    env.reset()
    ep = env.ep
    ep.latent[:] = 0
    assert env.reward(ACTIONS.index("ISSUE_WARNING"), 0, 2) < env.reward(ACTIONS.index("NO_ALERT"), 0, 0)   # false alarm costs
    ep.latent[:] = 3
    miss = env.reward(ACTIONS.index("NO_ALERT"), 0, 0)
    assert miss < env.reward(ACTIONS.index("ISSUE_WARNING"), 0, 2) < env.reward(ACTIONS.index("ISSUE_CRITICAL_ALERT"), 0, 3)
    ep.prior = 3                                                       # already issued CRITICAL once, then dropped
    assert env.reward(ACTIONS.index("ISSUE_CRITICAL_ALERT"), 2, 3) < env.reward(ACTIONS.index("ISSUE_CRITICAL_ALERT"), 3, 3)
    s, r, done, _ = env.step(ACTIONS.index("REQUEST_ADDITIONAL_EVIDENCE"))
    assert s.shape == (S.STATE_DIM,) and not done


def test_simulator_episode_runs_to_the_end():
    from app.vision.env import T, VisualIncidentEnv, episode_metrics
    env = VisualIncidentEnv(_pool(), seed=5)
    for _ in range(20):
        env.reset()
        done, n = False, 0
        while not done:
            _, _, done, _ = env.step(np.random.default_rng(n).integers(len(ACTIONS)))
            n += 1
        assert n == T
        m = episode_metrics(env.ep.log, env.ep.latent)
        assert "repeats" in m and "false_public_alert" in m


# ---------------------------------------------------------------------------------------------------------- policy
def ev(**kw):
    base = dict(location_source="device_gps", accuracy_m=10, age_h=0.2, image_source="camera", capture_time_source="device_clock")
    return policy.Evidence(**{**base, **kw})


def test_photo_alone_is_capped_at_warning_and_never_auto_sent():
    d = policy.evaluate("flash_flooding", 0.97, ev())
    assert d.alert_level == "WARNING" and d.eligible and not d.corroborated
    assert any("reviewer must approve" in r for r in d.reasons)


def test_critical_needs_corroboration_and_a_second_report():
    assert policy.evaluate("urban_flooding", 0.95, ev(weather_correlation="confirmed")).alert_level == "WARNING"
    d = policy.evaluate("urban_flooding", 0.95, ev(weather_correlation="confirmed", reports_nearby=1))
    assert d.alert_level == "CRITICAL" and d.risk_level == "SEVERE"


def test_heavy_rain_photo_never_confirms_rain_and_is_capped_at_watch():
    d = policy.evaluate("heavy_rain", 0.99, ev(weather_correlation="confirmed", reports_nearby=5))
    assert d.alert_level == "WATCH"
    assert any("does not by itself confirm rain now" in r for r in d.reasons)


def test_missing_weather_is_not_confirmation():
    d = policy.evaluate("urban_flooding", 0.9, ev(weather_correlation="unavailable"))
    assert not d.corroborated and any("not as confirmation" in r for r in d.reasons)


def test_contradicting_gauges_cap_rain_driven_classes():
    assert policy.evaluate("urban_flooding", 0.9, ev(weather_correlation="contradicted")).alert_level == "WATCH"


def test_stale_future_duplicate_and_unavailable_model_are_blocked():
    assert not policy.evaluate("urban_flooding", 0.95, ev(age_h=30)).eligible
    assert not policy.evaluate("urban_flooding", 0.95, ev(future_min=60)).eligible
    assert not policy.evaluate("urban_flooding", 0.95, ev(duplicate_of="x")).eligible
    d = policy.evaluate("urban_flooding", 0.95, ev(model_available=False))
    assert not d.eligible and d.policy_action == "REQUEST_ADDITIONAL_EVIDENCE"


def test_uncertain_location_or_time_caps_at_watch():
    assert policy.evaluate("river_flooding", 0.95, ev(location_source="manual", accuracy_m=None)).alert_level == "WATCH"
    assert policy.evaluate("river_flooding", 0.95, ev(age_h=None, image_source="upload")).alert_level == "WATCH"
    assert policy.evaluate("river_flooding", 0.95, ev(location_source="manual", river_level=2)).alert_level == "WARNING"


def test_low_confidence_and_uncertain_class():
    assert policy.evaluate("urban_flooding", 0.5, ev()).policy_action == "MONITOR"
    assert policy.evaluate("uncertain", 0.9, ev()).policy_action == "REQUEST_ADDITIONAL_EVIDENCE"
    assert policy.evaluate("normal", 0.9, ev()).policy_action == "NO_ALERT"


def test_unvalidated_agent_is_advisory_only():
    a = policy.evaluate("urban_flooding", 0.9, ev(), dqn_action="NO_ALERT", dqn_validated=False)
    assert a.alert_level == "WARNING" and any("advisory only" in r for r in a.reasons)
    b = policy.evaluate("urban_flooding", 0.9, ev(), dqn_action="NO_ALERT", dqn_validated=True)
    assert b.alert_level == "WATCH"                                    # validated agent may lower by one level, not raise
    c = policy.evaluate("road_waterlogging", 0.9, ev(), dqn_action="ISSUE_CRITICAL_ALERT", dqn_validated=True)
    assert c.alert_level == "WATCH"
    d = policy.evaluate("urban_flooding", 0.9, ev(), dqn_action="REQUEST_ADDITIONAL_EVIDENCE", dqn_validated=True)
    assert not d.eligible


def test_radius_depends_on_type_severity_and_conditions():
    assert policy.suggest_radius("road_waterlogging", 1, ev()) == 1
    assert policy.suggest_radius("urban_flooding", 2, ev()) == 3
    assert policy.suggest_radius("flash_flooding", 3, ev()) == 10
    assert policy.suggest_radius("river_flooding", 2, ev(river_km=1.0)) == 10
    assert policy.suggest_radius("landslide", 2, ev(official_level=2)) == 5
    assert all(policy.suggest_radius(c, lv, ev()) in policy.RADII for c in policy.RADIUS for lv in (1, 2, 3))


def test_weather_correlation_categories():
    assert correlation(8, 10, None) == "confirmed" and correlation(None, 30, None) == "confirmed"
    assert correlation(0, 1, 80) == "contradicted"                        # measured gauges win over the model
    assert correlation(2, 12, None) == "inconclusive"
    assert correlation(None, None, 40) == "supported_by_model" and correlation(None, None, None) == "unavailable"


def test_time_checks():
    now = datetime(2026, 7, 1, 12, tzinfo=timezone.utc)
    assert time_checks(None, now) == (None, 0.0)
    age, fut = time_checks(now - timedelta(hours=3), now)
    assert age == pytest.approx(3) and fut == 0
    _, fut = time_checks(now + timedelta(minutes=30), now)
    assert fut == pytest.approx(30)


# ---------------------------------------------------------------------------------------------------------- geography
def test_gazetteer_has_7_provinces_and_77_districts():
    assert len(PROVINCES) == 7 and len(DISTRICTS) == 77
    assert {p for p, *_ in DISTRICTS.values()} == set(PROVINCES)
    assert canonical_district("SINDHUPALCHOWK") == "Sindhupalchok" and canonical_district("kathmandu") == "Kathmandu"
    assert nearest_district(27.70, 85.33)[0] == "Kathmandu"
    assert "Pokhara" in place_label(28.21, 83.99)


def test_haversine():
    assert haversine_km(27.7, 85.3, 27.7, 85.3) == 0
    assert haversine_km(27.70, 85.30, 27.709, 85.30) == pytest.approx(1.0, abs=0.01)


# ---------------------------------------------------------------------------------------------------------- notifications
def test_message_text_has_required_parts_and_disclaimer():
    body = notify.incident_body("WARNING", "HIGH", "FLOOD", "Kathmandu, Kathmandu district", datetime(2026, 7, 14, 10, tzinfo=timezone.utc),
                                "Asia/Kathmandu", 1.24, exercise=True)
    for part in ("EXERCISE", "Location: Kathmandu", "Risk level: HIGH", "Reported: 2026-07-14 15:45", "Distance: 1.2 km",
                 "Avoid flooded roads", "AI-assisted visual observation", "not an official government emergency announcement"):
        assert part in body
    assert notify.incident_title("WARNING", "FLOOD") == "FLOOD WARNING"
    assert notify.incident_title("CRITICAL", "LANDSLIDE") == "CRITICAL LANDSLIDE ALERT"


def test_channel_resolution_respects_preferences_and_contact_details():
    r = notify.Recipient("u", email=None, phone="+97798", channels={"sms": True, "email": True, "push": False}, distance_km=1)
    assert notify.resolve_channels(r, set(notify.CHANNELS)) == ["in_app", "sms"]       # no email address → no email
    assert notify.resolve_channels(r, {"in_app"}) == ["in_app"]


class FakeConn:
    """Just enough of asyncpg for notify.distribute: records rows and enforces the dedup unique index."""

    def __init__(self, history=None, today=0):
        self.rows, self.keys, self.history, self.today = [], set(), history, today

    async def fetchrow(self, q, *a):
        return self.history

    async def fetchval(self, q, *a):
        if q.strip().startswith("insert"):
            incident, broadcast, rid, ch, status, level = a[:6]
            key = (incident, broadcast, rid, ch, level if incident else None)
            if key in self.keys:
                return None
            self.keys.add(key)
            self.rows.append({"id": len(self.rows), "recipient": rid, "channel": ch, "status": status, "level": level})
            return len(self.rows) - 1
        return self.today

    async def execute(self, q, *a):
        if q.strip().startswith("update"):
            self.rows[a[0]]["status"] = a[1]
        return "UPDATE 1"


def test_distribution_dedups_simulates_external_and_skips_unconfigured(monkeypatch):
    from app import config
    config.get_settings.cache_clear()
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_FROM", "alerts@example.test")
    monkeypatch.setenv("NOTIFY_EXTERNAL_ENABLED", "false")
    try:
        conn = FakeConn()
        recips = [notify.Recipient("a", "a@x.test", None, {"in_app": True, "email": True}, 0.5),
                  notify.Recipient("b", None, "+9779800000000", {"in_app": True, "sms": True}, 2.0)]

        async def run():
            return await notify.distribute(conn, recipients=recips, level="WARNING", title="FLOOD WARNING", body_for=lambda r: "x",
                                           allowed_channels=set(notify.CHANNELS), incident_id="i1")
        c1 = asyncio.run(run())
        assert c1["delivered"] == 2 and c1["simulated"] == 1 and c1["skipped_unconfigured"] == 1     # email simulated; SMS not configured
        c2 = asyncio.run(run())                                                                        # same incident and level again
        assert c2.get("duplicate_skipped") == 4 and "delivered" not in c2
    finally:
        config.get_settings.cache_clear()


def test_cooldown_and_daily_limit():
    r = notify.Recipient("a", None, None, {"in_app": True}, 1)
    recent = {"lvl": 2, "at": datetime.now(timezone.utc) - timedelta(minutes=5)}
    assert asyncio.run(notify.suppression_reason(FakeConn(history=recent), r, "WARNING", "i1"))           # same level, in cooldown
    assert asyncio.run(notify.suppression_reason(FakeConn(history=recent), r, "WATCH", "i1"))             # lower than already sent
    assert asyncio.run(notify.suppression_reason(FakeConn(history=recent), r, "CRITICAL", "i1")) is None  # escalation goes out
    assert asyncio.run(notify.suppression_reason(FakeConn(history=None, today=99), r, "WARNING", None))   # daily limit
    assert asyncio.run(notify.suppression_reason(FakeConn(history=None, today=99), r, "CRITICAL", None)) is None
    assert asyncio.run(notify.suppression_reason(FakeConn(history=recent), r, "INFO", "i1", all_clear=True)) is None


# ---------------------------------------------------------------------------------------------------------- inference
def test_model_unavailable_is_reported_not_guessed(tmp_path):
    from app.vision.infer import ModelUnavailable, VisualModels
    m = VisualModels(tmp_path)
    assert not m.available and m.version == "unavailable"
    with pytest.raises(ModelUnavailable):
        m.classify(Image.new("RGB", (100, 100)))


def test_trained_artifacts_load_and_classify_if_present():
    from app.vision.infer import MODELS
    if not MODELS.available:
        pytest.skip("no trained visual model in app/vision/artifacts")
    res = MODELS.classify(Image.new("RGB", (300, 200), (90, 120, 160)))
    assert res["class"] in CLASSES and 0 <= res["confidence"] <= 1 and abs(res["probs"].sum() - 1) < 1e-4
    action, q = MODELS.advise(S.build(res["probs"], res["emb_proj"], {}))
    assert action in ACTIONS and len(q) == len(ACTIONS)


# ---------------------------------------------------------------------------------------------------------- auth
def test_endpoints_require_authentication_and_roles():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.security import mint_token
    c = TestClient(app)                                     # no lifespan: requests below fail before touching the database
    for method, path in (("get", "/api/v1/visual-disaster/observations"), ("post", "/api/v1/visual-disaster/analyze"),
                         ("get", "/api/v1/visual-disaster/incidents"), ("get", "/api/v1/visual-disaster/alerts"),
                         ("put", "/api/v1/visual-disaster/subscription"), ("post", "/api/v1/visual-disaster/broadcasts")):
        assert getattr(c, method)(path).status_code == 401, path
    viewer = {"Authorization": f"Bearer {mint_token('00000000-0000-0000-0000-000000000001', 'v@x.test', 'viewer', False)}"}
    assert c.get("/api/v1/visual-disaster/incidents", headers=viewer).status_code == 403
    assert c.post("/api/v1/visual-disaster/incidents/x/approve-send", headers=viewer, json={}).status_code == 403
    assert c.post("/api/v1/visual-disaster/broadcasts", headers=viewer, json={}).status_code == 403
    op = {"Authorization": f"Bearer {mint_token('00000000-0000-0000-0000-000000000002', 'o@x.test', 'operator', False)}"}
    assert c.post("/api/v1/visual-disaster/incidents/x/close", headers=viewer, json={"note": "abc"}).status_code == 403  # operators may close (SEND_ROLE)
    appr = {"Authorization": f"Bearer {mint_token('00000000-0000-0000-0000-000000000003', 'a@x.test', 'approver', False)}"}
    r = c.post("/api/v1/visual-disaster/incidents/x/approve-send", headers=appr,
               json={"level": "WARNING", "radius_km": 4, "title": "FLOOD", "body": "x" * 30})
    assert r.status_code == 422                                                              # radius must be 1/3/5/10
