"""Deterministic synthetic predictions for development and tests.

The mock follows the media it is given, so the UI behaves sensibly without a
GPU: visual systems respond to scene cuts, sound and speech follow loudness,
and the other systems drift slowly. Everything is seeded from the file's
bytes, so the same clip always gives the same result. None of it is a brain
prediction; it only exercises the pipeline.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import numpy.typing as npt

from adcortex.analysis.atlas import N_VERTICES, load_atlas
from adcortex.analysis.systems import SystemCatalog, load_systems
from adcortex.brain.base import BrainPrediction, BrainRequest
from adcortex.brain.transcript import spread_words
from adcortex.domain.errors import MediaError
from adcortex.media.envelope import audio_envelope
from adcortex.media.scenes import detect_cuts, seconds_grid

logger = logging.getLogger(__name__)

Curve = npt.NDArray[np.float64]

HASH_BYTES = 4 * 1024 * 1024
CUT_THRESHOLD = 12.0
ENVELOPE_HZ = 10
VERTEX_NOISE = 0.05
SYSTEM_NOISE = 0.15
QUIET = 0.05

# How strongly each feature drives each system (unknown systems only drift).
DRIVERS: dict[str, dict[str, float]] = {
    "visual": {"cuts": 1.4, "drift": 0.4},
    "motion": {"cuts": 0.9, "drift": 0.6},
    "faces": {"cuts": 0.3, "drift": 0.9},
    "scenes": {"cuts": 0.8, "drift": 0.5},
    "sound": {"loudness": 1.2, "drift": 0.2},
    "speech": {"speech": 1.0, "drift": 0.4},
    "social": {"speech": 0.4, "drift": 0.7},
    "attention": {"cuts": 0.6, "drift": 0.6},
    "salience": {"change": 0.8, "cuts": 0.4, "drift": 0.4},
    "valuation": {"drift": 0.8},
}


class MockBrain:
    name = "mock"

    def __init__(self, catalog: SystemCatalog | None = None) -> None:
        self._catalog = catalog or load_systems()
        self._atlas = load_atlas()
        self._indices = self._catalog.vertex_indices(self._atlas)

    def warmup(self) -> None:
        return None

    def predict(self, request: BrainRequest) -> BrainPrediction:
        n = seconds_grid(request.duration_s)
        rng = np.random.default_rng(_seed(request))
        features = {
            "cuts": _cuts(request.media, n) if request.kind == "video" else np.zeros(n),
            **_loudness_features(request.media, n),
        }
        signals = self._signals(request, n, rng, features)
        return BrainPrediction(
            preds=self._paint(signals, n, rng),
            times=np.arange(n, dtype=np.float64),
            words=spread_words(request.script, request.duration_s),
            language=None if request.language == "auto" else request.language,
            model=self.name,
        )

    def _signals(
        self,
        request: BrainRequest,
        n: int,
        rng: np.random.Generator,
        features: Mapping[str, Curve],
    ) -> dict[str, Curve]:
        signals: dict[str, Curve] = {}
        for system in self._catalog.systems:
            noise = rng.normal(0.0, SYSTEM_NOISE, n)
            if system.visual and request.kind != "video":
                signals[system.id] = QUIET * noise
                continue
            weights = DRIVERS.get(system.id, {"drift": 1.0})
            signal = noise + weights.get("drift", 0.0) * _drift(rng, n)
            for feature, weight in weights.items():
                if feature != "drift":
                    signal = signal + weight * _zscore(features[feature])
            signals[system.id] = signal
        return signals

    def _paint(
        self, signals: Mapping[str, Curve], n: int, rng: np.random.Generator
    ) -> npt.NDArray[np.float32]:
        """Spread system signals over their vertices with per-parcel gains."""
        parcels = self._atlas.vertex_parcel
        gains = rng.uniform(0.6, 1.4, int(parcels.max()) + 1)[parcels]
        preds = rng.normal(0.0, VERTEX_NOISE, (n, N_VERTICES))
        in_system = np.zeros(N_VERTICES, dtype=bool)
        for system_id, vertices in self._indices.items():
            preds[:, vertices] += signals[system_id][:, None] * gains[None, vertices]
            in_system[vertices] = True
        background = 0.3 * np.mean(list(signals.values()), axis=0)
        preds[:, ~in_system] += background[:, None] * gains[None, ~in_system]
        return preds.astype(np.float32)


def _seed(request: BrainRequest) -> int:
    digest = hashlib.sha256(str(request.seed).encode())
    try:
        with request.media.open("rb") as fh:
            digest.update(fh.read(HASH_BYTES))
    except OSError:
        digest.update(str(request.media).encode())
    return int.from_bytes(digest.digest()[:8], "little")


def _cuts(media: Path, n: int) -> Curve:
    """Impulse at the first frame and at each cut, decaying over one second."""
    try:
        cuts = detect_cuts(media, threshold=CUT_THRESHOLD)
    except MediaError:
        logger.debug("Mock: no scene cuts for %s", media)
        cuts = []
    signal = np.zeros(n)
    for t in [0.0, *cuts]:
        second = int(np.floor(t + 0.05))
        if 0 <= second < n:
            signal[second] += 1.0
            if second + 1 < n:
                signal[second + 1] += 0.5
    return signal


def _loudness_features(media: Path, n: int) -> dict[str, Curve]:
    try:
        envelope = np.asarray(audio_envelope(media, hz=ENVELOPE_HZ), dtype=np.float64)
    except MediaError:
        logger.debug("Mock: no loudness for %s", media)
        envelope = np.zeros(0)
    loudness = np.zeros(n)
    for second in range(n):
        window = envelope[second * ENVELOPE_HZ : (second + 1) * ENVELOPE_HZ]
        if window.size:
            loudness[second] = window.mean()
    return {
        "loudness": loudness,
        "speech": _smooth(loudness, 3),
        "change": np.abs(np.diff(loudness, prepend=loudness[:1])),
    }


def _drift(rng: np.random.Generator, n: int) -> Curve:
    return _zscore(_smooth(np.cumsum(rng.normal(0.0, 1.0, n)), 3))


def _smooth(values: Curve, window: int) -> Curve:
    if values.size < window:
        return values.copy()
    kernel = np.ones(window) / window
    padded = np.pad(values, (window // 2, window - 1 - window // 2), mode="edge")
    return np.convolve(padded, kernel, mode="valid")


def _zscore(values: Curve) -> Curve:
    std = values.std()
    if std < 1e-9:
        return np.zeros_like(values)
    return (values - values.mean()) / std
