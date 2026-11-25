"""Live inference with the exported visual models (numpy only). Reloads automatically when artifacts change."""
import json
import logging
import threading
from pathlib import Path

import numpy as np
from PIL import Image

from app.ml.nets import mlp_forward
from app.vision import cnn_np
from app.vision import state as S
from app.vision.classes import ACTIONS, CLASSES
from app.vision.imageio import to_array

log = logging.getLogger(__name__)
ART = Path(__file__).resolve().parent / "artifacts"


class ModelUnavailable(RuntimeError):
    pass


class VisualModels:
    def __init__(self, art: Path = ART):
        self.art = art
        self._lock = threading.Lock()
        self._stamp: tuple | None = None
        self.cnn: dict | None = None
        self.dqn: dict | None = None
        self.pca: dict | None = None
        self.meta: dict = {}

    def _files(self):
        return [self.art / n for n in ("cnn.npz", "dqn.npz", "vision_meta.json")]

    def load(self) -> None:
        with self._lock:
            files = self._files()
            if not all(f.exists() for f in files):
                self.cnn = self.dqn = None
                self.meta = {}
                self._stamp = None
                return
            stamp = tuple(f.stat().st_mtime for f in files)
            if stamp == self._stamp:
                return
            meta = json.loads(files[2].read_text(encoding="utf-8"))
            if meta.get("classes") != CLASSES or meta.get("state_names") != S.STATE_NAMES:
                log.error("visual model artifacts do not match this code version (classes/state); retrain")
                self.cnn = self.dqn = None
                self.meta = {**meta, "error": "artifacts do not match code version"}
                self._stamp = stamp
                return
            with np.load(files[0]) as z:
                self.cnn = {k: z[k] for k in z.files}
            with np.load(files[1]) as z:
                d = {k: z[k] for k in z.files}
            self.pca = {"mean": d.pop("pca_mean"), "components": d.pop("pca_components"), "scale": d.pop("pca_scale")}
            self.dqn = d
            self.meta = meta
            self._stamp = stamp
            log.info("loaded visual models %s / %s", meta["cnn"]["version"], meta["dqn"]["version"])

    @property
    def available(self) -> bool:
        self.load()
        return self.cnn is not None

    def classify(self, img: Image.Image) -> dict:
        if not self.available:
            raise ModelUnavailable("visual model artifacts are missing; run python -m app.vision.train_all")
        x = to_array(img, int(self.meta["img_size"]))
        logits, emb = cnn_np.forward(self.cnn, x)
        probs = cnn_np.softmax(logits, float(self.meta.get("temperature", 1.0)))
        i = int(probs.argmax())
        return {"class": CLASSES[i], "confidence": float(probs[i]), "probs": probs, "embedding": emb,
                "emb_proj": S.project(emb, self.pca)}

    def advise(self, state: np.ndarray) -> tuple[str, list[float]]:
        if self.dqn is None:
            raise ModelUnavailable("decision agent artifacts are missing")
        q = mlp_forward(self.dqn, state[None])[0]
        return ACTIONS[int(q.argmax())], [round(float(v), 4) for v in q]

    @property
    def cnn_validated(self) -> bool:
        return bool(self.meta.get("cnn", {}).get("validated_for_alerts"))

    @property
    def dqn_validated(self) -> bool:
        return bool(self.meta.get("dqn", {}).get("validated_for_alerts"))

    @property
    def version(self) -> str:
        if not self.meta.get("cnn"):
            return "unavailable"
        return f"{self.meta['cnn']['version']}+{self.meta['dqn']['version']}"


MODELS = VisualModels()
