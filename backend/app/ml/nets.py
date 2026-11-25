"""Forward passes of the trained neural networks in plain numpy, so the live backend needs no PyTorch.
Weights are PyTorch state_dicts exported to .npz by app.ml.train; the layouts here mirror the torch modules there."""
import numpy as np


def _sigmoid(x):
    return 1 / (1 + np.exp(-x))


def lstm_forward(w: dict, seq: np.ndarray, extra: np.ndarray) -> np.ndarray:
    """seq: (batch, steps, inputs); extra: (batch, k) forecast-rain inputs joined after the LSTM.
    Mirrors FlowLSTM: LSTM (gate order i, f, g, o like torch) → concat extra → Linear → ReLU → Linear."""
    W_ih, W_hh, b = w["lstm.weight_ih_l0"], w["lstm.weight_hh_l0"], w["lstm.bias_ih_l0"] + w["lstm.bias_hh_l0"]
    H = W_hh.shape[1]
    h = np.zeros((seq.shape[0], H), dtype=np.float32)
    c = np.zeros_like(h)
    for t in range(seq.shape[1]):
        g = seq[:, t] @ W_ih.T + h @ W_hh.T + b
        i, f, gg, o = _sigmoid(g[:, :H]), _sigmoid(g[:, H:2 * H]), np.tanh(g[:, 2 * H:3 * H]), _sigmoid(g[:, 3 * H:])
        c = f * c + i * gg
        h = o * np.tanh(c)
    x = np.maximum(np.concatenate([h, extra], axis=1) @ w["head.0.weight"].T + w["head.0.bias"], 0)
    return x @ w["head.2.weight"].T + w["head.2.bias"]


def mlp_forward(w: dict, x: np.ndarray) -> np.ndarray:
    """Mirrors QNet: Linear → ReLU → Linear → ReLU → Linear (one Q-value per action)."""
    x = np.maximum(x @ w["net.0.weight"].T + w["net.0.bias"], 0)
    x = np.maximum(x @ w["net.2.weight"].T + w["net.2.bias"], 0)
    return x @ w["net.4.weight"].T + w["net.4.bias"]
