from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from adcortex.analysis.atlas import N_VERTICES, load_atlas
from adcortex.analysis.systems import SystemCatalog, load_systems


def test_atlas_covers_every_fsaverage5_vertex() -> None:
    atlas = load_atlas()

    assert atlas.vertex_parcel.shape == (N_VERTICES,)
    assert atlas.vertex_parcel.dtype == np.uint8
    assert len(atlas.parcels) == 181
    assert atlas.parcels[0].name == "???"
    assert int(atlas.vertex_parcel.max()) == 180


def test_atlas_parcel_spans_both_hemispheres() -> None:
    atlas = load_atlas()

    v1 = atlas.vertices_for(["V1"])

    assert (v1 < 10242).any()
    assert (v1 >= 10242).any()
    assert atlas.parcel("FFC").long_name == "Fusiform Face Complex"
    assert atlas.parcel("FFC").section == "Ventral Stream Visual Cortex"


def test_atlas_rejects_unknown_parcel() -> None:
    with pytest.raises(KeyError, match="NOPE"):
        load_atlas().vertices_for(["NOPE"])


def test_systems_catalog_is_consistent_with_atlas() -> None:
    catalog = load_systems()
    atlas = load_atlas()

    ids = [s.id for s in catalog.systems]
    assert ids == [
        "visual",
        "motion",
        "faces",
        "scenes",
        "sound",
        "speech",
        "social",
        "attention",
        "salience",
        "valuation",
    ]
    for system in catalog.systems:
        assert atlas.vertices_for(system.parcels).size > 0
        for key in system.citations:
            assert key in catalog.citations


def test_systems_do_not_share_parcels() -> None:
    parcels = [p for s in load_systems().systems for p in s.parcels]

    assert len(parcels) == len(set(parcels))


def test_vertex_indices_are_disjoint_per_system() -> None:
    indices = load_systems().vertex_indices(load_atlas())

    seen: set[int] = set()
    for vertices in indices.values():
        as_set = set(vertices.tolist())
        assert not seen & as_set
        seen |= as_set


def test_catalog_rejects_unknown_citation(tmp_path: Path) -> None:
    bad = tmp_path / "systems.yaml"
    bad.write_text(
        "version: 1\n"
        "systems:\n"
        "  - {id: x, label: X, confidence: high, visual: false,\n"
        "     parcels: [V1], description: d, citations: [missing]}\n"
        "citations: {}\n"
    )

    with pytest.raises(ValueError, match="missing"):
        load_systems(bad)


def test_catalog_validates_against_atlas() -> None:
    catalog = SystemCatalog.model_validate(
        {
            "version": 1,
            "systems": [
                {
                    "id": "x",
                    "label": "X",
                    "confidence": "high",
                    "visual": False,
                    "parcels": ["NOT_A_PARCEL"],
                    "description": "d",
                    "citations": [],
                }
            ],
            "citations": {},
        }
    )

    with pytest.raises(KeyError):
        catalog.vertex_indices(load_atlas())
