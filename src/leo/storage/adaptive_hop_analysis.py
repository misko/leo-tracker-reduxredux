"""Pinned, immutable per-visit analysis with bounded reads and crash-safe resume.

Only metrics are finalized here. A metrics manifest does not assert that plots,
trajectory association, API integration or detector qualification are complete.
"""

from __future__ import annotations

import ctypes
import fcntl
import json
import os
import re
import stat
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import zstandard as zstd
from pydantic import BaseModel

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.scanner.adaptive_hop_analysis import AdaptiveHopVisitAnalysisV1
from leo.scanner.adaptive_hop_products import (
    AdaptiveHopAnalysisBindingV1,
    AdaptiveHopMetricsManifestV1,
    AdaptiveHopVisitReferenceV1,
)
from leo.storage.errors import BundleCorruptionError, BundleNotFoundError
from leo.storage.pinned import PinnedLocalRoot

_NAMESPACE = "scanner-adaptive-analysis"
_MAX_BINDING = 32 * 1024 * 1024
_MAX_VISIT = 2 * 1024 * 1024
_MAX_MANIFEST = 4 * 1024 * 1024
_VISIT = re.compile(r"visit-([0-9]{6})\.v1\.json\.zst")


def _read(directory: PinnedLocalRoot, name: str, maximum: int) -> bytes:
    descriptor = os.open(
        name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory.fileno()
    )
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or not 0 < before.st_size <= maximum
        ):
            raise BundleCorruptionError("analysis file is not bounded single-link regular data")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read(maximum + 1)
        after = os.fstat(descriptor)
        fields = ("st_size", "st_mtime_ns", "st_ctime_ns", "st_nlink")
        if len(raw) != before.st_size or any(
            getattr(before, key) != getattr(after, key) for key in fields
        ):
            raise BundleCorruptionError("analysis file changed during bounded read")
        return raw
    finally:
        os.close(descriptor)


def _seal(model: BaseModel) -> bytes:
    body = model.model_dump(mode="json")
    return canonical_json_bytes(
        {"document": body, "sha256": sha256_digest(canonical_json_bytes(body))}
    )


def _unseal[Model: BaseModel](raw: bytes, model: type[Model]) -> Model:
    try:
        sealed = json.loads(raw)
        if (
            not isinstance(sealed, dict)
            or set(sealed) != {"document", "sha256"}
            or sealed["sha256"] != sha256_digest(canonical_json_bytes(sealed["document"]))
        ):
            raise ValueError("analysis seal differs")
        return model.model_validate(sealed["document"])
    except (ValueError, TypeError, KeyError) as error:
        raise BundleCorruptionError("invalid sealed analysis document") from error


def _publish(directory: PinnedLocalRoot, name: str, payload: bytes, maximum: int) -> None:
    if not 0 < len(payload) <= maximum:
        raise ValueError("analysis document exceeds its byte bound")
    temporary = f".{name}.{uuid4().hex}.partial"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o640,
        dir_fd=directory.fileno(),
    )
    # Failed temporary files are retained for diagnosis and ignored on resume.
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    rename = ctypes.CDLL(None, use_errno=True).renameat2
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(directory.fileno(), temporary.encode(), directory.fileno(), name.encode(), 1):
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), name)
    os.fsync(directory.fileno())


