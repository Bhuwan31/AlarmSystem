"""ML feature engineering and the numpy re-implementations of the trained networks."""
import numpy as np
import pytest

from app.ml import features as F
from app.ml.nets import lstm_forward, mlp_forward


def _series(n=200, seed=1):
    rng = np.random.default_rng(seed)
    rain = rng.gamma(0.6, 8, n)
    q = 50 + np.convolve(rain, np.exp(-np.arange(10) / 3), mode="full")[:n] * 4
    dates = [str(np.datetime64("2020-01-01") + np.timedelta64(i, "D")) for i in range(n)]
    return dates, q, rain


def test_station_stats_and_classes_follow_percentiles():
    _, q, _ = _series(1000)
    st = F.station_stats(q)
    assert st["q_watch"] < st["q_warning"] < st["q_critical"]
    cls = F.classify(q, st)
    assert 0.08 < (cls >= 1).mean() < 0.12          # about 10 % of days at WATCH or above
    assert (cls == 3).mean() < 0.01


def test_qn_round_trip():
    st = {"mu": 3.0, "sd": 0.7}
    q = np.array([0.0, 5.0, 500.0])
    assert np.allclose(F.q_from_qn(F.qn(q, st), st), q)


def _ctx(q, rain, st, q_up=None):
    n = len(q)
    return F.context(q, rain, st, q_up, np.full(n, 0.3), np.linspace(-5, 10, n), np.zeros(n))


def test_build_targets_look_ahead_without_leaking_into_features():
    dates, q, rain = _series()
    st = F.station_stats(q)
    d = F.build(dates, _ctx(q, rain, st))
    assert d["X"].shape[1] == len(F.FEATURES)
    assert d["S"].shape[1:] == (F.SEQ_LEN, len(F.SEQ_FEATURES))
    t = d["t"][5]
    z = F.qn(q, st)
    assert d["X"][5][0] == pytest.approx(z[t])                       # flow_now is today's flow
    assert d["y1"][5] == pytest.approx(z[t + 1] - z[t])               # target is tomorrow's change
    assert d["y_cls"][5] == F.classify(q[t + 1:t + 4], st).max()      # class is the worst of the next 3 days
    lo, hi = F.UNCERTAINTY_RANGE
    assert ((d["X"][:, F.FEATURES.index("forecast_uncertainty")] >= lo) & (d["X"][:, F.FEATURES.index("forecast_uncertainty")] <= hi)).all()


def test_upstream_inputs_are_zero_without_upstream_and_on_own_scale_with_it():
    dates, q, rain = _series()
    st = F.station_stats(q)
    no_up = F.build(dates, _ctx(q, rain, st))
    up = F.build(dates, _ctx(q, rain, st, q_up=q.copy()))
    i_up, i_has = F.FEATURES.index("upstream_flow_now"), F.FEATURES.index("has_upstream")
    assert (no_up["X"][:, i_up] == 0).all() and (no_up["X"][:, i_has] == 0).all()
    assert np.allclose(up["X"][:, i_up], up["X"][:, 0]) and (up["X"][:, i_has] == 1).all()   # same water → same scaled flow


def test_anomaly_features_flag_a_jump_and_a_stuck_gauge():
    from datetime import datetime, timedelta
    t0 = datetime(2026, 1, 1)
    times = [t0 + timedelta(minutes=15 * i) for i in range(40)]
    vals = [2.0 + 0.01 * (i % 5) for i in range(40)]
    vals[20] = 6.0                                  # spike
    for i in range(30, 40):
        vals[i] = 2.02                              # stuck
    X = F.anomaly_matrix(times, vals)
    assert X[20, 1] == X[:, 1].max()                # biggest jump at the spike
    assert X[-1, 4] > 0.5                           # long flat run at the end


def test_numpy_networks_match_torch():
    torch = pytest.importorskip("torch")
    from app.ml.train import STATE_DIM, FlowLSTM, QNet
    torch.manual_seed(0)
    lstm, q = FlowLSTM().eval(), QNet().eval()
    seq, extra, s = torch.randn(3, F.SEQ_LEN, len(F.SEQ_FEATURES)), torch.randn(3, len(F.FC_IDX)), torch.randn(3, STATE_DIM)
    with torch.no_grad():
        ref_l, ref_q = lstm(seq, extra).numpy(), q(s).numpy()
    wl = {k: v.numpy() for k, v in lstm.state_dict().items()}
    wq = {k: v.numpy() for k, v in q.state_dict().items()}
    assert np.allclose(lstm_forward(wl, seq.numpy(), extra.numpy()), ref_l, atol=1e-5)
    assert np.allclose(mlp_forward(wq, s.numpy()), ref_q, atol=1e-5)


def test_dqn_reward_prefers_early_correct_warnings():
    torch = pytest.importorskip("torch")  # noqa: F841  (train imports torch)
    from app.ml.train import reward
    assert reward(2, 2, 2) > reward(1, 2, 1) > reward(0, 2, 0)     # under-calling a flood gets worse with distance
    assert reward(0, 2, 0) < reward(2, 0, 2)                        # a miss costs more than a false alarm
    assert reward(1, 1, 0) < reward(1, 1, 1)                        # changing level has a small cost
