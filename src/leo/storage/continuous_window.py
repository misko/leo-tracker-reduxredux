"""Bounded segment rotation and atomic continuous-run checkpoints."""

from __future__ import annotations

import os
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

from leo.contracts.continuous_window import ContinuousRunCheckpointV1
from leo.contracts.digests import canonical_json_bytes
from leo.contracts.recording import Identifier
from leo.scanner.continuous_window import ContinuousWindowConfiguration
from leo.storage.short_window import ShortWindowWriter
from leo.storage.writer import _fsync_directory


def run_path(root: Path, run_id: str) -> Path:
    from pydantic import TypeAdapter

    TypeAdapter(Identifier).validate_python(run_id)
    resolved = root.resolve()
    qnap = Path("/mnt/qnap01")
    if resolved == qnap or qnap in resolved.parents:
        raise ValueError("continuous recording controls cannot write beneath QNAP")
    path = resolved / run_id
    if path.is_symlink():
        raise ValueError("continuous run must be one owned directory")
    return path


def read_checkpoint(root: Path, run_id: str) -> ContinuousRunCheckpointV1:
    from leo.storage.scanner import ScannerIqStore

    path = run_path(root, run_id)
    failure = path / "publication-failure.json"
    payload = ScannerIqStore._read_regular(
        failure if failure.exists() else path / "run.json", 256 * 1024
    )
    result = ContinuousRunCheckpointV1.model_validate_json(payload)
    if result.run_id != run_id:
        raise ValueError("continuous checkpoint identity changed")
    return result


def list_checkpoints(root: Path, *, on_error=None) -> tuple[ContinuousRunCheckpointV1, ...]:
    """Discover explicit run checkpoints; a sealed segment alone is not a run."""
    results = []
    for path in sorted(root.iterdir()):
        if not path.is_dir() or not (path / "run.json").is_file():
            continue
        try:
            results.append(read_checkpoint(root, path.name))
        except (OSError, ValueError) as error:
            if on_error is None:
                raise
            on_error(path.name, error)
    return tuple(results)


def write_checkpoint(path: Path, checkpoint: ContinuousRunCheckpointV1) -> None:
    _write_checkpoint_named(path, checkpoint, "run.json")


def write_publication_failure(path: Path, checkpoint: ContinuousRunCheckpointV1) -> None:
    _write_checkpoint_named(path, checkpoint, "publication-failure.json")


def _write_checkpoint_named(path: Path, checkpoint: ContinuousRunCheckpointV1, name: str) -> None:
    partial = path / f"{name}.partial"
    if partial.is_symlink():
        raise ValueError("continuous checkpoint partial cannot be a symlink")
    with partial.open("wb") as stream:
        stream.write(canonical_json_bytes(checkpoint.model_dump(mode="json")))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(partial, path / name)
    _fsync_directory(path)


class ContinuousWindowWriter:
    """Reuse version-one chunks; retain no growing run-wide manifest or ledger.

    Global sequence/generation remains in acquisition metadata. Segment-local
    indexes restart at zero, and closing a segment never touches the source.
    """

    def __init__(
        self,
        path: Path,
        run_id: str,
        configuration: ContinuousWindowConfiguration,
        *,
        radio: dict[str, Any],
    ) -> None:
        from pydantic import TypeAdapter

        TypeAdapter(Identifier).validate_python(f"{run_id}-segment-00000000")
        self.path = path
        self.run_id = run_id
        self.configuration = configuration
        self.radio = radio
        self.segment: ShortWindowWriter | None = None
        self.segment_index = 0
        self.durable_windows = 0
        self.latest_segment_id: str | None = None
        self.accepted_windows = 0
        self._closed = False

    def _open(self) -> None:
        if shutil.disk_usage(self.path).free < self.configuration.reserve_bytes:
            raise OSError("continuous recording reserve exhausted before opening a segment")
        identifier = f"{self.run_id}-segment-{self.segment_index:08d}"
        self.segment = ShortWindowWriter(
            self.path,
            identifier,
            configuration=asdict(self.configuration),
            radio=self.radio,
            receiver_ids=self.configuration.receiver_ids,
            chunk_windows=self.configuration.chunk_windows,
        )

    def _seal(self, *, stop_reason: str, failure: str | None = None) -> None:
        if self.segment is None:
            return
        segment = self.segment
        segment.finish(stop_reason=stop_reason, failure=failure)
        self.latest_segment_id = segment.session_id
        self.durable_windows += segment.window_count
        self.segment_index += 1
        self.segment = None

    def append(
        self,
        *,
        sequence: int,
        target_id: str,
        samples,
        acquisition: dict[str, Any],
        powers: tuple[dict[str, Any], ...],
    ) -> None:
        if self._closed or sequence != self.accepted_windows:
            raise ValueError("continuous writer closed or global sequence is not consecutive")
        if self.segment is None:
            self._open()
        assert self.segment is not None
        self.segment.append(
            sequence=self.segment.window_count,
            target_id=target_id,
            samples=samples,
            acquisition=acquisition,
            powers=powers,
        )
        self.accepted_windows += 1
        if self.segment.window_count == self.configuration.segment_windows:
            self._seal(stop_reason="segment_rotation")

    def finish(self, *, stop_reason: str, failure: str | None = None) -> dict[str, Any]:
        self._seal(stop_reason=stop_reason, failure=failure)
        self._closed = True
        return {
            "sealed_segments": self.segment_index,
            "durable_windows": self.durable_windows,
            "latest_segment_id": self.latest_segment_id,
        }

    def abort(self) -> None:
        if self.segment is not None:
            self.segment.abort()
        self._closed = True