class AdaptiveHopAnalysisStore:
    """Owns a retained root; caller closes it. Read-only use creates nothing."""

    def __init__(self, root: Path, *, read_only: bool = False):
        self._root = PinnedLocalRoot(root)
        self._read_only = read_only

    def close(self) -> None:
        self._root.close()

    @contextmanager
    def job(
        self, binding: AdaptiveHopAnalysisBindingV1, *, writable: bool = False
    ) -> Iterator[AdaptiveHopAnalysisJob]:
        binding = AdaptiveHopAnalysisBindingV1.model_validate(binding.model_dump())
        if writable and self._read_only:
            raise PermissionError("adaptive analysis store is read-only")
        handles: list[PinnedLocalRoot] = []
        lock = None
        try:
            parent = self._root
            for component in (
                _NAMESPACE,
                binding.session_id,
                binding.sha256.removeprefix("sha256:"),
            ):
                if not writable:
                    try:
                        os.stat(component, dir_fd=parent.fileno(), follow_symlinks=False)
                    except FileNotFoundError as error:
                        raise BundleNotFoundError("adaptive analysis does not exist") from error
                child = parent.child(component, create=writable)
                handles.append(child)
                if writable:
                    os.fsync(parent.fileno())
                parent = child
            if writable:
                lock = os.open(
                    "worker.lock",
                    os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                    0o640,
                    dir_fd=parent.fileno(),
                )
                info = os.fstat(lock)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise BundleCorruptionError("adaptive analysis lock is not a regular file")
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as error:
                    raise BlockingIOError(
                        "adaptive analysis binding already has a worker"
                    ) from error
            try:
                existing = _unseal(
                    _read(parent, "binding.v1.json", _MAX_BINDING), AdaptiveHopAnalysisBindingV1
                )
            except FileNotFoundError:
                if not writable:
                    raise BundleNotFoundError("adaptive analysis binding is unpublished") from None
                _publish(parent, "binding.v1.json", _seal(binding), _MAX_BINDING)
            else:
                if existing != binding:
                    raise BundleCorruptionError("adaptive analysis binding changed")
            yield AdaptiveHopAnalysisJob(parent, binding, writable=writable)
        finally:
            if lock is not None:
                os.close(lock)
            for handle in reversed(handles):
                handle.close()


