"""Custom CNN for disaster photos, trained from randomly initialised weights (no pretrained backbone).

Layout (for a 128 px input; any size divisible by 16 works):
  stem   3×3 conv stride 2 → 24 ch, BN, ReLU                     64×64
  block1 [3×3 conv, BN, ReLU] ×2 → 48 ch, 2×2 max-pool            32×32
  block2 [3×3 conv, BN, ReLU] ×2 → 96 ch, 2×2 max-pool            16×16
  block3 [3×3 conv, BN, ReLU] ×2 → 160 ch, 2×2 max-pool            8×8
  head   global average pool → 160-d visual features → dropout → linear → 9 class logits

The 160-d pooled vector is the "visual feature" passed to the decision agent. Requires PyTorch (ml image only).
"""
import numpy as np
import torch
from torch import nn

from app.vision.classes import CLASSES

CHANNELS = (24, 48, 96, 160)
EMBED_DIM = CHANNELS[-1]


def _cbr(cin: int, cout: int, stride: int = 1) -> list[nn.Module]:
    return [nn.Conv2d(cin, cout, 3, stride=stride, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True)]


class DisasterCNN(nn.Module):
    def __init__(self, n_classes: int = len(CLASSES), dropout: float = 0.3):
        super().__init__()
        c0, c1, c2, c3 = CHANNELS
        self.features = nn.Sequential(
            *_cbr(3, c0, 2),
            *_cbr(c0, c1), *_cbr(c1, c1), nn.MaxPool2d(2),
            *_cbr(c1, c2), *_cbr(c2, c2), nn.MaxPool2d(2),
            *_cbr(c2, c3), *_cbr(c3, c3), nn.MaxPool2d(2),
        )
        self.drop = nn.Dropout(dropout)
        self.fc = nn.Linear(c3, n_classes)
        for m in self.modules():                                     # random initialisation (He / Kaiming)
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode="fan_out", nonlinearity="relu")
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.ones_(m.weight)
                nn.init.zeros_(m.bias)

    def embed(self, x: torch.Tensor) -> torch.Tensor:
        return self.features(x).mean(dim=(2, 3))

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        e = self.embed(x)
        return self.fc(self.drop(e)), e


def export(model: DisasterCNN) -> dict[str, np.ndarray]:
    """Fold each BatchNorm into the preceding conv and return numpy arrays for app.vision.cnn_np.

    Keys: conv{i}.w (O, C, 3, 3), conv{i}.b (O,), conv{i}.stride, pool_after (indices of convs followed by a pool),
    fc.w, fc.b."""
    model = model.eval()
    out: dict[str, np.ndarray] = {}
    layers = list(model.features)
    i, k, pools = 0, 0, []
    while i < len(layers):
        conv, bn = layers[i], layers[i + 1]
        assert isinstance(conv, nn.Conv2d) and isinstance(bn, nn.BatchNorm2d)
        scale = (bn.weight / torch.sqrt(bn.running_var + bn.eps)).detach()
        out[f"conv{k}.w"] = (conv.weight.detach() * scale[:, None, None, None]).numpy().astype(np.float32)
        out[f"conv{k}.b"] = (bn.bias.detach() - bn.running_mean * scale).numpy().astype(np.float32)
        out[f"conv{k}.stride"] = np.array(conv.stride[0])
        i += 3                                                       # conv, bn, relu
        if i < len(layers) and isinstance(layers[i], nn.MaxPool2d):
            pools.append(k)
            i += 1
        k += 1
    out["n_convs"] = np.array(k)
    out["pool_after"] = np.array(pools)
    out["fc.w"] = model.fc.weight.detach().numpy().astype(np.float32)
    out["fc.b"] = model.fc.bias.detach().numpy().astype(np.float32)
    return out
