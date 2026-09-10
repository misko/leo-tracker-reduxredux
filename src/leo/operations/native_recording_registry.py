"""Explicit local registration of pinned native publications; no radio I/O."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Literal

from leo.contracts.base import ContractModel
from leo.contracts.native_journal_recording import Digest
from leo.operations.native_recording_bundle import NativeRecordingBundle, load_native_bundle
from leo.presentation.native_recordings import (
    NativeRecordingDetailV1,
    NativeRecordingEntryV1,
    NativeRecordingListV1,
    NativeRecordingRowV1,
    NativeRecordingSummaryV1,
    NativeRecordingUnavailable,
)


class NativeRecordingRegistrationV1(ContractModel):
    schema_version: Literal[1] = 1
    manifest_path: str
    manifest_sha256: Digest


def _summary(bundle: NativeRecordingBundle) -> NativeRecordingSummaryV1:
    record, manifest = bundle.recording, bundle.manifest
    supported = [row.cfo_hz for row in record.measurements if row.supported]
    span = None
    if record.measurements:
        span = (
            int(record.measurements[-1].native_start_sample)
            - int(record.measurements[0].native_start_sample)
        ) / record.source_rate_hz
    return NativeRecordingSummaryV1(
        bundle_id=bundle.manifest_sha256,
        **{
            key: getattr(manifest, key)
            for key in (
                "serial",
                "boot_id",
                "fit_sha256",
                "visit",
                "epoch",
                "episode_index",
                "runtime_result",
                "owner_status",
                "evidence_mode",
            )
        },
        head_count=record.head_count,
        supported_count=record.supported_count,
        rejected_count=record.rejected_count,
        observed_start_span_s=span,
        supported_cfo_min_hz=min(supported) if supported else None,
        supported_cfo_max_hz=max(supported) if supported else None,
        frequency_reference=record.frequency_reference,
    )


class NativeRecordingRegistry:
    """Own registration paths; expose IDs only through the presentation port.

    Each read verifies current publication bytes. No catalog entry can turn a
    failed runtime or retrospectively bound evidence into scientific success.
    """

    def __init__(self, root: Path):
        if not root.is_absolute() or root.resolve().is_relative_to("/mnt/qnap01"):
            raise ValueError("native registry requires an absolute local directory")
        self.root = root.resolve()

    def register(self, manifest: Path, *, expected_sha256: str) -> str:
        selected = load_native_bundle(manifest, expected_sha256=expected_sha256)
        registration = NativeRecordingRegistrationV1(
            manifest_path=str(manifest.resolve()),
            manifest_sha256=expected_sha256,
        )
        raw = (registration.model_dump_json() + "\n").encode()
        try:
            self.root.mkdir(parents=True)
        except FileExistsError:
            if not self.root.is_dir():
                raise ValueError("native registry path is not a directory") from None
        else:
            self.root.chmod(0o755)
        target = self.root / (expected_sha256 + ".json")
        descriptor, name = tempfile.mkstemp(prefix=".registration-", dir=self.root)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                # Published metadata must be readable by the separate API user.
                os.fchmod(stream.fileno(), 0o644)
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(name, target)
            except FileExistsError:
                if target.is_symlink() or target.read_bytes() != raw:
                    raise ValueError(
                        "native registration already exists with different bytes"
                    ) from None
            directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            Path(name).unlink()
        return selected.manifest_sha256

    def _load(self, bundle_id: str) -> NativeRecordingBundle:
        if not re.fullmatch(r"[0-9a-f]{64}", bundle_id):
            raise KeyError(bundle_id)
        path = self.root / (bundle_id + ".json")
        if not path.exists() and not path.is_symlink():
            raise KeyError(bundle_id)
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 16384:
                raise ValueError("invalid registration file")
            raw = path.read_bytes()
            registration = NativeRecordingRegistrationV1.model_validate_json(raw)
            if registration.manifest_sha256 != bundle_id:
                raise ValueError("registration ID differs")
            manifest = Path(registration.manifest_path)
            if not manifest.is_absolute():
                raise ValueError("registration manifest must be absolute")
            return load_native_bundle(manifest, expected_sha256=bundle_id)
        except (ValueError, OSError) as error:
            raise NativeRecordingUnavailable("native recording integrity unavailable") from error

    def list_recordings(self, *, cursor: int = 0, limit: int = 20) -> NativeRecordingListV1:
        if cursor < 0 or not 1 <= limit <= 100:
            raise ValueError("invalid native recording page")
        ids = sorted(
            path.stem
            for path in self.root.glob("*.json")
            if re.fullmatch(r"[0-9a-f]{64}", path.stem)
        )
        items = []
        for bundle_id in ids[cursor : cursor + limit]:
            try:
                summary = _summary(self._load(bundle_id))
                items.append(
                    NativeRecordingEntryV1(bundle_id=bundle_id, summary=summary, error=None)
                )
            except (NativeRecordingUnavailable, KeyError):
                items.append(
                    NativeRecordingEntryV1(
                        bundle_id=bundle_id, summary=None, error="integrity_unavailable"
                    )
                )
        return NativeRecordingListV1(
            total=len(ids),
            next_cursor=cursor + limit if cursor + limit < len(ids) else None,
            items=tuple(items),
        )

    def get_recording(
        self, bundle_id: str, *, cursor: int = 0, limit: int = 200
    ) -> NativeRecordingDetailV1:
        if cursor < 0 or not 1 <= limit <= 1000:
            raise ValueError("invalid native measurement page")
        bundle = self._load(bundle_id)
        recording = bundle.recording
        origin = int(bundle.source_binding.native_origin)
        rows = []
        for measurement in recording.measurements[cursor : cursor + limit]:
            relative = (int(measurement.native_start_sample) - origin) / recording.source_rate_hz
            rows.append(
                NativeRecordingRowV1(
                    measurement=measurement,
                    coarse_relative_scheduled_start_s=relative,
                    coarse_relative_refined_start_s=relative + measurement.delay_s,
                )
            )
        return NativeRecordingDetailV1(
            summary=_summary(bundle),
            cursor=cursor,
            next_cursor=cursor + limit if cursor + limit < recording.head_count else None,
            rows=tuple(rows),
        )
