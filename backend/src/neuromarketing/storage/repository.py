"""Analyses as folders of JSON documents and media artifacts.

Layout inside the store:

    analyses/<id>/meta.json      AnalysisMeta     written by the web tier
    analyses/<id>/state.json     AnalysisState    written by the pipeline
    analyses/<id>/job.json       JobRef           written by the dispatcher
    analyses/<id>/result.json    AnalysisResult   written by the pipeline
    analyses/<id>/report.json    StoredReport     written by the pipeline
    analyses/<id>/fingerprint    the analysis's entry in fingerprints/
    analyses/<id>/<artifact>     media, keyframes, brain frames, prediction
    fingerprints/<sha256>        id of a finished analysis of identical input
    comparisons/<a>--<b>.json    StoredComparison

Each document has a single writer, so concurrent containers never overwrite
each other's changes. Ids start with their creation time, so sorting folder
names sorts the history without reading any document.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import BaseModel, ValidationError

from neuromarketing.domain.errors import NotFoundError
from neuromarketing.domain.ids import is_analysis_id, require_analysis_id
from neuromarketing.domain.models import (
    Analysis,
    AnalysisMeta,
    AnalysisResult,
    AnalysisState,
    JobRef,
    StoredComparison,
    StoredReport,
)
from neuromarketing.storage.base import ArtifactStore

logger = logging.getLogger(__name__)

ANALYSES = "analyses"
FINGERPRINTS = "fingerprints"
COMPARISONS = "comparisons"

META = "meta.json"
STATE = "state.json"
JOB = "job.json"
RESULT = "result.json"
REPORT = "report.json"
FINGERPRINT = "fingerprint"

# Artifacts, relative to the analysis folder.
PREVIEW_VIDEO = "preview.mp4"
PREVIEW_AUDIO = "preview.m4a"
AUDIO = "audio.wav"
LLM_VIDEO = "llm.mp4"
PREDICTION = "prediction.npz"
FRAMES = "frames.bin"
STRIP = "strip.jpg"
SCRIPT = "script.txt"
KEYFRAMES = "keyframes"

_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")


def source_name(extension: str) -> str:
    return f"source{extension.lower()}"


def keyframe_name(scene_index: int) -> str:
    return f"{KEYFRAMES}/{scene_index:03d}.jpg"


class AnalysisRepository:
    def __init__(self, store: ArtifactStore) -> None:
        self.store = store

    # ── analyses ───────────────────────────────────────────────────────────

    def create(self, meta: AnalysisMeta, state: AnalysisState) -> None:
        # meta.json marks the analysis as existing, so it is written last.
        self.save_state(meta.id, state)
        self.save_meta(meta)

    def exists(self, analysis_id: str) -> bool:
        return is_analysis_id(analysis_id) and self.store.exists(
            self._doc(analysis_id, META)
        )

    def get(self, analysis_id: str) -> Analysis:
        require_analysis_id(analysis_id)
        docs = self.store.read_many(
            [self._doc(analysis_id, META), self._doc(analysis_id, STATE)]
        )
        analysis = self._assemble(analysis_id, docs)
        if analysis is None:
            raise NotFoundError("Analysis not found.")
        return analysis

    def history(self, *, limit: int = 50, before: str | None = None) -> list[Analysis]:
        """Newest first. `before` continues after the last id of the previous page."""
        ids = sorted(
            (name for name in self.store.list_dir(ANALYSES) if is_analysis_id(name)),
            reverse=True,
        )
        if before is not None:
            ids = [i for i in ids if i < before]
        page = ids[:limit]
        paths = [self._doc(i, name) for i in page for name in (META, STATE)]
        docs = self.store.read_many(paths)
        found = (self._assemble(i, docs) for i in page)
        return [analysis for analysis in found if analysis is not None]

    def save_meta(self, meta: AnalysisMeta) -> None:
        self._write(self._doc(meta.id, META), meta)

    def get_state(self, analysis_id: str) -> AnalysisState:
        return self._read(analysis_id, STATE, AnalysisState, "Analysis not found.")

    def save_state(self, analysis_id: str, state: AnalysisState) -> None:
        self._write(self._doc(analysis_id, STATE), state)

    def get_job(self, analysis_id: str) -> JobRef | None:
        return self._read_optional(analysis_id, JOB, JobRef)

    def save_job(self, analysis_id: str, job: JobRef) -> None:
        self._write(self._doc(analysis_id, JOB), job)

    def clear_job(self, analysis_id: str) -> None:
        self.store.remove(self._doc(analysis_id, JOB))

    def get_result(self, analysis_id: str) -> AnalysisResult:
        return self._read(
            analysis_id, RESULT, AnalysisResult, "The results are not ready yet."
        )

    def save_result(self, analysis_id: str, result: AnalysisResult) -> None:
        self._write(self._doc(analysis_id, RESULT), result)

    def get_report(self, analysis_id: str) -> StoredReport | None:
        return self._read_optional(analysis_id, REPORT, StoredReport)

    def save_report(self, analysis_id: str, report: StoredReport) -> None:
        self._write(self._doc(analysis_id, REPORT), report)

    def delete(self, analysis_id: str) -> None:
        """Remove the analysis, its fingerprint entry, and comparisons using it."""
        if not self.exists(analysis_id):
            raise NotFoundError("Analysis not found.")
        fingerprint = self._read_text(self._doc(analysis_id, FINGERPRINT))
        self.store.remove(f"{ANALYSES}/{analysis_id}")
        if (
            fingerprint
            and self._read_text(f"{FINGERPRINTS}/{fingerprint}") == analysis_id
        ):
            self.store.remove(f"{FINGERPRINTS}/{fingerprint}")
        for name in self.store.list_dir(COMPARISONS):
            if analysis_id in name.removesuffix(".json").split("--"):
                self.store.remove(f"{COMPARISONS}/{name}")

    def discard(self, analysis_id: str) -> None:
        """Remove files a job wrote after its analysis was deleted."""
        self.store.remove(f"{ANALYSES}/{require_analysis_id(analysis_id)}")

    # ── artifacts ──────────────────────────────────────────────────────────

    def put_artifacts(self, analysis_id: str, files: Mapping[str, Path]) -> None:
        self.store.upload(
            {self._doc(analysis_id, name): src for name, src in files.items()}
        )

    def put_artifact_bytes(self, analysis_id: str, name: str, data: bytes) -> None:
        self.store.write_bytes(self._doc(analysis_id, name), data)

    def has_artifact(self, analysis_id: str, name: str) -> bool:
        return self.store.exists(self._doc(analysis_id, name))

    def read_artifacts(
        self, analysis_id: str, names: Sequence[str]
    ) -> dict[str, bytes | None]:
        """Read several artifacts at once; missing ones map to None."""
        found = self.store.read_many([self._doc(analysis_id, n) for n in names])
        return {name: found.get(self._doc(analysis_id, name)) for name in names}

    def read_artifact(self, analysis_id: str, name: str) -> bytes:
        try:
            return self.store.read_bytes(self._doc(analysis_id, name))
        except FileNotFoundError:
            raise NotFoundError("File not found.") from None

    def local_artifact(self, analysis_id: str, name: str) -> Path:
        try:
            return self.store.local_path(self._doc(analysis_id, name))
        except FileNotFoundError:
            raise NotFoundError("File not found.") from None

    def download_artifact(self, analysis_id: str, name: str, dst: Path) -> Path:
        try:
            self.store.download(self._doc(analysis_id, name), dst)
        except FileNotFoundError:
            raise NotFoundError("File not found.") from None
        return dst

    def list_artifacts(self, analysis_id: str, folder: str) -> list[str]:
        return self.store.list_dir(self._doc(analysis_id, folder))

    # ── repeat uploads ─────────────────────────────────────────────────────

    def remember_fingerprint(self, fingerprint: str, analysis_id: str) -> None:
        """Record that `analysis_id` holds the prediction for this input."""
        _check_fingerprint(fingerprint)
        self.store.write_bytes(
            self._doc(analysis_id, FINGERPRINT), fingerprint.encode()
        )
        self.store.write_bytes(f"{FINGERPRINTS}/{fingerprint}", analysis_id.encode())

    def find_fingerprint(self, fingerprint: str) -> str | None:
        """The analysis whose prediction can be reused for this input, if any."""
        _check_fingerprint(fingerprint)
        analysis_id = self._read_text(f"{FINGERPRINTS}/{fingerprint}")
        if analysis_id is None or not is_analysis_id(analysis_id):
            return None
        return (
            analysis_id
            if self.store.exists(self._doc(analysis_id, PREDICTION))
            else None
        )

    # ── comparisons ────────────────────────────────────────────────────────

    def save_comparison(self, comparison: StoredComparison) -> None:
        self._write(self._comparison(comparison.a_id, comparison.b_id), comparison)

    def get_comparison(self, a_id: str, b_id: str) -> StoredComparison | None:
        try:
            raw = self.store.read_bytes(self._comparison(a_id, b_id))
        except FileNotFoundError:
            return None
        return StoredComparison.model_validate_json(raw)

    # ── helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _doc(analysis_id: str, name: str) -> str:
        return f"{ANALYSES}/{require_analysis_id(analysis_id)}/{name}"

    @staticmethod
    def _comparison(a_id: str, b_id: str) -> str:
        pair = f"{require_analysis_id(a_id)}--{require_analysis_id(b_id)}"
        return f"{COMPARISONS}/{pair}.json"

    def _write(self, path: str, document: BaseModel) -> None:
        self.store.write_bytes(path, document.model_dump_json().encode())

    def _read[M: BaseModel](
        self, analysis_id: str, name: str, model: type[M], missing: str
    ) -> M:
        try:
            raw = self.store.read_bytes(self._doc(analysis_id, name))
        except FileNotFoundError:
            raise NotFoundError(missing) from None
        return model.model_validate_json(raw)

    def _read_optional[M: BaseModel](
        self, analysis_id: str, name: str, model: type[M]
    ) -> M | None:
        try:
            raw = self.store.read_bytes(self._doc(analysis_id, name))
        except FileNotFoundError:
            return None
        return model.model_validate_json(raw)

    def _read_text(self, path: str) -> str | None:
        try:
            return self.store.read_bytes(path).decode().strip()
        except FileNotFoundError:
            return None

    def _assemble(
        self, analysis_id: str, docs: Mapping[str, bytes | None]
    ) -> Analysis | None:
        meta = docs.get(self._doc(analysis_id, META))
        state = docs.get(self._doc(analysis_id, STATE))
        if meta is None or state is None:
            return None
        try:
            return Analysis(
                meta=AnalysisMeta.model_validate_json(meta),
                state=AnalysisState.model_validate_json(state),
            )
        except ValidationError:
            logger.warning(
                "Skipping unreadable analysis %s", analysis_id, exc_info=True
            )
            return None


def _check_fingerprint(fingerprint: str) -> None:
    if not _FINGERPRINT_RE.fullmatch(fingerprint):
        raise ValueError(f"Invalid fingerprint: {fingerprint!r}")
