"""HCP-MMP1.0 parcels on the fsaverage5 vertices TRIBE v2 predicts.

The JSON file is produced by `scripts/export_brain_assets.py`.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path

import numpy as np
import numpy.typing as npt

HEMI_VERTICES = 10242
N_VERTICES = 2 * HEMI_VERTICES


@dataclass(frozen=True)
class Parcel:
    id: int
    name: str
    long_name: str
    section: str


@dataclass(frozen=True)
class Atlas:
    parcels: tuple[Parcel, ...]
    vertex_parcel: npt.NDArray[np.uint8]
    acknowledgment: str

    def parcel(self, name: str) -> Parcel:
        for parcel in self.parcels:
            if parcel.name == name:
                return parcel
        raise KeyError(f"Unknown HCP-MMP1.0 parcel: {name}")

    def vertices_for(self, names: Iterable[str]) -> npt.NDArray[np.intp]:
        """Indices of all vertices (both hemispheres) in the named parcels."""
        ids = [self.parcel(name).id for name in names]
        return np.flatnonzero(np.isin(self.vertex_parcel, ids))


def _default_path() -> Path:
    return Path(str(resources.files("adcortex.data") / "atlas_fsaverage5.json"))


@lru_cache(maxsize=4)
def load_atlas(path: Path | None = None) -> Atlas:
    raw = json.loads((path or _default_path()).read_text())
    vertex_parcel = np.frombuffer(
        base64.b64decode(raw["vertex_parcel_b64"]), dtype=np.uint8
    ).copy()
    vertex_parcel.setflags(write=False)
    if vertex_parcel.shape != (N_VERTICES,):
        raise ValueError(f"Atlas has {vertex_parcel.size} vertices, need {N_VERTICES}")
    parcels = tuple(
        Parcel(
            id=int(p["id"]),
            name=str(p["name"]),
            long_name=str(p["long_name"]),
            section=str(p["section"]),
        )
        for p in raw["parcels"]
    )
    return Atlas(
        parcels=parcels,
        vertex_parcel=vertex_parcel,
        acknowledgment=str(raw.get("acknowledgment", "")),
    )
