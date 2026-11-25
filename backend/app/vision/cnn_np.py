"""Numpy forward pass of the exported DisasterCNN (BatchNorm folded into the convs), so the live backend needs no
PyTorch. Mirrors app.vision.cnn exactly; tests/test_visual.py checks the two agree."""
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view


def conv3x3(x: np.ndarray, w: np.ndarray, b: np.ndarray, stride: int) -> np.ndarray:
    """x (C, H, W), w (O, C, 3, 3), padding 1 → (O, H', W')."""
    xp = np.pad(x, ((0, 0), (1, 1), (1, 1)))
    win = sliding_window_view(xp, (3, 3), axis=(1, 2))[:, ::stride, ::stride]     # (C, H', W', 3, 3)
    out = np.einsum("chwij,ocij->ohw", win, w, optimize=True)
    return out + b[:, None, None]


def maxpool2(x: np.ndarray) -> np.ndarray:
    c, h, w = x.shape
    h2, w2 = h // 2, w // 2
    return x[:, :h2 * 2, :w2 * 2].reshape(c, h2, 2, w2, 2).max(axis=(2, 4))


def forward(weights: dict, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """x (3, S, S) normalised image → (logits (n_classes,), embedding (embed_dim,))."""
    pools = set(int(p) for p in np.atleast_1d(weights["pool_after"]))
    h = x.astype(np.float32)
    for k in range(int(weights["n_convs"])):
        h = np.maximum(conv3x3(h, weights[f"conv{k}.w"], weights[f"conv{k}.b"], int(weights[f"conv{k}.stride"])), 0)
        if k in pools:
            h = maxpool2(h)
    emb = h.mean(axis=(1, 2))
    return emb @ weights["fc.w"].T + weights["fc.b"], emb


def softmax(z: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    z = z / temperature
    e = np.exp(z - z.max())
    return e / e.sum()
