"""Release-local execution of the native known-pilot evidence worker."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

import numpy as np

from leo.analysis._streaming import validated_blocks
from leo.analysis.starlink.acceptance import NativeEvidenceExecutionResult
from leo.contracts.calibration import ReceiverFrequencyCalibrationV1, ReceiverPathIdentityV1
from leo.contracts.digests import canonical_digest, sha256_digest
from leo.contracts.scientific import (
    MatchedPilotAcceptanceConfigV1,
    PilotWindowDecisionV1,
    TrustedNativeReleaseEvidenceV2,
)
from leo.pipeline import IqReader
from leo.qualification.native_release import (
    _beneath_qnap,
    _file_digest,
    _open_absolute_directory,
    _resolve_regular_file,
    _runtime_package_tree_digest,
)

_MAX_OUTPUT_BYTES = 8 * 1024 * 1024
_WORKER_ENVIRONMENT = {
    "HOME": "/nonexistent",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PATH": "/usr/bin:/bin",
    "PYTHONDONTWRITEBYTECODE": "1",
}
_WORKER_ENVIRONMENT_DIGEST = canonical_digest(_WORKER_ENVIRONMENT)


class ReleaseLocalNativeEvidenceExecutor:
    """Snapshot one receiver and execute only the validated release-local worker."""

    def __init__(self, *, scratch_root: Path = Path("/var/tmp")) -> None:
        if not scratch_root.is_absolute() or _beneath_qnap(scratch_root):
            raise ValueError("native evidence scratch must be absolute local storage")
        scratch_fd = _open_absolute_directory(scratch_root)
        os.close(scratch_fd)
        self._scratch_root = scratch_root

    def execute(
        self,
        *,
        iq: IqReader,
        path_identity: ReceiverPathIdentityV1,
        calibration: ReceiverFrequencyCalibrationV1,
        release: TrustedNativeReleaseEvidenceV2,
        config: MatchedPilotAcceptanceConfigV1,
    ) -> NativeEvidenceExecutionResult:
        release_root = Path(release.release_path)
        worker = release_root / "tools/native_evidence_worker.py"
        interpreter = release_root / ".venv/bin/python"
        self._verify_executables(worker, interpreter, release)
        scratch_fd = _open_absolute_directory(self._scratch_root)
        try:
            with _temporary_file_at(scratch_fd) as snapshot:
                iq_digest = _snapshot_receiver(
                    snapshot.fileno(),
                    iq=iq,
                    receiver_id=path_identity.receiver_id,
                    block_samples=config.block_sample_count,
                )
                expected_window_digests = _expected_window_iq_digests(snapshot.fileno())
                with (
                    _temporary_file_at(scratch_fd) as output,
                    _temporary_file_at(scratch_fd) as errors,
                ):
                    subprocess.run(
                        (
                            str(interpreter),
                            "-I",
                            str(worker),
                            "--iq-fd",
                            str(snapshot.fileno()),
                            "--iq-sha256",
                            iq_digest,
                            "--config-json",
                            config.model_dump_json(),
                            "--calibration-json",
                            calibration.model_dump_json(),
                        ),
                        cwd=release_root,
                        env=_WORKER_ENVIRONMENT,
                        stdin=subprocess.DEVNULL,
                        stdout=output,
                        stderr=errors,
                        pass_fds=(snapshot.fileno(),),
                        timeout=6 * 60 * 60,
                        check=True,
                    )
                    output.seek(0)
                    stdout = output.read(_MAX_OUTPUT_BYTES + 1)
        finally:
            os.close(scratch_fd)
        if len(stdout) > _MAX_OUTPUT_BYTES:
            raise ValueError("native evidence worker output exceeded its bound")
        self._verify_executables(worker, interpreter, release)
        payload = json.loads(stdout)
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != 1
            or payload.get("iq_sha256") != iq_digest
            or payload.get("config_digest") != config.config_digest
            or payload.get("calibration_digest") != calibration.calibration_digest
            or payload.get("runtime_package_tree_digest") != release.runtime_package_tree_digest
        ):
            raise ValueError("native evidence worker output binding is invalid")
        decisions = tuple(
            PilotWindowDecisionV1.model_validate(item) for item in payload.get("decisions", ())
        )
        if len(decisions) != 600 or tuple(item.window_index for item in decisions) != tuple(
            range(600)
        ):
            raise ValueError("native evidence worker did not return all 600 ordered decisions")
        if any(
            decision.sample_start != index * config.interval_sample_count
            or decision.window_iq_digest != expected_window_digests[index]
            for index, decision in enumerate(decisions)
        ):
            raise ValueError("native evidence decisions differ from the exact IQ windows")
        return NativeEvidenceExecutionResult(
            decisions=decisions,
            execution_environment_digest=_WORKER_ENVIRONMENT_DIGEST,
            worker_output_digest=sha256_digest(stdout),
        )

    @staticmethod
    def _verify_executables(
        worker: Path,
        interpreter: Path,
        release: TrustedNativeReleaseEvidenceV2,
    ) -> None:
        if _file_digest(worker) != release.worker_digest:
            raise ValueError("validated native evidence worker changed")
        target = _resolve_regular_file(interpreter)
        if _file_digest(target) != release.interpreter_digest:
            raise ValueError("validated native evidence interpreter changed")
        if _runtime_package_tree_digest(Path(release.release_path)) != (
            release.runtime_package_tree_digest
        ):
            raise ValueError("validated installed leo runtime package changed")


def _snapshot_receiver(
    descriptor: int,
    *,
    iq: IqReader,
    receiver_id: int,
    block_samples: int,
) -> str:
    if iq.sample_count != 150_000_000 or iq.sample_rate_hz != 2_500_000:
        raise ValueError("native evidence requires the exact 2.5 MS/s, 60 second dwell")
    try:
        receiver_index = iq.receiver_ids.index(receiver_id)
    except ValueError as error:
        raise ValueError("native evidence receiver is absent from IQ scope") from error
    digest = hashlib.sha256()
    expected_start = 0
    for block in validated_blocks(iq, block_samples=block_samples):
        if block.metadata.session_sample_start != expected_start:
            raise ValueError("native evidence IQ snapshot cannot contain gaps")
        selected = np.ascontiguousarray(block.samples[:, receiver_index, :], dtype="<i2")
        payload = selected.tobytes(order="C")
        _write_all(descriptor, payload)
        digest.update(payload)
        expected_start += block.metadata.sample_count
    if expected_start != iq.sample_count:
        raise ValueError("native evidence IQ snapshot is incomplete")
    os.fsync(descriptor)
    os.lseek(descriptor, 0, os.SEEK_SET)
    return "sha256:" + digest.hexdigest()


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise OSError("native IQ snapshot write made no progress")
        offset += written


def _expected_window_iq_digests(descriptor: int) -> tuple[str, ...]:
    digests: list[str] = []
    window_bytes = 25_000 * 4
    for index in range(600):
        payload = os.pread(descriptor, window_bytes, index * 250_000 * 4)
        if len(payload) != window_bytes:
            raise ValueError("native IQ snapshot lacks an exact scheduled window")
        raw = np.frombuffer(payload, dtype="<i2").reshape(25_000, 2)
        samples = ((raw[:, 0] + 1j * raw[:, 1]) / 32_768.0).astype(np.complex64)
        digests.append(sha256_digest(samples.tobytes(order="C")))
    return tuple(digests)


@contextmanager
def _temporary_file_at(directory_fd: int) -> Iterator[BinaryIO]:
    try:
        descriptor = os.open(
            ".",
            os.O_RDWR | os.O_TMPFILE,
            0o600,
            dir_fd=directory_fd,
        )
    except OSError as error:
        raise ValueError("native evidence scratch does not support anonymous files") from error
    with os.fdopen(descriptor, "w+b", buffering=0) as stream:
        yield stream
