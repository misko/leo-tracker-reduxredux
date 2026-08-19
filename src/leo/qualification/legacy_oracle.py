"""Fail-closed launcher and sealed receipt for the pinned legacy pilot oracle.

This qualification component never imports ``leo_tracker``.  The historical
implementation is executed in a caller-supplied, clean checkout by a separate
Python process.  Production composition roots do not reference this module.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import StringConstraints, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest, canonical_json_bytes
from leo.contracts.scientific import PilotWindowDecisionV1

LEGACY_REVISION = "0bb80d14759fd8496b74e7d3219a690be18565a6"
LEGACY_UV_LOCK_SHA256 = "sha256:7ddef431a8ce54f1f7fcad5e228ae856e352a65f0ce0a8406707c15aee5d87f9"
LEGACY_ACQUISITION_SOURCE_SHA256 = (
    "sha256:6e01091a8029df5475776fd298e5db5b01538b5ee8a02d91739ba15030261640"
)
LEGACY_ANALYSIS_SOURCE_SHA256 = (
    "sha256:db46c03395900ac862f82d8438afdc6dcf1e3380404689ff5c62aac2f042ba77"
)
LEGACY_DECODE_SOURCE_SHA256 = (
    "sha256:2ed3a4ed87c14a6bc028539bc83a671e100d9fe6b35732f2db14adab05273f84"
)
WINDOW_COUNT = 600
WINDOW_SAMPLES = 25_000
WINDOW_INTERVAL_SAMPLES = 250_000
DWELL_SAMPLES = 150_000_000
IQ_BYTES = DWELL_SAMPLES * 2 * 2
_MAX_WORKER_OUTPUT_BYTES = 4 * 1024 * 1024


class LegacyOracleEnvironmentV1(ContractModel):
    schema_version: Literal[1] = 1
    python_executable: Annotated[str, StringConstraints(min_length=1, max_length=4096)]
    python_sha256: Sha256Digest
    python_version: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    numpy_version: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    scipy_version: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    installed_distributions: tuple[
        Annotated[str, StringConstraints(min_length=3, max_length=512)], ...
    ]
    environment_fingerprint_sha256: Sha256Digest

    @model_validator(mode="after")
    def _fingerprint_matches(self) -> Self:
        expected = canonical_digest(
            self.model_dump(mode="json", exclude={"environment_fingerprint_sha256"})
        )
        if self.environment_fingerprint_sha256 != expected:
            raise ValueError(f"legacy environment fingerprint does not match content: {expected}")
        return self


class LegacyOracleConfigV1(ContractModel):
    schema_version: Literal[1] = 1
    source_revision: str = LEGACY_REVISION
    source_tree: Annotated[str, StringConstraints(min_length=40, max_length=64)]
    uv_lock_sha256: Sha256Digest = LEGACY_UV_LOCK_SHA256
    acquisition_source_sha256: Sha256Digest
    analysis_source_sha256: Sha256Digest
    decode_source_sha256: Sha256Digest
    worker_sha256: Sha256Digest
    legacy_python_sha256: Sha256Digest
    required_environment_fingerprint_sha256: Sha256Digest
    sample_rate_hz: Literal[2_500_000] = 2_500_000
    dwell_sample_count: Literal[150_000_000] = 150_000_000
    window_sample_count: Literal[25_000] = 25_000
    interval_sample_count: Literal[250_000] = 250_000
    scheduled_window_count: Literal[600] = 600
    input_format: Literal["ci16_le_interleaved_iq_single_receiver"] = (
        "ci16_le_interleaved_iq_single_receiver"
    )
    normalization: Literal["complex64(I+jQ)/32768"] = "complex64(I+jQ)/32768"
    edge: Literal["lower"] = "lower"
    acquisition_method: Literal["pilot_symbolwise_v3"] = "pilot_symbolwise_v3"
    acquisition_span_hz: float = 0.0
    acquisition_step_hz: float = 500_000.0
    exact_subband_rate_hz: float = 2_500_000.0
    single_match_margin: float = 0.025
    single_symbol_margin: float = 0.03
    cfo_semantics: Literal["absolute_digital_offset_hz"] = "absolute_digital_offset_hz"
    receiver_center_hz: float
    config_digest: Sha256Digest

    @model_validator(mode="after")
    def _digest_matches(self) -> Self:
        frozen = (
            self.source_revision,
            self.uv_lock_sha256,
            self.acquisition_source_sha256,
            self.analysis_source_sha256,
            self.decode_source_sha256,
            self.acquisition_span_hz,
            self.acquisition_step_hz,
            self.exact_subband_rate_hz,
            self.single_match_margin,
            self.single_symbol_margin,
        )
        expected_frozen = (
            LEGACY_REVISION,
            LEGACY_UV_LOCK_SHA256,
            LEGACY_ACQUISITION_SOURCE_SHA256,
            LEGACY_ANALYSIS_SOURCE_SHA256,
            LEGACY_DECODE_SOURCE_SHA256,
            0.0,
            500_000.0,
            2_500_000.0,
            0.025,
            0.03,
        )
        if frozen != expected_frozen:
            raise ValueError("legacy oracle source or scientific constants are not frozen v1")
        expected = canonical_digest(self.model_dump(mode="json", exclude={"config_digest"}))
        if self.config_digest != expected:
            raise ValueError(f"legacy oracle config digest does not match content: {expected}")
        return self


class LegacyOracleReceiptV1(ContractModel):
    schema_version: Literal[1] = 1
    kind: Literal["sealed_legacy_pilot_oracle"] = "sealed_legacy_pilot_oracle"
    status: Literal["complete"] = "complete"
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    attribution_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False
    iq_path: Annotated[str, StringConstraints(min_length=1, max_length=4096)]
    iq_sha256: Sha256Digest
    iq_size_bytes: int = IQ_BYTES
    config: LegacyOracleConfigV1
    environment: LegacyOracleEnvironmentV1
    decisions: tuple[PilotWindowDecisionV1, ...]
    receipt_digest: Sha256Digest

    @model_validator(mode="after")
    def _receipt_is_complete_and_sealed(self) -> Self:
        if len(self.decisions) != WINDOW_COUNT:
            raise ValueError("legacy oracle receipt must retain exactly 600 decisions")
        if self.iq_size_bytes != IQ_BYTES:
            raise ValueError("legacy oracle receipt has the wrong IQ geometry")
        if tuple(item.window_index for item in self.decisions) != tuple(range(WINDOW_COUNT)):
            raise ValueError("legacy oracle decisions must be ordered over all 600 windows")
        if any(item.source != "legacy_reference" for item in self.decisions):
            raise ValueError("legacy oracle decisions must declare legacy_reference")
        expected = canonical_digest(self.model_dump(mode="json", exclude={"receipt_digest"}))
        if self.receipt_digest != expected:
            raise ValueError(f"legacy oracle receipt digest does not match content: {expected}")
        return self


def load_sealed_legacy_decisions(path: Path) -> tuple[PilotWindowDecisionV1, ...]:
    """Validate a sealed receipt for ``SealedLegacyReferenceDecisionPort``."""

    payload = _read_bounded_json(_safe_input_file(path, "oracle receipt"))
    return LegacyOracleReceiptV1.model_validate(payload).decisions


def run_legacy_oracle(
    *,
    legacy_root: Path,
    legacy_python: Path,
    iq_path: Path,
    expected_iq_sha256: str,
    expected_environment_fingerprint_sha256: str,
    receiver_center_hz: float,
    output_path: Path,
    worker_path: Path | None = None,
) -> LegacyOracleReceiptV1:
    """Execute the frozen worker and atomically publish a validated receipt."""

    root = _safe_directory(legacy_root, "legacy root")
    python = _safe_python_executable(legacy_python)
    iq = _safe_input_file(iq_path, "IQ input")
    output = _safe_new_output(output_path)
    worker = _safe_input_file(
        worker_path or Path(__file__).parents[3] / "tools" / "legacy_oracle_worker.py",
        "legacy worker",
    )
    if iq.stat(follow_symlinks=False).st_size != IQ_BYTES:
        raise ValueError(f"IQ input must contain exactly {IQ_BYTES} bytes")
    expected_iq_sha256 = _validate_digest(expected_iq_sha256, "expected IQ digest")
    expected_environment_fingerprint_sha256 = _validate_digest(
        expected_environment_fingerprint_sha256, "expected environment fingerprint"
    )

    revision = _git(root, "rev-parse", "HEAD")
    if revision != LEGACY_REVISION:
        raise ValueError(f"legacy checkout must be pinned to {LEGACY_REVISION}; got {revision}")
    if _git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("legacy checkout must be completely clean")
    source_tree = _git(root, "rev-parse", "HEAD^{tree}")
    if _file_digest(root / "uv.lock") != LEGACY_UV_LOCK_SHA256:
        raise ValueError("legacy uv.lock does not match the reviewed revision")
    source_digests = _legacy_source_digests(root)
    if _file_digest(iq) != expected_iq_sha256:
        raise ValueError("IQ input digest does not match --iq-sha256")

    worker_digest = _file_digest(worker)
    python_digest = _file_digest(python)
    venv_root = root / ".venv"
    if venv_root not in python.parents:
        raise ValueError("legacy Python must be the pinned checkout's .venv interpreter")
    config_without_digest = {
        "schema_version": 1,
        "source_revision": LEGACY_REVISION,
        "source_tree": source_tree,
        "uv_lock_sha256": LEGACY_UV_LOCK_SHA256,
        "acquisition_source_sha256": source_digests[0],
        "analysis_source_sha256": source_digests[1],
        "decode_source_sha256": source_digests[2],
        "worker_sha256": worker_digest,
        "legacy_python_sha256": python_digest,
        "required_environment_fingerprint_sha256": expected_environment_fingerprint_sha256,
        "sample_rate_hz": 2_500_000,
        "dwell_sample_count": DWELL_SAMPLES,
        "window_sample_count": WINDOW_SAMPLES,
        "interval_sample_count": WINDOW_INTERVAL_SAMPLES,
        "scheduled_window_count": WINDOW_COUNT,
        "input_format": "ci16_le_interleaved_iq_single_receiver",
        "normalization": "complex64(I+jQ)/32768",
        "edge": "lower",
        "acquisition_method": "pilot_symbolwise_v3",
        "acquisition_span_hz": 0.0,
        "acquisition_step_hz": 500_000.0,
        "exact_subband_rate_hz": 2_500_000.0,
        "single_match_margin": 0.025,
        "single_symbol_margin": 0.03,
        "cfo_semantics": "absolute_digital_offset_hz",
        "receiver_center_hz": float(receiver_center_hz),
    }
    config = LegacyOracleConfigV1.model_validate(
        {**config_without_digest, "config_digest": canonical_digest(config_without_digest)}
    )
    temporary = output.with_name(f".{output.name}.{os.getpid()}.worker")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(root / "src")
    argv = [
        str(python),
        "-I",
        str(worker),
        "--legacy-root",
        str(root),
        "--iq-path",
        str(iq),
        "--iq-sha256",
        expected_iq_sha256,
        "--config-json",
        json.dumps(config.model_dump(mode="json"), sort_keys=True),
        "--output",
        str(temporary),
    ]
    try:
        subprocess.run(  # noqa: S603 - every executable and argument is explicit and validated
            argv,
            cwd=root,
            env=environment,
            check=True,
            stdin=subprocess.DEVNULL,
            timeout=6 * 60 * 60,
        )
        if (
            _git(root, "rev-parse", "HEAD") != LEGACY_REVISION
            or _git(root, "rev-parse", "HEAD^{tree}") != source_tree
            or _git(root, "status", "--porcelain=v1", "--untracked-files=all")
            or _file_digest(root / "uv.lock") != LEGACY_UV_LOCK_SHA256
            or _legacy_source_digests(root) != source_digests
            or _file_digest(worker) != worker_digest
            or _file_digest(python) != python_digest
        ):
            raise ValueError("legacy source, lock, or worker changed during evaluation")
        worker_payload = _read_bounded_json(_safe_input_file(temporary, "worker output"))
        receipt = _seal_worker_payload(
            worker_payload,
            iq=iq,
            iq_sha256=expected_iq_sha256,
            config=config,
            legacy_python=python,
        )
        _atomic_create(output, canonical_json_bytes(receipt.model_dump(mode="json")) + b"\n")
        return receipt
    finally:
        temporary.unlink(missing_ok=True)


def _seal_worker_payload(
    payload: object,
    *,
    iq: Path,
    iq_sha256: str,
    config: LegacyOracleConfigV1,
    legacy_python: Path | None = None,
) -> LegacyOracleReceiptV1:
    if not isinstance(payload, dict):
        raise ValueError("legacy worker output must be an object")
    if payload.get("config_digest") != config.config_digest:
        raise ValueError("legacy worker output has the wrong config digest")
    if payload.get("iq_sha256") != iq_sha256:
        raise ValueError("legacy worker output has the wrong IQ digest")
    environment = LegacyOracleEnvironmentV1.model_validate(payload.get("environment"))
    if legacy_python is not None and not os.path.samefile(
        environment.python_executable, legacy_python
    ):
        raise ValueError("legacy worker ran under a different Python executable")
    if environment.python_sha256 != config.legacy_python_sha256:
        raise ValueError("legacy worker Python digest does not match the sealed config")
    if (
        environment.environment_fingerprint_sha256
        != config.required_environment_fingerprint_sha256
    ):
        raise ValueError("legacy worker environment is not the separately reviewed environment")
    decisions = tuple(
        PilotWindowDecisionV1.model_validate(item) for item in payload.get("decisions", [])
    )
    values = {
        "schema_version": 1,
        "kind": "sealed_legacy_pilot_oracle",
        "status": "complete",
        "candidate_only": True,
        "specificity_claimed": False,
        "attribution_claimed": False,
        "payload_decoded": False,
        "iq_path": str(iq),
        "iq_sha256": iq_sha256,
        "iq_size_bytes": IQ_BYTES,
        "config": config.model_dump(mode="json"),
        "environment": environment.model_dump(mode="json"),
        "decisions": [item.model_dump(mode="json") for item in decisions],
    }
    return LegacyOracleReceiptV1.model_validate(
        {**values, "receipt_digest": canonical_digest(values)}
    )


def _safe_input_file(path: Path, label: str) -> Path:
    candidate = _lexical_absolute(path, label)
    _reject_symlink_components(candidate, label)
    info = candidate.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ValueError(f"{label} must be a non-symlink regular file")
    return candidate


def _safe_directory(path: Path, label: str) -> Path:
    candidate = _lexical_absolute(path, label)
    _reject_symlink_components(candidate, label)
    info = candidate.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise ValueError(f"{label} must be a non-symlink directory")
    return candidate


def _safe_python_executable(path: Path) -> Path:
    """Allow the conventional venv ``bin/python`` symlink without following QNAP."""

    candidate = _lexical_absolute(path, "legacy Python")
    _reject_symlink_components(candidate.parent, "legacy Python parent")
    info = candidate.lstat()
    if stat.S_ISREG(info.st_mode):
        target = candidate
    elif stat.S_ISLNK(info.st_mode):
        link = Path(os.readlink(candidate))
        target = link if link.is_absolute() else candidate.parent / link
        target = _lexical_absolute(target, "legacy Python target")
        _reject_symlink_components(target, "legacy Python target")
        if not stat.S_ISREG(target.lstat().st_mode):
            raise ValueError("legacy Python symlink must target a regular file")
    else:
        raise ValueError("legacy Python must be a regular file or venv symlink")
    if not os.access(candidate, os.X_OK):
        raise ValueError("legacy Python must be executable")
    return candidate


def _safe_new_output(path: Path) -> Path:
    candidate = _lexical_absolute(path, "output path")
    _reject_symlink_components(candidate.parent, "output parent")
    try:
        candidate.lstat()
    except FileNotFoundError:
        pass
    else:
        raise FileExistsError(f"output already exists: {candidate}")
    _safe_directory(candidate.parent, "output parent")
    return candidate


def _reject_symlink_components(path: Path, label: str) -> None:
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        try:
            info = current.lstat()
        except FileNotFoundError:
            return
        if stat.S_ISLNK(info.st_mode):
            raise ValueError(f"{label} cannot traverse a symlink: {current}")


def _lexical_absolute(path: Path, label: str) -> Path:
    candidate = Path(os.path.abspath(os.fspath(path)))
    if not candidate.is_absolute():
        raise ValueError(f"{label} must be absolute")
    if candidate == Path("/mnt/qnap01") or Path("/mnt/qnap01") in candidate.parents:
        raise ValueError(f"{label} cannot be beneath read-only /mnt/qnap01")
    return candidate


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(  # noqa: S603,S607 - fixed git executable and literal arguments
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _legacy_source_digests(root: Path) -> tuple[str, str, str]:
    paths = (
        root / "src/leo_tracker/radio/beacon/acquisition.py",
        root / "src/leo_tracker/radio/beacon/analysis.py",
        root / "src/leo_tracker/radio/beacon/decode.py",
    )
    values = tuple(_file_digest(_safe_input_file(path, "legacy source")) for path in paths)
    expected = (
        LEGACY_ACQUISITION_SOURCE_SHA256,
        LEGACY_ANALYSIS_SOURCE_SHA256,
        LEGACY_DECODE_SOURCE_SHA256,
    )
    if values != expected:
        raise ValueError("legacy acquisition, gate, or QAM source digest is not frozen v1")
    return values


def _validate_digest(value: str, label: str) -> str:
    if len(value) != 71 or not value.startswith("sha256:"):
        raise ValueError(f"{label} must be a tagged SHA-256 digest")
    try:
        bytes.fromhex(value.removeprefix("sha256:"))
    except ValueError as exc:
        raise ValueError(f"{label} must be a tagged SHA-256 digest") from exc
    return value


def _read_bounded_json(path: Path) -> object:
    if path.stat(follow_symlinks=False).st_size > _MAX_WORKER_OUTPUT_BYTES:
        raise ValueError("legacy oracle evidence exceeds its bounded size")
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_create(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o440)
    try:
        with os.fdopen(descriptor, "wb") as target:
            target.write(payload)
            target.flush()
            os.fsync(target.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the pinned qualification-only oracle")
    parser.add_argument("--legacy-root", type=Path, required=True)
    parser.add_argument("--legacy-python", type=Path, required=True)
    parser.add_argument("--iq-path", type=Path, required=True)
    parser.add_argument("--iq-sha256", required=True)
    parser.add_argument("--environment-sha256", required=True)
    parser.add_argument("--receiver-center-hz", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    receipt = run_legacy_oracle(
        legacy_root=arguments.legacy_root,
        legacy_python=arguments.legacy_python,
        iq_path=arguments.iq_path,
        expected_iq_sha256=arguments.iq_sha256,
        expected_environment_fingerprint_sha256=arguments.environment_sha256,
        receiver_center_hz=arguments.receiver_center_hz,
        output_path=arguments.output,
    )
    print(receipt.receipt_digest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
