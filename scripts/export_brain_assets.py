"""Export the fsaverage5 meshes and the HCP-MMP1.0 atlas for the app.

TRIBE v2 predicts 20,484 cortical vertices on fsaverage5 (10,242 per
hemisphere, left first). This script writes the two files that give those
vertices anatomy:

* backend/src/adcortex/data/atlas_fsaverage5.json
    parcel list (180 HCP-MMP1.0 areas + medial wall) and a vertex -> parcel map
* frontend/public/brain/atlas.json   (same content, for hover labels)
* frontend/public/brain/mesh.json + mesh.bin
    pial and inflated surfaces (uint16-quantized), faces, and sulcal depth

The atlas follows tribev2.utils.get_hcp_labels: HCP-MMP1.0 projected to
fsaverage (Mills 2016, figshare 3498446), keeping the first 10,242 vertices
of each hemisphere, which are the fsaverage5 vertices (icosahedral nesting).

Run from the repo root (needs network for the two annotation files):

    uv run --python 3.12 --with nilearn --with nibabel --with numpy \
        scripts/export_brain_assets.py
"""

from __future__ import annotations

import base64
import hashlib
import json
import urllib.request
from pathlib import Path

import nibabel as nib
import numpy as np
from nilearn import datasets

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ATLAS = ROOT / "backend/src/adcortex/data/atlas_fsaverage5.json"
FRONTEND_DIR = ROOT / "frontend/public/brain"
CACHE = ROOT / ".adcortex-data/cache/atlas"

HEMI_SIZE = 10242
# MD5 sums are the ones MNE pins for the figshare originals; the OpenNeuro
# mirror (ds000248, MNE sample data) serves byte-identical files.
_OPENNEURO = (
    "https://s3.amazonaws.com/openneuro.org/ds000248/derivatives/freesurfer/"
    "subjects/fsaverage/label/{hemi}.HCPMMP1.annot"
)
ANNOT = {
    "lh": (
        [
            _OPENNEURO.format(hemi="lh"),
            "https://ndownloader.figshare.com/files/5528816",
        ],
        "46a102b59b2fb1bb4bd62d51bf02e975",
    ),
    "rh": (
        [
            _OPENNEURO.format(hemi="rh"),
            "https://ndownloader.figshare.com/files/5528819",
        ],
        "75e96b331940227bbcb07c1c791c2463",
    ),
}
LONG_NAMES_URL = (
    "https://raw.githubusercontent.com/netstim/leaddbs/"
    "master/ext_libs/dsi_studio/atlas/human/HCPex_abbreviations.txt"
)

# Glasser et al. (2016) section groupings, as implemented in
# mne.datasets.fetch_hcp_mmp_parcellation(combine=True).
SECTIONS: list[tuple[str, tuple[str, ...]]] = [
    ("Primary Visual Cortex (V1)", ("V1",)),
    ("Early Visual Cortex", ("V2", "V3", "V4")),
    ("Dorsal Stream Visual Cortex", ("V3A", "V3B", "V6", "V6A", "V7", "IPS1")),
    ("Ventral Stream Visual Cortex", ("V8", "VVC", "PIT", "FFC", "VMV1", "VMV2", "VMV3")),
    ("MT+ Complex and Neighboring Visual Areas", ("V3CD", "LO1", "LO2", "LO3", "V4t", "FST", "MT", "MST", "PH")),
    ("Somatosensory and Motor Cortex", ("4", "3a", "3b", "1", "2")),
    ("Paracentral Lobular and Mid Cingulate Cortex", ("24dd", "24dv", "6mp", "6ma", "SCEF", "5m", "5L", "5mv")),
    ("Premotor Cortex", ("55b", "6d", "6a", "FEF", "6v", "6r", "PEF")),
    ("Posterior Opercular Cortex", ("43", "FOP1", "OP4", "OP1", "OP2-3", "PFcm")),
    ("Early Auditory Cortex", ("A1", "LBelt", "MBelt", "PBelt", "RI")),
    ("Auditory Association Cortex", ("A4", "A5", "STSdp", "STSda", "STSvp", "STSva", "STGa", "TA2")),
    ("Insular and Frontal Opercular Cortex", ("52", "PI", "Ig", "PoI1", "PoI2", "FOP2", "FOP3", "MI", "AVI", "AAIC", "Pir", "FOP4", "FOP5")),
    ("Medial Temporal Cortex", ("H", "PreS", "EC", "PeEc", "PHA1", "PHA2", "PHA3")),
    ("Lateral Temporal Cortex", ("PHT", "TE1p", "TE1m", "TE1a", "TE2p", "TE2a", "TGv", "TGd", "TF")),
    ("Temporo-Parieto-Occipital Junction", ("TPOJ1", "TPOJ2", "TPOJ3", "STV", "PSL")),
    ("Superior Parietal Cortex", ("LIPv", "LIPd", "VIP", "AIP", "MIP", "7PC", "7AL", "7Am", "7PL", "7Pm")),
    ("Inferior Parietal Cortex", ("PGp", "PGs", "PGi", "PFm", "PF", "PFt", "PFop", "IP0", "IP1", "IP2")),
    ("Posterior Cingulate Cortex", ("DVT", "ProS", "POS1", "POS2", "RSC", "v23ab", "d23ab", "31pv", "31pd", "31a", "23d", "23c", "PCV", "7m")),
    ("Anterior Cingulate and Medial Prefrontal Cortex", ("33pr", "p24pr", "a24pr", "p24", "a24", "p32pr", "a32pr", "d32", "p32", "s32", "8BM", "9m", "10v", "10r", "25")),
    ("Orbital and Polar Frontal Cortex", ("47s", "47m", "a47r", "11l", "13l", "a10p", "p10p", "10pp", "10d", "OFC", "pOFC")),
    ("Inferior Frontal Cortex", ("44", "45", "IFJp", "IFJa", "IFSp", "IFSa", "47l", "p47r")),
    ("DorsoLateral Prefrontal Cortex", ("8C", "8Av", "i6-8", "s6-8", "SFL", "8BL", "9p", "9a", "8Ad", "p9-46v", "a9-46v", "46", "9-46d")),
]  # fmt: skip
MEDIAL_WALL = "???"
ACKNOWLEDGMENT = (
    "Data were provided [in part] by the Human Connectome Project, WU-Minn "
    "Consortium (Principal Investigators: David Van Essen and Kamil Ugurbil; "
    "1U54MH091657) funded by the 16 NIH Institutes and Centers that support "
    "the NIH Blueprint for Neuroscience Research; and by the McDonnell Center "
    "for Systems Neuroscience at Washington University."
)


