"""Named brain systems, each a set of HCP-MMP1.0 parcels (see systems.yaml)."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from pathlib import Path

import numpy as np
import numpy.typing as npt
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from adcortex.analysis.atlas import Atlas
from adcortex.domain.models import Confidence


class SystemDef(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=r"^[a-z_]+$")
    label: str
    confidence: Confidence
    visual: bool
    parcels: tuple[str, ...] = Field(min_length=1)
    description: str
    citations: tuple[str, ...] = ()


class SystemCatalog(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: int
    systems: tuple[SystemDef, ...]
    citations: dict[str, str]

    @model_validator(mode="after")
    def _check_references(self) -> SystemCatalog:
        ids = [s.id for s in self.systems]
        if len(ids) != len(set(ids)):
            raise ValueError("System ids must be unique")
        for system in self.systems:
            missing = [c for c in system.citations if c not in self.citations]
            if missing:
                raise ValueError(f"System {system.id} cites unknown keys: {missing}")
        return self

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(s.id for s in self.systems)

    def get(self, system_id: str) -> SystemDef:
        for system in self.systems:
            if system.id == system_id:
                return system
        raise KeyError(system_id)

    def vertex_indices(self, atlas: Atlas) -> dict[str, npt.NDArray[np.intp]]:
        """Vertex indices per system. Raises KeyError for unknown parcels."""
        return {s.id: atlas.vertices_for(s.parcels) for s in self.systems}


def _default_path() -> Path:
    return Path(str(resources.files("adcortex.data") / "systems.yaml"))


@lru_cache(maxsize=4)
def load_systems(path: Path | None = None) -> SystemCatalog:
    raw = yaml.safe_load((path or _default_path()).read_text())
    return SystemCatalog.model_validate(raw)
