"""Crash-safe storage for retuned scanner sweeps as one framed IQ payload."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import numpy.typing as npt
import zstandard as zstd

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.contracts.recording import CompressionSettingsV1
from leo.domain.iq import receiver_major_complex_to_ci16
from leo.scanner.application import CapturedScannerSweep
from leo.scanner.models import (
    ScannerConfigurationV2,
    ScannerIqBundleManifestLike,
    ScannerIqBundleManifestV1,
    ScannerIqBundleManifestV2,
    ScannerIqBundleManifestV3,
    ScannerIqCaptureFailureV1,
    ScannerIqFrameV1,
    ScannerIqFrameV2,
    ScannerIqFrameV3,
)
from leo.scanner.ports import ScanRadioBlockV2
from leo.storage.errors import BundleCorruptionError, BundleNotFoundError
from leo.storage.uri import BulkUriResolver, confined_path
from leo.storage.writer import _CompressedFileWriter, _fsync_directory, _mkdir_durable

_MAX_MANIFEST_BYTES = 16 * 1024 * 1024
_READ_BUFFER_BYTES = 1024 * 1024
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@dataclass(frozen=True, slots=True)
class PublishedScannerIqBundle:
    scan_id: str
    path: Path
    uri: str
    manifest: ScannerIqBundleManifestLike
    manifest_sha256: str


class ScannerIqStore:
    """Own scanner IQ bundles beneath one local bulk root.

    Samples from different tunings share one storage coordinate but never lose
    their frame boundaries: the manifest is the authority for signal time and
    frequency. Publication follows the recording writer's commit discipline.
    """

    def __init__(self, root: Path) -> None:
        if root == Path("/mnt/qnap01") or str(root).startswith("/mnt/qnap01/"):
            raise ValueError("scanner IQ bundles cannot be written beneath QNAP")
        root.mkdir(parents=True, exist_ok=True)
        self.root = root.resolve(strict=True)
        self.spool_root = self.root / "spool"
        self.bundles_root = self.root / "scanner-recordings"
        self.spool_root.mkdir(exist_ok=True)
        self.bundles_root.mkdir(exist_ok=True)
        if os.stat(self.spool_root).st_dev != os.stat(self.bundles_root).st_dev:
            raise ValueError("scanner spool and bundle roots must share one filesystem")
        self.resolver = BulkUriResolver(
            self.root,
            allowed_namespaces=("scanner-recordings",),
        )

    def publish(
        self,
        scan_id: str,
        captured: CapturedScannerSweep,
        *,
        compression: CompressionSettingsV1 | None = None,
    ) -> PublishedScannerIqBundle | None:
        """Publish all successful target frames as one immutable CI16 payload."""

        if not _IDENTIFIER.fullmatch(scan_id):
            raise ValueError("scan ID is not one safe persisted identifier")
        if tuple(item.target for item in captured.targets) != captured.configuration.targets:
            raise ValueError("captured scanner targets disagree with the configured plan")
        selected_compression = compression or CompressionSettingsV1(policy_id="zstd-128m-v1")
        prepared: list[tuple[int, npt.NDArray[np.int16]]] = []
        for target_index, item in enumerate(captured.targets):
            if item.block is None:
                continue
            ci16 = receiver_major_complex_to_ci16(
                np.asarray(item.block.samples).T,
                len(captured.configuration.receiver_ids),
                captured.configuration.dwell_samples,
            )
            prepared.append((target_index, ci16))
        if not prepared:
            return None

        spool_path = self.spool_root / f"{scan_id}.scanner.partial"
        spool_path.mkdir(parents=False, exist_ok=False)
        _fsync_directory(self.spool_root)
        payload_writer = _CompressedFileWriter(
            spool_path / "iq.ci16.zst.partial",
            level=selected_compression.level,
        )
        uncompressed_digest = hashlib.sha256()
        frames: list[ScannerIqFrameV1 | ScannerIqFrameV2 | ScannerIqFrameV3] = []
        sample_start = 0
        try:
            for frame_index, (target_index, ci16) in enumerate(prepared):
                item = captured.targets[target_index]
                assert item.block is not None
                payload = memoryview(ci16).cast("B")
                payload_writer.write(payload)
                uncompressed_digest.update(payload)
                frame_digest = hashlib.sha256(payload).hexdigest()
                block = item.block
                common = {
                    "frame_index": frame_index,
                    "target_index": target_index,
                    "target": item.target,
                    "sample_start": sample_start,
                    "sample_count": ci16.shape[0],
                    "requested_if_center_hz": block.requested_if_center_hz,
                    "actual_if_center_hz": block.actual_if_center_hz,
                    "actual_rf_center_hz": (
                        block.actual_if_center_hz + captured.configuration.lnb_lo_hz
                    ),
                    "tune_ms": block.tune_ms,
                    "listen_ms": block.listen_ms,
                    "host_request_utc_ns_lower": block.host_request_utc_ns[0],
                    "host_request_utc_ns_upper": block.host_request_utc_ns[1],
                    "host_request_monotonic_ns_lower": block.host_request_monotonic_ns[0],
                    "host_request_monotonic_ns_upper": block.host_request_monotonic_ns[1],
                    "uncompressed_bytes": payload.nbytes,
                    "uncompressed_sha256": f"sha256:{frame_digest}",
                }
                if isinstance(captured.configuration, ScannerConfigurationV2):
                    if not isinstance(block, ScanRadioBlockV2):
                        raise ValueError("scanner V2 capture omitted metadata-attested IQ")
                    frame_type = (
                        ScannerIqFrameV3 if block.metadata_abi_version == 3 else ScannerIqFrameV2
                    )
                    frames.append(
                        frame_type.model_validate(
                            {
                                **common,
                                "metadata_abi_version": block.metadata_abi_version,
                                "stream_id": block.stream_id,
                                "stream_generation": block.stream_generation,
                                "buffer_sequence": block.buffer_sequence,
                                "source_sequence": block.source_sequence,
                                "first_sample_sequence": block.first_sample_sequence,
                                "last_sample_sequence_exclusive": (
                                    block.last_sample_sequence_exclusive
                                ),
                                "device_sample_counter": block.device_sample_counter,
                                "device_sample_counter_end_exclusive": (
                                    block.device_sample_counter_end_exclusive
                                ),
                                "metadata_flags": block.metadata_flags,
                                "sample_time_realtime_start_ns": (block.sample_time_realtime_ns[0]),
                                "sample_time_realtime_end_ns": block.sample_time_realtime_ns[1],
                                "sample_time_monotonic_start_ns": (
                                    block.sample_time_monotonic_ns[0]
                                ),
                                "sample_time_monotonic_end_ns": (block.sample_time_monotonic_ns[1]),
                                "sample_time_uncertainty_ns": (block.sample_time_uncertainty_ns),
                                "kernel_buffers_requested": block.kernel_buffers_requested,
                                "kernel_buffers_readback": block.kernel_buffers_readback,
                                "reset_episode": block.reset_episode,
                                "missing_samples_before": block.missing_samples_before,
                                "overflow_observed": block.overflow_observed,
                            }
                        )
                    )
                else:
                    if isinstance(block, ScanRadioBlockV2):
                        raise ValueError("scanner V1 configuration cannot persist V2 IQ")
                    frames.append(ScannerIqFrameV1.model_validate(common))
                sample_start += ci16.shape[0]
            payload_path, compressed_bytes, compressed_digest = payload_writer.finish()
        except Exception:
            payload_writer.abort()
            raise

        failures = tuple(
            ScannerIqCaptureFailureV1(
                target_index=target_index,
                target=item.target,
                reason=item.error or "capture failed",
            )
            for target_index, item in enumerate(captured.targets)
            if item.block is None
        )
        created_utc_ns = min(frame.host_request_utc_ns_lower for frame in frames)
        manifest_common = {
            "scan_id": scan_id,
            "created_utc_ns": created_utc_ns,
            "finalized_utc_ns": max(created_utc_ns, time.time_ns()),
            "radio_id": captured.identity.radio_id,
            "radio_serial": captured.identity.serial,
            "radio_uri": captured.identity.uri,
            "configuration": captured.configuration,
            "frames": tuple(frames),
            "failures": failures,
            "total_sample_count": sample_start,
            "uncompressed_bytes": (sample_start * len(captured.configuration.receiver_ids) * 4),
            "compressed_bytes": compressed_bytes,
            "uncompressed_sha256": f"sha256:{uncompressed_digest.hexdigest()}",
            "compressed_sha256": compressed_digest,
            "compression": selected_compression,
        }
        manifest: ScannerIqBundleManifestLike
        if any(isinstance(frame, ScannerIqFrameV3) for frame in frames):
            manifest = ScannerIqBundleManifestV3.model_validate(
                {
                    **manifest_common,
                    "retune_boundary_count": max(0, len(frames) - 1),
                }
            )
        elif isinstance(captured.configuration, ScannerConfigurationV2):
            manifest = ScannerIqBundleManifestV2.model_validate(
                {
                    **manifest_common,
                    "retune_boundary_count": max(0, len(frames) - 1),
                }
            )
        else:
            manifest = ScannerIqBundleManifestV1.model_validate(manifest_common)
        if payload_path.name != manifest.payload_relative_path:
            raise RuntimeError("scanner IQ payload name disagrees with its contract")
        manifest_payload = canonical_json_bytes(manifest.model_dump(mode="json"))
        partial_manifest = spool_path / "manifest.json.partial"
        with partial_manifest.open("xb") as stream:
            stream.write(manifest_payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(partial_manifest, spool_path / "manifest.json")
        _fsync_directory(spool_path)

        created = datetime.fromtimestamp(created_utc_ns // 1_000_000_000, tz=UTC)
        parent = (
            self.bundles_root
            / f"{created.year:04d}"
            / f"{created.month:02d}"
            / f"{created.day:02d}"
        )
        _mkdir_durable(parent, stop=self.bundles_root)
        destination = parent / scan_id
        if destination.exists():
            raise FileExistsError(f"scanner IQ bundle already exists: {destination}")
        os.rename(spool_path, destination)
        _fsync_directory(parent)
        return PublishedScannerIqBundle(
            scan_id=scan_id,
            path=destination,
            uri=self.resolver.uri_for(destination),
            manifest=manifest,
            manifest_sha256=sha256_digest(manifest_payload),
        )

    def inspect(self, scan_id: str) -> PublishedScannerIqBundle:
        if not _IDENTIFIER.fullmatch(scan_id):
            raise ValueError("scan ID is not one safe persisted identifier")
        matches = tuple(self.bundles_root.glob(f"*/*/*/{scan_id}"))
        if not matches:
            raise BundleNotFoundError(f"scanner IQ bundle does not exist: {scan_id}")
        if len(matches) != 1:
            raise BundleCorruptionError(f"scanner IQ bundle appears more than once: {scan_id}")
        path = confined_path(self.bundles_root, matches[0], must_exist=True)
        manifest_path = path / "manifest.json"
        payload = self._read_regular(manifest_path, _MAX_MANIFEST_BYTES)
        try:
            document = json.loads(payload)
            schema_version = document.get("schema_version")
            if schema_version == 1:
                manifest = ScannerIqBundleManifestV1.model_validate(document)
            elif schema_version == 2:
                manifest = ScannerIqBundleManifestV2.model_validate(document)
            elif schema_version == 3:
                manifest = ScannerIqBundleManifestV3.model_validate(document)
            else:
                raise ValueError(f"unsupported scanner IQ manifest schema {schema_version!r}")
        except Exception as error:
            raise BundleCorruptionError(f"invalid scanner IQ manifest: {error}") from error
        if manifest.scan_id != scan_id:
            raise BundleCorruptionError("scanner IQ manifest scan ID disagrees with its path")
        return PublishedScannerIqBundle(
            scan_id=scan_id,
            path=path,
            uri=self.resolver.uri_for(path),
            manifest=manifest,
            manifest_sha256=sha256_digest(payload),
        )

    def captured_at(self, scan_id: str) -> datetime:
        """Return the immutable start of RF observation for one scan."""

        created_utc_ns = self.inspect(scan_id).manifest.created_utc_ns
        return datetime.fromtimestamp(created_utc_ns / 1_000_000_000, tz=UTC)

    def recording_ids(self) -> tuple[str, ...]:
        """Return immutable scanner recording IDs in oldest-first order."""

        recordings: list[tuple[int, str]] = []
        for candidate in self.bundles_root.glob("*/*/*/*"):
            if not _IDENTIFIER.fullmatch(candidate.name):
                continue
            try:
                path = confined_path(self.bundles_root, candidate, must_exist=True)
                metadata = path.stat(follow_symlinks=False)
            except (FileNotFoundError, ValueError):
                continue
            if not stat.S_ISDIR(metadata.st_mode) or path.is_symlink():
                continue
            recordings.append((metadata.st_mtime_ns, path.name))
        return tuple(scan_id for _modified_ns, scan_id in sorted(recordings))

    def read_ci16(
        self,
        bundle: PublishedScannerIqBundle | str,
        *,
        verify: bool = True,
    ) -> npt.NDArray[np.int16]:
        inspected = self.inspect(bundle) if isinstance(bundle, str) else bundle
        manifest = inspected.manifest
        payload_path = confined_path(
            inspected.path,
            inspected.path / manifest.payload_relative_path,
            must_exist=True,
        )
        compressed = self._read_regular(payload_path, manifest.compressed_bytes)
        if len(compressed) != manifest.compressed_bytes:
            raise BundleCorruptionError("scanner IQ compressed byte count changed")
        if verify and sha256_digest(compressed) != manifest.compressed_sha256:
            raise BundleCorruptionError("scanner IQ compressed digest mismatch")
        try:
            with zstd.ZstdDecompressor().stream_reader(compressed) as reader:
                raw = reader.read(manifest.uncompressed_bytes + 1)
        except zstd.ZstdError as error:
            raise BundleCorruptionError(f"scanner IQ decompression failed: {error}") from error
        if len(raw) != manifest.uncompressed_bytes:
            raise BundleCorruptionError("scanner IQ uncompressed byte count changed")
        if verify and sha256_digest(raw) != manifest.uncompressed_sha256:
            raise BundleCorruptionError("scanner IQ uncompressed digest mismatch")
        receiver_count = len(manifest.configuration.receiver_ids)
        values = np.frombuffer(raw, dtype="<i2").reshape(
            manifest.total_sample_count,
            receiver_count,
            2,
        )
        if verify:
            for frame in manifest.frames:
                frame_values = values[frame.sample_start : frame.sample_start + frame.sample_count]
                if sha256_digest(frame_values.tobytes(order="C")) != frame.uncompressed_sha256:
                    raise BundleCorruptionError(
                        f"scanner IQ frame {frame.frame_index} digest mismatch"
                    )
        values.setflags(write=False)
        return values

    @staticmethod
    def _read_regular(path: Path, maximum_bytes: int) -> bytes:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise BundleCorruptionError("scanner IQ bundle member is not one regular file")
            if before.st_size > maximum_bytes:
                raise BundleCorruptionError("scanner IQ bundle member exceeds its declared bound")
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
                raise BundleCorruptionError("scanner IQ bundle member changed while reading")
            return b"".join(chunks)
        finally:
            os.close(descriptor)