def download(urls: str | list[str], dest: Path, md5: str | None = None) -> Path:
    """Fetch the first URL that works; verify the MD5 when one is given."""
    candidates = [urls] if isinstance(urls, str) else urls
    errors: list[str] = []
    for url in candidates:
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            request = urllib.request.Request(
                url, headers={"User-Agent": "adcortex-assets"}
            )
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    dest.write_bytes(response.read())
            except OSError as exc:
                errors.append(f"{url}: {exc}")
                continue
        if md5 is None or hashlib.md5(dest.read_bytes()).hexdigest() == md5:
            return dest
        errors.append(f"{url}: checksum mismatch")
        dest.unlink()
    raise SystemExit("Download failed:\n" + "\n".join(errors))


def long_names() -> dict[str, str]:
    path = download(LONG_NAMES_URL, CACHE / "HCPex_abbreviations.txt")
    names: dict[str, str] = {}
    for line in path.read_text().splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[1].endswith("_L"):
            short = parts[1].removesuffix("_L")
            names[short] = parts[2].removesuffix("_L").replace("_", " ")
    return names


def parcel_table() -> list[dict[str, object]]:
    names = long_names()
    table: list[dict[str, object]] = [
        {"id": 0, "name": MEDIAL_WALL, "long_name": "Medial wall", "section": ""}
    ]
    for section, members in SECTIONS:
        for short in members:
            table.append(
                {
                    "id": len(table),
                    "name": short,
                    "long_name": names.get(short, short),
                    "section": section,
                }
            )
    assert len(table) == 181, len(table)
    return table


def vertex_parcels(table: list[dict[str, object]]) -> np.ndarray:
    index = {str(p["name"]): int(str(p["id"])) for p in table}
    out = []
    for hemi in ("lh", "rh"):
        urls, md5 = ANNOT[hemi]
        path = download(urls, CACHE / f"{hemi}.HCPMMP1.annot", md5)
        labels, _ctab, raw_names = nib.freesurfer.read_annot(str(path))
        decoded = [n.decode() for n in raw_names]
        short = [n[2:].removesuffix("_ROI") if n != MEDIAL_WALL else n for n in decoded]
        lut = np.array([index[s] for s in short], dtype=np.uint8)
        hemi_labels = labels[:HEMI_SIZE]
        # -1 marks vertices outside every label; treat them as medial wall.
        out.append(np.where(hemi_labels >= 0, lut[np.clip(hemi_labels, 0, None)], 0))
    vertex = np.concatenate(out).astype(np.uint8)
    assert vertex.shape == (2 * HEMI_SIZE,)
    return vertex


