from app.devices.signing import device_key, sign_command, verify_command
from app.processing.validation import check, station_range


def test_range_and_missing():
    assert check("water_level_m", None, []).quality == "MISSING"
    assert check("water_level_m", 99.0, []).quality == "BAD"
    assert check("rain_1h_mm", -1.0, []).quality == "BAD"
    assert check("water_level_m", 2.4, [2.3]).quality == "GOOD"


def test_spike_and_flatline():
    assert check("water_level_m", 7.0, [2.0]).quality == "SUSPECT"
    flat = [3.21] * 11
    r = check("water_level_m", 3.21, flat)
    assert r.quality == "SUSPECT" and "flatline" in r.reason


def test_siren_signature_roundtrip_sr13():
    master = "test-master-key"
    msg = sign_command(master, "siren-001", "activate", test_mode=True, issued_at=1_000_000, nonce="abc")
    key = device_key(master, "siren-001")
    assert verify_command(key, msg, now=1_000_010)


def test_siren_rejects_tampering_replay_and_other_device_key():
    master = "test-master-key"
    msg = sign_command(master, "siren-001", "activate", test_mode=True, issued_at=1_000_000, nonce="abc")
    key = device_key(master, "siren-001")
    assert not verify_command(key, {**msg, "test_mode": False}, now=1_000_010)          # tampered
    assert not verify_command(key, msg, now=1_000_500)                                   # too old
    assert not verify_command(key, msg, now=1_000_010, seen_nonces={"abc"})              # replay
    assert not verify_command(device_key(master, "siren-002"), msg, now=1_000_010)       # wrong device


def test_elevation_datum_station_is_not_flagged_bad():
    bounds = station_range("water_level_m", 1345.8, 1346.0)
    assert check("water_level_m", 1343.9, [1343.8], bounds).quality == "GOOD"
    assert check("water_level_m", 12.0, [], bounds).quality == "BAD"
    assert station_range("water_level_m", 4.5, None) == (-5.0, 60.0)


def test_password_hash_and_totp():
    from app.security import hash_password, totp_code, verify_password, verify_totp
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h) and not verify_password("wrong", h)
    # RFC 6238 test vector (SHA1, secret "12345678901234567890", T=59 -> 287082)
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert totp_code(secret, at=59) == "287082"
    assert verify_totp(secret, "287082", at=59 + 30)      # one step of clock drift accepted
    assert not verify_totp(secret, "287082", at=59 + 120)


def test_login_throttle():
    from app.security import LoginThrottle
    t = LoginThrottle(max_failures=3)
    for _ in range(3):
        t.fail("e:a")
    assert t.blocked("e:a") and not t.blocked("e:b")
    t.reset("e:a")
    assert not t.blocked("e:a")
