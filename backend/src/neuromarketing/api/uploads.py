"""Turn the upload form into a stored, queued analysis.

The media is probed here, before anything is stored, so a wrong track type
or a clip outside the length limits fails at once instead of minutes later
in the pipeline.
"""

from __future__ import annotations

import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Protocol

from neuromarketing.api.actions import clean_text, start_analysis
from neuromarketing.api.context import AppContext
from neuromarketing.api.middleware import upload_too_large
from neuromarketing.domain.errors import InvalidInputError, PayloadTooLargeError
from neuromarketing.domain.ids import new_analysis_id
from neuromarketing.domain.languages import normalize_language
from neuromarketing.domain.models import (
    Analysis,
    AnalysisMeta,
    MediaKind,
    SourceFile,
    utcnow,
)
from neuromarketing.media.probe import (
    AUDIO_EXTENSIONS,
    VIDEO_EXTENSIONS,
    probe,
    validate_media,
)
from neuromarketing.media.speech import check_speech_language, speech_language
from neuromarketing.storage.repository import SCRIPT, source_name

NAME_CHARS = 120
FILENAME_CHARS = 255
SCRIPT_NAME_WORDS = 8
CHUNK = 1024 * 1024
# The Audio tab also takes videos and analyzes their sound.
ACCEPTED = {
    MediaKind.VIDEO: VIDEO_EXTENSIONS,
    MediaKind.AUDIO: AUDIO_EXTENSIONS | VIDEO_EXTENSIONS,
}


class IncomingFile(Protocol):
    """The parts of an uploaded file this module reads."""

    filename: str | None
    size: int | None
    file: BinaryIO


@dataclass(frozen=True)
class UploadForm:
    kind: MediaKind
    file: IncomingFile | None = None
    script: str | None = None
    name: str | None = None
    language: str | None = None


def create_analysis(ctx: AppContext, form: UploadForm) -> Analysis:
    language = normalize_language(form.language)
    name = _requested_name(form.name)
    if form.kind is MediaKind.TEXT:
        meta = _from_script(ctx, form.script, name, language)
    else:
        meta = _from_file(ctx, form, name, language)
    return start_analysis(ctx, meta)


def _from_file(
    ctx: AppContext, form: UploadForm, name: str | None, language: str
) -> AnalysisMeta:
    upload = form.file
    if upload is None or not upload.filename:
        raise InvalidInputError("Choose a file to upload.")
    settings = ctx.settings
    too_large = upload_too_large(settings.max_upload_mb)
    if upload.size is not None and upload.size > settings.max_upload_bytes:
        raise PayloadTooLargeError(too_large)
    filename = _filename(upload.filename)
    extension = _extension(filename, form.kind)
    analysis_id = new_analysis_id()
    with tempfile.TemporaryDirectory(prefix="nm-upload-") as tmp:
        local = Path(tmp) / source_name(extension)
        size, sha256 = _save(upload.file, local, settings.max_upload_bytes, too_large)
        validate_media(
            probe(local),
            form.kind,
            min_s=settings.min_duration_s,
            max_s=settings.max_duration_s,
        )
        ctx.repo.put_artifacts(analysis_id, {source_name(extension): local})
    stem = clean_text(PurePosixPath(filename).stem)[:NAME_CHARS]
    return AnalysisMeta(
        id=analysis_id,
        name=name or stem or "Untitled",
        kind=form.kind,
        created_at=utcnow(),
        source=SourceFile(
            filename=filename, extension=extension, size_bytes=size, sha256=sha256
        ),
        language=language,
    )


def _from_script(
    ctx: AppContext, script: str | None, name: str | None, language: str
) -> AnalysisMeta:
    text = (script or "").strip()
    low, high = ctx.settings.min_script_chars, ctx.settings.max_script_chars
    if len(text) < low:
        raise InvalidInputError(f"The script needs at least {low} characters.")
    if len(text) > high:
        raise InvalidInputError(f"The script can have at most {high} characters.")
    check_speech_language(speech_language(language))
    data = text.encode()
    analysis_id = new_analysis_id()
    ctx.repo.put_artifact_bytes(analysis_id, SCRIPT, data)
    return AnalysisMeta(
        id=analysis_id,
        name=name or _first_words(text),
        kind=MediaKind.TEXT,
        created_at=utcnow(),
        source=SourceFile(
            filename="script.txt",
            extension=".txt",
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        ),
        language=language,
    )


def _requested_name(raw: str | None) -> str | None:
    if raw is None:
        return None
    name = clean_text(raw)
    if len(name) > NAME_CHARS:
        raise InvalidInputError(f"The name can have at most {NAME_CHARS} characters.")
    return name or None


def _filename(raw: str) -> str:
    """The base name only: browsers on Windows may send a full path."""
    return clean_text(PurePosixPath(raw.replace("\\", "/")).name)[:FILENAME_CHARS]


def _extension(filename: str, kind: MediaKind) -> str:
    suffix = PurePosixPath(filename).suffix.lower()
    accepted = ACCEPTED[kind]
    if suffix not in accepted:
        shown = suffix or filename[:40]
        raise InvalidInputError(
            f"'{shown}' files are not supported. Use one of: "
            + " ".join(sorted(accepted))
        )
    return suffix


def _first_words(text: str) -> str:
    words = clean_text(text).split()
    name = " ".join(words[:SCRIPT_NAME_WORDS])
    if len(words) > SCRIPT_NAME_WORDS:
        name += "…"
    return name[:NAME_CHARS]


def _save(src: BinaryIO, dst: Path, limit: int, too_large: str) -> tuple[int, str]:
    """Copy the upload while hashing it; returns (size, sha256)."""
    src.seek(0)
    digest = hashlib.sha256()
    size = 0
    with dst.open("wb") as out:
        while chunk := src.read(CHUNK):
            size += len(chunk)
            if size > limit:
                raise PayloadTooLargeError(too_large)
            digest.update(chunk)
            out.write(chunk)
    if size == 0:
        raise InvalidInputError("The file is empty.")
    return size, digest.hexdigest()