def load_surface(path: str) -> tuple[np.ndarray, np.ndarray]:
    gii = nib.load(path)
    coords = gii.darrays[0].data.astype(np.float32)
    faces = gii.darrays[1].data.astype(np.int64)
    assert coords.shape == (HEMI_SIZE, 3), coords.shape
    return coords, faces


def quantize(coords: np.ndarray) -> tuple[np.ndarray, list[float], list[float]]:
    lo, hi = coords.min(axis=0), coords.max(axis=0)
    q = np.round((coords - lo) / (hi - lo) * 65535).astype("<u2")
    return q, lo.round(4).tolist(), hi.round(4).tolist()


def build_mesh(parcels: np.ndarray) -> tuple[bytes, dict[str, object]]:
    fs = datasets.fetch_surf_fsaverage("fsaverage5")
    surfaces: dict[str, dict[str, np.ndarray]] = {"pial": {}, "inflated": {}}
    faces: dict[str, np.ndarray] = {}
    for hemi in ("left", "right"):
        pial, f = load_surface(fs[f"pial_{hemi}"])
        infl, f2 = load_surface(fs[f"infl_{hemi}"])
        assert np.array_equal(f, f2)
        surfaces["pial"][hemi] = pial
        surfaces["inflated"][hemi] = infl
        faces[hemi] = f
    # Inflated hemispheres overlap at the midline; pull them apart.
    gap = 6.0
    left, right = (
        surfaces["inflated"]["left"].copy(),
        surfaces["inflated"]["right"].copy(),
    )
    left[:, 0] -= left[:, 0].max() + gap / 2
    right[:, 0] -= right[:, 0].min() - gap / 2
    surfaces["inflated"] = {"left": left, "right": right}

    chunks: list[bytes] = []
    manifest: dict[str, object] = {
        "format": 1,
        "hemisphere_vertices": HEMI_SIZE,
        "buffers": {},
    }
    buffers: dict[str, object] = {}
    offset = 0

    def add(name: str, data: np.ndarray, **extra: object) -> None:
        nonlocal offset
        raw = data.tobytes()
        buffers[name] = {
            "offset": offset,
            "length": len(raw),
            "dtype": data.dtype.str.lstrip("<|"),
            **extra,
        }
        chunks.append(raw)
        offset += len(raw)
        pad = (-offset) % 4
        if pad:
            chunks.append(b"\0" * pad)
            offset += pad

    for surface, hemis in surfaces.items():
        for hemi, coords in hemis.items():
            q, lo, hi = quantize(coords)
            add(f"{surface}.{hemi}.position", q, min=lo, max=hi)
    for hemi, f in faces.items():
        assert f.max() < 65536
        add(f"faces.{hemi}", f.astype("<u2"))
    sulc = np.concatenate(
        [
            np.asarray(nib.load(fs[f"sulc_{h}"]).darrays[0].data)
            for h in ("left", "right")
        ]
    )
    sulc_u8 = np.clip((sulc - sulc.min()) / (sulc.max() - sulc.min()) * 255, 0, 255)
    add("sulc", sulc_u8.astype(np.uint8))
    add("parcel", parcels)
    manifest["buffers"] = buffers
    manifest["bytes"] = offset
    return b"".join(chunks), manifest


def main() -> None:
    table = parcel_table()
    parcels = vertex_parcels(table)
    atlas = {
        "source": (
            "HCP-MMP1.0 (Glasser et al., 2016, Nature 536:171-178) projected to "
            "fsaverage (figshare 3498446); first 10,242 vertices per hemisphere "
            "(fsaverage5), left hemisphere first."
        ),
        "license": "HCP Open Access Data Use Terms (derived data).",
        "acknowledgment": ACKNOWLEDGMENT,
        "hemisphere_vertices": HEMI_SIZE,
        "sections": [name for name, _ in SECTIONS],
        "parcels": table,
        "vertex_parcel_b64": base64.b64encode(parcels.tobytes()).decode(),
    }
    text = json.dumps(atlas, separators=(",", ":"))
    BACKEND_ATLAS.write_text(text)
    FRONTEND_DIR.mkdir(parents=True, exist_ok=True)
    (FRONTEND_DIR / "atlas.json").write_text(text)
    blob, manifest = build_mesh(parcels)
    (FRONTEND_DIR / "mesh.bin").write_bytes(blob)
    (FRONTEND_DIR / "mesh.json").write_text(json.dumps(manifest, indent=1))
    counts = np.bincount(parcels, minlength=181)
    print(f"atlas: {len(table)} parcels, medial wall {counts[0]} vertices")
    print(f"mesh.bin: {len(blob) / 1024:.0f} KiB")


if __name__ == "__main__":
    main()