class AdaptiveHopAnalysisJob:
    """Lifetime is the store.job context; one decoded visit at a time."""

    def __init__(
        self, directory: PinnedLocalRoot, binding: AdaptiveHopAnalysisBindingV1, *, writable: bool
    ):
        self._directory, self.binding, self._writable = directory, binding, writable
        self._binding_sha256 = binding.sha256

    def _index(self, index: int) -> str:
        if type(index) is not int or not 0 <= index < self.binding.receipt.complete_visit_count:
            raise ValueError("adaptive analysis visit is not retained by the source")
        return f"visit-{index:06d}.v1.json.zst"

    def _read_visit(
        self, index: int
    ) -> tuple[AdaptiveHopVisitAnalysisV1, AdaptiveHopVisitReferenceV1]:
        name = self._index(index)
        compressed = _read(self._directory, name, _MAX_VISIT)
        try:
            frame = zstd.get_frame_parameters(compressed)
            if not 0 < frame.content_size <= _MAX_VISIT or frame.window_size > _MAX_VISIT:
                raise BundleCorruptionError("adaptive analysis expansion exceeds bound")
            raw = zstd.ZstdDecompressor(max_window_size=_MAX_VISIT).decompress(
                compressed,
                max_output_size=_MAX_VISIT,
                allow_extra_data=False,
            )
        except zstd.ZstdError as error:
            raise BundleCorruptionError("adaptive analysis decompression failed") from error
        product = _unseal(raw, AdaptiveHopVisitAnalysisV1)
        self._validate(product)
        if product.visit_index != index:
            raise BundleCorruptionError("adaptive analysis path changed visit identity")
        reference = AdaptiveHopVisitReferenceV1(
            visit_index=index,
            relative_path=name,
            compressed_sha256=sha256_digest(compressed),
            uncompressed_sha256=sha256_digest(raw),
            compressed_bytes=len(compressed),
            uncompressed_bytes=len(raw),
            probe_count=len(product.probes),
            candidate_count=sum(p.candidate_count for p in product.probes),
            fractional_candidate_count=sum(len(p.candidates) for p in product.probes),
            passed_fractional_candidate_count=sum(
                c.passed_fractional_margin_gate for p in product.probes for c in p.candidates
            ),
        )
        return product, reference

    def _validate(self, product: AdaptiveHopVisitAnalysisV1) -> None:
        try:
            self.binding.validate_visit(product)
        except ValueError as error:
            raise BundleCorruptionError(str(error)) from error

    def _references(self) -> tuple[AdaptiveHopVisitReferenceV1, ...]:
        indexes = []
        for name in os.listdir(self._directory.fileno()):
            if name.startswith("visit-"):
                match = _VISIT.fullmatch(name)
                if match is None:
                    raise BundleCorruptionError("malformed adaptive analysis visit filename")
                indexes.append(int(match.group(1)))
        return tuple(self._read_visit(index)[1] for index in sorted(indexes))

    def completed_visits(self) -> tuple[int, ...]:
        return tuple(r.visit_index for r in self._references())

    def read_visit(self, index: int) -> AdaptiveHopVisitAnalysisV1:
        product, reference = self._read_visit(index)
        manifest = self.manifest()
        if manifest is not None and manifest.visits[index] != reference:
            raise BundleCorruptionError("adaptive published visit digest differs from manifest")
        return product

    def write_visit(self, product: AdaptiveHopVisitAnalysisV1) -> AdaptiveHopVisitReferenceV1:
        if not self._writable:
            raise PermissionError("adaptive analysis job is read-only")
        product = AdaptiveHopVisitAnalysisV1.model_validate(product.model_dump())
        self._validate(product)
        name = self._index(product.visit_index)
        try:
            existing, reference = self._read_visit(product.visit_index)
        except FileNotFoundError:
            if self.manifest() is not None:
                raise BundleCorruptionError("published adaptive analysis lost a visit") from None
        else:
            if existing != product:
                raise BundleCorruptionError("adaptive checkpoint cannot be overwritten")
            # A sealed publication must also agree with its externally stored digest.
            self.read_visit(product.visit_index)
            return reference
        raw = _seal(product)
        if len(raw) > _MAX_VISIT:
            raise ValueError("adaptive visit exceeds its uncompressed bound")
        compressed = zstd.ZstdCompressor(level=3, threads=0).compress(raw)
        _publish(self._directory, name, compressed, _MAX_VISIT)
        return self._read_visit(product.visit_index)[1]

    def manifest(self) -> AdaptiveHopMetricsManifestV1 | None:
        try:
            raw = _read(self._directory, "metrics-manifest.v1.json", _MAX_MANIFEST)
        except FileNotFoundError:
            return None
        result = _unseal(raw, AdaptiveHopMetricsManifestV1)
        if (
            result.session_id != self.binding.session_id
            or result.binding_sha256 != self._binding_sha256
            or result.input_manifest_sha256 != self.binding.input_manifest_sha256
            or result.configuration != self.binding.configuration
            or result.complete_visit_count != self.binding.receipt.complete_visit_count
        ):
            raise BundleCorruptionError("adaptive metrics manifest binding differs")
        return result

    def verify(self) -> AdaptiveHopMetricsManifestV1 | None:
        manifest, references = self.manifest(), self._references()
        if manifest is not None and manifest.visits != references:
            raise BundleCorruptionError("adaptive metrics manifest inventory/digests differ")
        return manifest

    def finalize_metrics(self) -> AdaptiveHopMetricsManifestV1:
        if not self._writable:
            raise PermissionError("adaptive analysis job is read-only")
        existing = self.verify()
        if existing is not None:
            return existing
        manifest = AdaptiveHopMetricsManifestV1(
            session_id=self.binding.session_id,
            input_manifest_sha256=self.binding.input_manifest_sha256,
            binding_sha256=self._binding_sha256,
            configuration=self.binding.configuration,
            complete_visit_count=self.binding.receipt.complete_visit_count,
            visits=self._references(),
            finalized_utc_ns=time.time_ns(),
        )
        _publish(self._directory, "metrics-manifest.v1.json", _seal(manifest), _MAX_MANIFEST)
        return manifest
