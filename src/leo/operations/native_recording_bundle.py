"""Read a pinned native publication using only the public manifest and ports."""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from leo.contracts.native_journal_recording import (
    NativeJournalRecordingV1,
    NativeJournalSourceBindingV1,
    NativeRecordingBundleV1,
)
from leo.operations.native_journal_recording import _verified_json, review_native_recording

LIMITS = {
    "journal.glrj": 128 * 1024 * 1024,
    "recording.json": 256 * 1024 * 1024,
    "source-binding.json": 65536,
    "owner-receipt.json": 4 * 1024 * 1024,
    "coarse-protocol.json": 1024 * 1024,
    "coarse-summary.json": 1024 * 1024,
    "coarse-final-snapshot.txt": 16384,
}


@dataclass(frozen=True)
class NativeRecordingBundle:
    root: Path
    manifest_sha256: str
    manifest: NativeRecordingBundleV1
    recording: NativeJournalRecordingV1
    source_binding: NativeJournalSourceBindingV1


def load_native_bundle(path: Path, *, expected_sha256: str) -> NativeRecordingBundle:
    # A caller may explicitly select a manifest via a symlink; payloads must be
    # regular files inside that resolved publication directory.
    path = path.resolve(strict=True)
    manifest = NativeRecordingBundleV1.model_validate_json(
        _verified_json(path, expected_sha256, 65536)
    )
    root = path.parent
    for name, artifact in manifest.artifacts.items():
        target = root / name
        if artifact.bytes > LIMITS[name] or not stat.S_ISREG(target.lstat().st_mode):
            raise ValueError("native bundle payload is not a bounded regular file")
        descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size != artifact.bytes:
                raise ValueError("native bundle payload type or byte count differs")
            if hashlib.file_digest(stream, "sha256").hexdigest() != artifact.sha256:
                raise ValueError("native bundle payload digest differs: " + name)
    recording = NativeJournalRecordingV1.model_validate_json(
        _verified_json(
            root / "recording.json",
            manifest.artifacts["recording.json"].sha256,
            LIMITS["recording.json"],
        )
    )
    binding = NativeJournalSourceBindingV1.model_validate_json(
        _verified_json(
            root / "source-binding.json", manifest.artifacts["source-binding.json"].sha256, 65536
        )
    )
    binding.require_recording(recording, export_sha256=manifest.artifacts["recording.json"].sha256)
    manifest.require_binding(binding)
    if recording.journal_bytes != manifest.artifacts["journal.glrj"].bytes:
        raise ValueError("native bundle raw journal byte count differs from recording")
    return NativeRecordingBundle(root, expected_sha256, manifest, recording, binding)


def review_native_bundle(path: Path, output: Path, *, expected_sha256: str) -> dict:
    bundle = load_native_bundle(path, expected_sha256=expected_sha256)
    # The existing adapter rechecks both files against these pinned hashes;
    # mutation after bundle validation cannot change the reviewed input silently.
    return review_native_recording(
        bundle.root / "recording.json",
        output,
        expected_sha256=bundle.manifest.artifacts["recording.json"].sha256,
        source_binding=bundle.root / "source-binding.json",
        expected_binding_sha256=bundle.manifest.artifacts["source-binding.json"].sha256,
    )
