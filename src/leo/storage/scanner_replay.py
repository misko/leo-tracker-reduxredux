"""Crash-safe materialization of scanner replay datasets from recording slices."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
import zstandard as zstd

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.contracts.recording import CompressionSettingsV1
from leo.scanner.models import ScannerConfiguration, ScanTarget
from leo.scanner.replay import (
    PreparedScannerReplayDataset,
    PreparedScannerReplayFrame,
    ScannerReplayDatasetEntryV1,
    ScannerReplayDatasetManifestV1,
    ScannerReplayDatasetRecipeV1,
    ScannerReplayFrameRecipeV1,
    ScannerReplayIqBundleManifestV1,
    ScannerReplayIqFrameV1,
    ScannerReplaySourceV1,
    ScannerReplaySplit,
    ScannerReplayTruthItemV1,
    ScannerReplayTruthV1,
)
from leo.storage.errors import BundleCorruptionError, BundleNotFoundError
from leo.storage.store import RecordingStore
from leo.storage.uri import BulkUriResolver, confined_path
from leo.storage.writer import _CompressedFileWriter, _fsync_directory

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_JSON_BYTES = 16 * 1024 * 1024
_READ_BUFFER_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class PublishedScannerReplayDataset:
    dataset_id: str
    path: Path
    uri: str
    manifest: ScannerReplayDatasetManifestV1
    manifest_sha256: str
    truth: ScannerReplayTruthV1


@dataclass(frozen=True, slots=True)
class PublishedScannerReplaySweep:
    dataset_id: str
    sweep_id: str
    path: Path
    uri: str
    manifest: ScannerReplayIqBundleManifestV1
    manifest_sha256: str


class RecordingScannerReplaySource:
    """Read-only adapter that resolves replay recipes through RecordingStore."""

    def __init__(self, recordings: RecordingStore) -> None:
        self._recordings = recordings

    def read_frame(
        self,
        recipe: ScannerReplayFrameRecipeV1,
        target: ScanTarget,
        configuration: ScannerConfiguration,
    ) -> PreparedScannerReplayFrame:
        bundle = self._recordings.inspect(recipe.source_session_id)
        matches = tuple(
            stream
            for stream in bundle.manifest.streams
            if stream.stream_id == recipe.source_stream_id
        )
        if len(matches) != 1:
            raise ValueError("replay source stream is absent or ambiguous")
        stream = matches[0]
        if stream.applied_settings is None:
            raise ValueError("replay source stream has no applied radio settings")
        requested = stream.requested_settings
        settings = stream.applied_settings
        if requested.center_frequency_hz != target.if_center_hz:
            raise ValueError("replay requested source IF disagrees with target")
        if settings.sample_rate_hz != configuration.sample_rate_hz:
            raise ValueError("replay source sample rate disagrees with scanner plan")
        if settings.bandwidth_hz != configuration.bandwidth_hz:
            raise ValueError("replay source bandwidth disagrees with scanner plan")
        if settings.receiver_ids != configuration.receiver_ids:
            raise ValueError("replay source receivers disagree with scanner plan")
        samples = self._recordings.read_ci16(
            bundle,
            stream.stream_id,
            recipe.source_sample_start,
            configuration.dwell_samples,
            receiver_ids=configuration.receiver_ids,
            verify=True,
        )
        samples = np.ascontiguousarray(samples, dtype="<i2")
        source = ScannerReplaySourceV1(
            session_id=bundle.session_id,
            recording_uri=bundle.uri,
            recording_manifest_sha256=bundle.manifest_sha256,
            stream_id=stream.stream_id,
            radio_id=stream.radio.radio_id,
            radio_serial=stream.radio.serial,
            source_receiver_ids=settings.receiver_ids,
            source_sample_start=recipe.source_sample_start,
            source_sample_count=configuration.dwell_samples,
            requested_settings=requested,
            applied_settings=settings,
        )
        return PreparedScannerReplayFrame(recipe=recipe, source=source, samples=samples)


class ScannerReplayStore:
    """Own complete immutable replay datasets beneath one local bulk root."""

    def __init__(self, root: Path) -> None:
        if root == Path("/mnt/qnap01") or str(root).startswith("/mnt/qnap01/"):
            raise ValueError("scanner replay datasets cannot be written beneath QNAP")
        root.mkdir(parents=True, exist_ok=True)
        self.root = root.resolve(strict=True)
        self.spool_root = self.root / "spool"
        self.datasets_root = self.root / "scanner-replays"
        self.spool_root.mkdir(exist_ok=True)
        self.datasets_root.mkdir(exist_ok=True)
        if os.stat(self.spool_root).st_dev != os.stat(self.datasets_root).st_dev:
            raise ValueError("scanner replay spool and datasets must share one filesystem")
        self.resolver = BulkUriResolver(self.root, allowed_namespaces=("scanner-replays",))

    def publish(
        self,
        prepared: PreparedScannerReplayDataset,
        *,
        compression: CompressionSettingsV1 | None = None,
    ) -> PublishedScannerReplayDataset:
        recipe = prepared.recipe
        if not _IDENTIFIER.fullmatch(recipe.dataset_id):
            raise ValueError("dataset ID is not one safe persisted identifier")
        if tuple(sweep.recipe for sweep in prepared.sweeps) != recipe.sweeps:
            raise ValueError("prepared replay sweeps disagree with the recipe")
        destination = self.datasets_root / recipe.dataset_id
        if destination.exists():
            raise FileExistsError(f"scanner replay dataset already exists: {destination}")
        selected_compression = compression or CompressionSettingsV1(policy_id="zstd-128m-v1")
        spool = self.spool_root / f"{recipe.dataset_id}.replay.partial"
        spool.mkdir(parents=False, exist_ok=False)
        _fsync_directory(self.spool_root)
        entries: list[ScannerReplayDatasetEntryV1] = []
        truth_items: list[ScannerReplayTruthItemV1] = []
        for sweep in prepared.sweeps:
            bundle_path = spool / sweep.recipe.split.value / sweep.recipe.sweep_id
            bundle_path.mkdir(parents=True, exist_ok=False)
            manifest, manifest_payload = self._write_sweep(
                bundle_path,
                prepared,
                sweep.frames,
                sweep.recipe.sweep_id,
                sweep.recipe.split,
                selected_compression,
            )
            entries.append(
                ScannerReplayDatasetEntryV1(
                    sweep_id=sweep.recipe.sweep_id,
                    split=sweep.recipe.split,
                    bundle_relative_path=bundle_path.relative_to(spool).as_posix(),
                    manifest_sha256=sha256_digest(manifest_payload),
                )
            )
            truth_items.extend(
                ScannerReplayTruthItemV1(
                    sweep_id=sweep.recipe.sweep_id,
                    target_index=frame.recipe.target_index,
                    target=manifest.configuration.targets[frame.recipe.target_index],
                    label=frame.recipe.label,
                    evidence=frame.recipe.evidence,
                )
                for frame in sweep.frames
            )
        truth = ScannerReplayTruthV1(dataset_id=recipe.dataset_id, items=tuple(truth_items))
        truth_payload = canonical_json_bytes(truth.model_dump(mode="json"))
        self._write_json(spool / "truth.v1.json", truth_payload)
        recipe_payload = canonical_json_bytes(recipe.model_dump(mode="json"))
        self._write_json(spool / "recipe.v1.json", recipe_payload)
        dataset_manifest = ScannerReplayDatasetManifestV1(
            dataset_id=recipe.dataset_id,
            generator_id=recipe.generator_id,
            configuration=recipe.configuration,
            entries=tuple(entries),
            recipe_sha256=sha256_digest(recipe_payload),
            truth_sha256=sha256_digest(truth_payload),
        )
        dataset_payload = canonical_json_bytes(dataset_manifest.model_dump(mode="json"))
        self._write_json(spool / "manifest.json", dataset_payload)
        _fsync_directory(spool)
        os.rename(spool, destination)
        _fsync_directory(self.datasets_root)
        return PublishedScannerReplayDataset(
            dataset_id=recipe.dataset_id,
            path=destination,
            uri=self.resolver.uri_for(destination),
            manifest=dataset_manifest,
            manifest_sha256=sha256_digest(dataset_payload),
            truth=truth,
        )

    def _write_sweep(
        self,
        bundle_path: Path,
        prepared: PreparedScannerReplayDataset,
        frames: tuple[PreparedScannerReplayFrame, ...],
        sweep_id: str,
        split: ScannerReplaySplit,
        compression: CompressionSettingsV1,
    ) -> tuple[ScannerReplayIqBundleManifestV1, bytes]:
        configuration = prepared.recipe.configuration
        if len(frames) != len(configuration.targets):
            raise ValueError("prepared replay sweep does not cover every target")
        writer = _CompressedFileWriter(bundle_path / "iq.ci16.zst.partial", level=compression.level)
        uncompressed_digest = hashlib.sha256()
        manifest_frames: list[ScannerReplayIqFrameV1] = []
        sample_start = 0
        try:
            for frame_index, frame in enumerate(frames):
                if frame.recipe.target_index != frame_index:
                    raise ValueError("prepared replay frames disagree with scan-plan order")
                payload = memoryview(frame.samples).cast("B")
                writer.write(payload)
                uncompressed_digest.update(payload)
                manifest_frames.append(
                    ScannerReplayIqFrameV1(
                        frame_index=frame_index,
                        target_index=frame_index,
                        target=configuration.targets[frame_index],
                        sample_start=sample_start,
                        sample_count=frame.samples.shape[0],
                        source=frame.source,
                        uncompressed_bytes=payload.nbytes,
                        uncompressed_sha256=sha256_digest(payload),
                    )
                )
                sample_start += frame.samples.shape[0]
            payload_path, compressed_bytes, compressed_digest = writer.finish()
        except Exception:
            writer.abort()
            raise
        manifest = ScannerReplayIqBundleManifestV1(
            dataset_id=prepared.recipe.dataset_id,
            sweep_id=sweep_id,
            split=split,
            generator_id=prepared.recipe.generator_id,
            configuration=configuration,
            frames=tuple(manifest_frames),
            total_sample_count=sample_start,
            uncompressed_bytes=sample_start * len(configuration.receiver_ids) * 4,
            compressed_bytes=compressed_bytes,
            uncompressed_sha256=f"sha256:{uncompressed_digest.hexdigest()}",
            compressed_sha256=compressed_digest,
            compression=compression,
        )
        if payload_path.name != manifest.payload_relative_path:
            raise RuntimeError("scanner replay IQ payload name disagrees with contract")
        manifest_payload = canonical_json_bytes(manifest.model_dump(mode="json"))
        self._write_json(bundle_path / "manifest.json", manifest_payload)
        _fsync_directory(bundle_path)
        _fsync_directory(bundle_path.parent)
        return manifest, manifest_payload

    def inspect(self, dataset_id: str) -> PublishedScannerReplayDataset:
        if not _IDENTIFIER.fullmatch(dataset_id):
            raise ValueError("dataset ID is not one safe persisted identifier")
        candidate = self.datasets_root / dataset_id
        if not candidate.exists():
            raise BundleNotFoundError(f"scanner replay dataset does not exist: {dataset_id}")
        path = confined_path(self.datasets_root, candidate, must_exist=True)
        if not path.is_dir():
            raise BundleCorruptionError("scanner replay dataset path is not a directory")
        manifest_payload = self._read_regular(path / "manifest.json", _MAX_JSON_BYTES)
        try:
            manifest = ScannerReplayDatasetManifestV1.model_validate_json(manifest_payload)
        except Exception as error:
            raise BundleCorruptionError(
                f"invalid scanner replay dataset manifest: {error}"
            ) from error
        if manifest.dataset_id != dataset_id:
            raise BundleCorruptionError("scanner replay dataset ID disagrees with its path")
        recipe_payload = self._read_regular(path / manifest.recipe_relative_path, _MAX_JSON_BYTES)
        if sha256_digest(recipe_payload) != manifest.recipe_sha256:
            raise BundleCorruptionError("scanner replay recipe digest mismatch")
        try:
            recipe = ScannerReplayDatasetRecipeV1.model_validate_json(recipe_payload)
        except Exception as error:
            raise BundleCorruptionError(f"invalid scanner replay recipe: {error}") from error
        if (
            recipe.dataset_id != dataset_id
            or recipe.generator_id != manifest.generator_id
            or recipe.configuration != manifest.configuration
        ):
            raise BundleCorruptionError("scanner replay recipe disagrees with dataset manifest")
        if tuple((sweep.sweep_id, sweep.split) for sweep in recipe.sweeps) != tuple(
            (entry.sweep_id, entry.split) for entry in manifest.entries
        ):
            raise BundleCorruptionError("scanner replay recipe sweep inventory disagrees")
        truth_payload = self._read_regular(path / manifest.truth_relative_path, _MAX_JSON_BYTES)
        if sha256_digest(truth_payload) != manifest.truth_sha256:
            raise BundleCorruptionError("scanner replay truth digest mismatch")
        try:
            truth = ScannerReplayTruthV1.model_validate_json(truth_payload)
        except Exception as error:
            raise BundleCorruptionError(f"invalid scanner replay truth: {error}") from error
        if truth.dataset_id != dataset_id:
            raise BundleCorruptionError("scanner replay truth dataset ID disagrees")
        expected_truth: list[tuple[str, int]] = []
        for entry in manifest.entries:
            bundle_path = confined_path(path, path / entry.bundle_relative_path, must_exist=True)
            payload = self._read_regular(bundle_path / "manifest.json", _MAX_JSON_BYTES)
            if sha256_digest(payload) != entry.manifest_sha256:
                raise BundleCorruptionError(
                    f"scanner replay sweep manifest changed: {entry.sweep_id}"
                )
            try:
                sweep_manifest = ScannerReplayIqBundleManifestV1.model_validate_json(payload)
            except Exception as error:
                raise BundleCorruptionError(
                    f"invalid scanner replay sweep manifest: {error}"
                ) from error
            if (
                sweep_manifest.dataset_id != dataset_id
                or sweep_manifest.sweep_id != entry.sweep_id
                or sweep_manifest.split is not entry.split
                or sweep_manifest.generator_id != manifest.generator_id
                or sweep_manifest.configuration != manifest.configuration
            ):
                raise BundleCorruptionError(
                    f"scanner replay sweep disagrees with dataset inventory: {entry.sweep_id}"
                )
            expected_truth.extend(
                (entry.sweep_id, frame.target_index) for frame in sweep_manifest.frames
            )
        actual_truth = [(item.sweep_id, item.target_index) for item in truth.items]
        if actual_truth != expected_truth:
            raise BundleCorruptionError(
                "scanner replay truth does not cover dataset frames exactly"
            )
        target_by_identity = {
            (item.sweep_id, item.target_index): item.target for item in truth.items
        }
        for sweep_id, target_index in expected_truth:
            if (
                target_by_identity[(sweep_id, target_index)]
                != manifest.configuration.targets[target_index]
            ):
                raise BundleCorruptionError("scanner replay truth target disagrees with scan plan")
        return PublishedScannerReplayDataset(
            dataset_id=dataset_id,
            path=path,
            uri=self.resolver.uri_for(path),
            manifest=manifest,
            manifest_sha256=sha256_digest(manifest_payload),
            truth=truth,
        )

    def inspect_sweep(self, dataset_id: str, sweep_id: str) -> PublishedScannerReplaySweep:
        dataset = self.inspect(dataset_id)
        entries = tuple(entry for entry in dataset.manifest.entries if entry.sweep_id == sweep_id)
        if len(entries) != 1:
            raise BundleNotFoundError(f"scanner replay sweep does not exist: {sweep_id}")
        entry = entries[0]
        path = confined_path(
            dataset.path,
            dataset.path / entry.bundle_relative_path,
            must_exist=True,
        )
        payload = self._read_regular(path / "manifest.json", _MAX_JSON_BYTES)
        try:
            manifest = ScannerReplayIqBundleManifestV1.model_validate_json(payload)
        except Exception as error:
            raise BundleCorruptionError(
                f"invalid scanner replay sweep manifest: {error}"
            ) from error
        if manifest.dataset_id != dataset_id or manifest.sweep_id != sweep_id:
            raise BundleCorruptionError("scanner replay sweep identity disagrees with its path")
        return PublishedScannerReplaySweep(
            dataset_id=dataset_id,
            sweep_id=sweep_id,
            path=path,
            uri=self.resolver.uri_for(path),
            manifest=manifest,
            manifest_sha256=sha256_digest(payload),
        )

    def read_ci16(
        self,
        sweep: PublishedScannerReplaySweep,
        *,
        verify: bool = True,
    ) -> npt.NDArray[np.int16]:
        manifest = sweep.manifest
        payload_path = confined_path(
            sweep.path,
            sweep.path / manifest.payload_relative_path,
            must_exist=True,
        )
        compressed = self._read_regular(payload_path, manifest.compressed_bytes)
        if len(compressed) != manifest.compressed_bytes:
            raise BundleCorruptionError("scanner replay compressed byte count changed")
        if verify and sha256_digest(compressed) != manifest.compressed_sha256:
            raise BundleCorruptionError("scanner replay compressed digest mismatch")
        try:
            with zstd.ZstdDecompressor().stream_reader(compressed) as reader:
                raw = reader.read(manifest.uncompressed_bytes + 1)
        except zstd.ZstdError as error:
            raise BundleCorruptionError(f"scanner replay decompression failed: {error}") from error
        if len(raw) != manifest.uncompressed_bytes:
            raise BundleCorruptionError("scanner replay uncompressed byte count changed")
        if verify and sha256_digest(raw) != manifest.uncompressed_sha256:
            raise BundleCorruptionError("scanner replay uncompressed digest mismatch")
        values = np.frombuffer(raw, dtype="<i2").reshape(
            manifest.total_sample_count,
            len(manifest.configuration.receiver_ids),
            2,
        )
        if verify:
            for frame in manifest.frames:
                selected = values[frame.sample_start : frame.sample_start + frame.sample_count]
                if sha256_digest(selected.tobytes(order="C")) != frame.uncompressed_sha256:
                    raise BundleCorruptionError(
                        f"scanner replay frame {frame.frame_index} digest mismatch"
                    )
        values.setflags(write=False)
        return values

    @staticmethod
    def _write_json(path: Path, payload: bytes) -> None:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())

    @staticmethod
    def _read_regular(path: Path, maximum_bytes: int) -> bytes:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise BundleCorruptionError("scanner replay member is not one regular file")
            if before.st_size > maximum_bytes:
                raise BundleCorruptionError("scanner replay member exceeds its declared bound")
            chunks: list[bytes] = []
            remaining = maximum_bytes + 1
            while remaining:
                chunk = os.read(descriptor, min(_READ_BUFFER_BYTES, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            after = os.fstat(descriptor)
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ):
                raise BundleCorruptionError("scanner replay member changed while reading")
            return b"".join(chunks)
        finally:
            os.close(descriptor)
