"""Fail-closed launcher for the qualification-only pinned legacy pilot oracle."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import secrets
import stat
import subprocess
import sys
from pathlib import Path, PurePath
from typing import Annotated, Literal, Self

from pydantic import StringConstraints, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest, canonical_json_bytes
from leo.contracts.scientific import PilotWindowDecisionV1
from leo.storage import PinnedLocalRoot

LEGACY_ROOT = Path("/home/mouse9911/gits/leo-tracker-oracle-0bb80d1")
LEGACY_PYTHON = LEGACY_ROOT / ".venv/bin/python"
LEGACY_REVISION = "0bb80d14759fd8496b74e7d3219a690be18565a6"
LEGACY_SOURCE_TREE = "631bc74222f1d03dad99f418ee21e75d94dbb27d"
LEGACY_EXECUTABLE_TREE_DIGEST = (
    "sha256:b2c0542f431118dc7f1ebc625e375cd1d91f48fd99db43f0a889f7c061da503a"
)
LEGACY_UV_LOCK_SHA256 = "sha256:7ddef431a8ce54f1f7fcad5e228ae856e352a65f0ce0a8406707c15aee5d87f9"
ENVIRONMENT_MANIFEST = Path(
    "/home/mouse9911/gits/leo-tracker-reduxredux/"
    "config/qualification/legacy-oracle-environment-v1.json"
)
ENVIRONMENT_MANIFEST_FILE_SHA256 = (
    "sha256:e5078d9d619f0c5782a673095b6852231c5c97c5ae33c796c04bc01c271e8e6a"
)
ENVIRONMENT_MANIFEST_DIGEST = (
    "sha256:dde115d44ca682b61d9f468757ee3a9ee9596705dbc1ecea7b78a3cb8b810b56"
)
ENVIRONMENT_EXTERNAL_EXECUTABLES_DIGEST = (
    "sha256:64f1e637f430b218363d2a50b469f6ccc1bd05864118a1710f27ca87bdb71b8d"
)
WORKER_PATH = Path("/home/mouse9911/gits/leo-tracker-reduxredux/tools/legacy_oracle_worker.py")
# Updated only after independently reviewing the exact worker file.
WORKER_SHA256 = "sha256:07162739e640b824421a3640ccd53001cdaee876cd429203496b8e1f6b209e77"
GIT_PATH = Path("/usr/bin/git")
GIT_SHA256 = "sha256:5516c9f362c29376ab9a499a33082f9f611941d8c75930c880e30ad109e39c9a"

WINDOW_COUNT = 600
WINDOW_SAMPLES = 25_000
WINDOW_INTERVAL_SAMPLES = 250_000
DWELL_SAMPLES = 150_000_000
IQ_BYTES = DWELL_SAMPLES * 4
_MAX_RECEIPT_BYTES = 4 * 1024 * 1024
_PUBLICATION_METHOD = "dirfd-o_nofollow-o_excl-file-and-directory-fsync-v1"


class LegacyOracleEnvironmentV1(ContractModel):
    schema_version: Literal[1] = 1
    manifest_digest: Sha256Digest
    python_executable: Annotated[str, StringConstraints(min_length=1, max_length=4096)]
    external_executable_files: tuple[dict[str, object], ...]

    @model_validator(mode="after")
    def _is_the_frozen_environment(self) -> Self:
        external_digest = canonical_digest(list(self.external_executable_files))
        if (
            self.manifest_digest != ENVIRONMENT_MANIFEST_DIGEST
            or self.python_executable != str(LEGACY_PYTHON)
            or external_digest != ENVIRONMENT_EXTERNAL_EXECUTABLES_DIGEST
        ):
            raise ValueError("worker did not use the frozen legacy environment")
        return self


class LegacyOracleConfigV1(ContractModel):
    schema_version: Literal[1] = 1
    source_revision: str
    source_tree: str
    executable_tree_digest: Sha256Digest
    uv_lock_sha256: Sha256Digest
    legacy_root: str
    environment_manifest_digest: Sha256Digest
    worker_path: str
    worker_sha256: Sha256Digest
    sample_rate_hz: Literal[2_500_000] = 2_500_000
    dwell_sample_count: Literal[150_000_000] = 150_000_000
    window_sample_count: Literal[25_000] = 25_000
    interval_sample_count: Literal[250_000] = 250_000
    scheduled_window_count: Literal[600] = 600
    input_format: Literal["ci16_le_interleaved_iq_single_receiver"] = (
        "ci16_le_interleaved_iq_single_receiver"
    )
    normalization: Literal["complex64(I+jQ)/32768"] = "complex64(I+jQ)/32768"
    edge: Literal["lower"]
    acquisition_method: Literal["pilot_symbolwise_v3"] = "pilot_symbolwise_v3"
    acquisition_span_hz: float
    acquisition_step_hz: float
    exact_subband_rate_hz: float
    single_match_margin: float
    single_symbol_margin: float
    cfo_semantics: Literal["absolute_digital_offset_hz"] = "absolute_digital_offset_hz"
    receiver_center_hz: float
    config_digest: Sha256Digest

    @model_validator(mode="after")
    def _is_the_frozen_configuration(self) -> Self:
        actual = (
            self.source_revision,
            self.source_tree,
            self.executable_tree_digest,
            self.uv_lock_sha256,
            self.legacy_root,
            self.environment_manifest_digest,
            self.worker_path,
            self.worker_sha256,
            self.acquisition_span_hz,
            self.acquisition_step_hz,
            self.exact_subband_rate_hz,
            self.single_match_margin,
            self.single_symbol_margin,
        )
        expected = (
            LEGACY_REVISION,
            LEGACY_SOURCE_TREE,
            LEGACY_EXECUTABLE_TREE_DIGEST,
            LEGACY_UV_LOCK_SHA256,
            str(LEGACY_ROOT),
            ENVIRONMENT_MANIFEST_DIGEST,
            str(WORKER_PATH),
            WORKER_SHA256,
            0.0,
            500_000.0,
            2_500_000.0,
            0.025,
            0.03,
        )
        if actual != expected:
            raise ValueError("legacy oracle source, environment, worker, or gates are not v1")
        digest = canonical_digest(self.model_dump(mode="json", exclude={"config_digest"}))
        if self.config_digest != digest:
            raise ValueError(f"legacy oracle config digest does not match content: {digest}")
        return self


class LegacyOracleReceiptV1(ContractModel):
    schema_version: Literal[1] = 1
    kind: Literal["sealed_legacy_pilot_oracle"] = "sealed_legacy_pilot_oracle"
    status: Literal["complete"] = "complete"
    publication_method: Literal["dirfd-o_nofollow-o_excl-file-and-directory-fsync-v1"] = (
        "dirfd-o_nofollow-o_excl-file-and-directory-fsync-v1"
    )
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    attribution_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False
    iq_path: Annotated[str, StringConstraints(min_length=1, max_length=4096)]
    iq_sha256: Sha256Digest
    iq_size_bytes: int
    config: LegacyOracleConfigV1
    environment: LegacyOracleEnvironmentV1
    decisions: tuple[PilotWindowDecisionV1, ...]
    worker_output_digest: Sha256Digest
    receipt_digest: Sha256Digest

    @model_validator(mode="after")
    def _is_complete_and_frozen(self) -> Self:
        if self.iq_size_bytes != IQ_BYTES or len(self.decisions) != WINDOW_COUNT:
            raise ValueError("legacy oracle receipt must retain the exact dwell and 600 windows")
        if tuple(item.window_index for item in self.decisions) != tuple(range(WINDOW_COUNT)):
            raise ValueError("legacy oracle decisions must be ordered over all 600 windows")
        if any(item.source != "legacy_reference" for item in self.decisions):
            raise ValueError("legacy oracle decisions must declare legacy_reference")
        if any(
            item.algorithm_id != "leo-tracker-pilot-symbolwise-v3-single-rx"
            or item.algorithm_version != LEGACY_REVISION
            or item.status.value != "evaluated"
            for item in self.decisions
        ):
            raise ValueError("every decision must be evaluated by the exact frozen legacy kernel")
        digest = canonical_digest(self.model_dump(mode="json", exclude={"receipt_digest"}))
        if self.receipt_digest != digest:
            raise ValueError(f"legacy oracle receipt digest does not match content: {digest}")
        return self


def load_sealed_legacy_decisions(
    *, evidence_root: Path, receipt_name: str
) -> tuple[PilotWindowDecisionV1, ...]:
    """Load only a confined, exclusively published, semantically frozen receipt."""

    return load_sealed_legacy_receipt(
        evidence_root=evidence_root,
        receipt_name=receipt_name,
    ).decisions


def load_sealed_legacy_receipt(*, evidence_root: Path, receipt_name: str) -> LegacyOracleReceiptV1:
    """Load the complete confined receipt for scope-bound scientific evidence."""

    root = _safe_directory(evidence_root, "qualification evidence root")
    name = _safe_leaf_name(receipt_name)
    root_fd = _open_directory(root)
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root_fd)
        try:
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o440
                or info.st_nlink != 1
                or info.st_size > _MAX_RECEIPT_BYTES
            ):
                raise ValueError("oracle receipt lacks frozen publication semantics")
            payload = _read_json_fd(descriptor, _MAX_RECEIPT_BYTES)
        finally:
            os.close(descriptor)
    finally:
        os.close(root_fd)
    return LegacyOracleReceiptV1.model_validate(payload)


def load_sealed_legacy_receipt_pinned(
    *, evidence_root: PinnedLocalRoot, receipt_name: str
) -> LegacyOracleReceiptV1:
    """Load a receipt relative to a retained evidence-directory capability."""

    name = _safe_leaf_name(receipt_name)
    root_fd = os.dup(evidence_root.fileno())
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root_fd)
        try:
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o440
                or info.st_nlink != 1
                or info.st_size > _MAX_RECEIPT_BYTES
            ):
                raise ValueError("oracle receipt lacks frozen publication semantics")
            payload = _read_json_fd(descriptor, _MAX_RECEIPT_BYTES)
        finally:
            os.close(descriptor)
    finally:
        os.close(root_fd)
    return LegacyOracleReceiptV1.model_validate(payload)


def run_legacy_oracle(
    *,
    iq_path: Path,
    expected_iq_sha256: str,
    receiver_center_hz: float,
    evidence_root: Path,
    receipt_name: str,
) -> LegacyOracleReceiptV1:
    """Run the exact reviewed oracle and publish beneath one evidence dir-fd."""

    iq = _safe_input_file(iq_path, "IQ input")
    expected_iq_sha256 = _validate_digest(expected_iq_sha256, "expected IQ digest")
    evidence = _safe_directory(evidence_root, "qualification evidence root")
    output_name = _safe_leaf_name(receipt_name)
    root_fd = _open_directory(evidence)
    lock_fd = _acquire_qualification_lock(root_fd)
    source_fd: int | None = None
    snapshot_fd: int | None = None
    try:
        source_fd = os.open(iq, os.O_RDONLY | os.O_NOFOLLOW)
        if os.fstat(source_fd).st_size != IQ_BYTES:
            raise ValueError(f"IQ input must contain exactly {IQ_BYTES} bytes")
        _assert_output_absent(root_fd, output_name)
        identities = _verify_all_frozen_identities()
        snapshot_fd = _snapshot_iq(root_fd, source_fd, expected_iq_sha256)
        config = _frozen_config(receiver_center_hz)
        worker_payload, worker_output_digest = _execute_worker(
            snapshot_fd, expected_iq_sha256, config
        )
        if _verify_all_frozen_identities() != identities:
            raise ValueError("legacy source, environment, worker, or tools changed during run")
        receipt = _seal_worker_payload(
            worker_payload,
            iq=iq,
            iq_sha256=expected_iq_sha256,
            config=config,
            worker_output_digest=worker_output_digest,
        )
        payload = canonical_json_bytes(receipt.model_dump(mode="json")) + b"\n"
        _atomic_create_confined(root_fd, output_name, payload)
        return receipt
    finally:
        if snapshot_fd is not None:
            os.close(snapshot_fd)
        if source_fd is not None:
            os.close(source_fd)
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
        os.close(root_fd)


def run_legacy_oracle_fd(
    *,
    iq_fd: int,
    iq_label: str,
    expected_iq_sha256: str,
    receiver_center_hz: float,
    evidence_root: Path | PinnedLocalRoot,
    receipt_name: str,
) -> LegacyOracleReceiptV1:
    """Run the frozen oracle from an already-confined anonymous regular file."""

    if not iq_label or len(iq_label) > 4096:
        raise ValueError("IQ evidence label is invalid")
    info = os.fstat(iq_fd)
    if not stat.S_ISREG(info.st_mode) or info.st_size != IQ_BYTES:
        raise ValueError(f"IQ descriptor must contain exactly {IQ_BYTES} regular-file bytes")
    expected_iq_sha256 = _validate_digest(expected_iq_sha256, "expected IQ digest")
    output_name = _safe_leaf_name(receipt_name)
    if isinstance(evidence_root, PinnedLocalRoot):
        root_fd = os.dup(evidence_root.fileno())
    else:
        evidence = _safe_directory(evidence_root, "qualification evidence root")
        root_fd = _open_directory(evidence)
    lock_fd = _acquire_qualification_lock(root_fd)
    snapshot_fd: int | None = None
    try:
        _assert_output_absent(root_fd, output_name)
        identities = _verify_all_frozen_identities()
        snapshot_fd = _snapshot_iq(root_fd, iq_fd, expected_iq_sha256)
        config = _frozen_config(receiver_center_hz)
        worker_payload, worker_output_digest = _execute_worker(
            snapshot_fd, expected_iq_sha256, config
        )
        if _verify_all_frozen_identities() != identities:
            raise ValueError("legacy source, environment, worker, or tools changed during run")
        receipt = _seal_worker_payload(
            worker_payload,
            iq=Path(iq_label),
            iq_sha256=expected_iq_sha256,
            config=config,
            worker_output_digest=worker_output_digest,
        )
        _atomic_create_confined(
            root_fd,
            output_name,
            canonical_json_bytes(receipt.model_dump(mode="json")) + b"\n",
        )
        return receipt
    finally:
        if snapshot_fd is not None:
            os.close(snapshot_fd)
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
        os.close(root_fd)


def _frozen_config(receiver_center_hz: float) -> LegacyOracleConfigV1:
    values = {
        "schema_version": 1,
        "source_revision": LEGACY_REVISION,
        "source_tree": LEGACY_SOURCE_TREE,
        "executable_tree_digest": LEGACY_EXECUTABLE_TREE_DIGEST,
        "uv_lock_sha256": LEGACY_UV_LOCK_SHA256,
        "legacy_root": str(LEGACY_ROOT),
        "environment_manifest_digest": ENVIRONMENT_MANIFEST_DIGEST,
        "worker_path": str(WORKER_PATH),
        "worker_sha256": WORKER_SHA256,
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
    return LegacyOracleConfigV1.model_validate(
        {**values, "config_digest": canonical_digest(values)}
    )


def _execute_worker(iq_fd: int, iq_sha256: str, config: LegacyOracleConfigV1) -> tuple[object, str]:
    environment = {
        "HOME": "/nonexistent",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/bin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "XDG_CACHE_HOME": "/tmp/leo-legacy-oracle-cache-disabled",
    }
    result = subprocess.run(  # noqa: S603 - executable and worker are frozen identities
        [
            str(LEGACY_PYTHON),
            "-I",
            str(WORKER_PATH),
            "--iq-fd",
            str(iq_fd),
            "--iq-sha256",
            iq_sha256,
            "--config-json",
            json.dumps(config.model_dump(mode="json"), sort_keys=True),
        ],
        cwd=LEGACY_ROOT,
        env=environment,
        check=True,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        pass_fds=(iq_fd,),
        timeout=6 * 60 * 60,
    )
    if len(result.stdout) > _MAX_RECEIPT_BYTES:
        raise ValueError("legacy worker output exceeded its bound")
    return json.loads(result.stdout), _bytes_digest(result.stdout)


def _seal_worker_payload(
    payload: object,
    *,
    iq: Path,
    iq_sha256: str,
    config: LegacyOracleConfigV1,
    worker_output_digest: str,
) -> LegacyOracleReceiptV1:
    if not isinstance(payload, dict):
        raise ValueError("legacy worker output must be an object")
    if payload.get("config_digest") != config.config_digest:
        raise ValueError("legacy worker output has the wrong config digest")
    if payload.get("iq_sha256") != iq_sha256:
        raise ValueError("legacy worker output has the wrong IQ digest")
    environment = LegacyOracleEnvironmentV1.model_validate(payload.get("environment"))
    _safe_python_executable(Path(environment.python_executable))
    decisions = tuple(
        PilotWindowDecisionV1.model_validate(item) for item in payload.get("decisions", [])
    )
    values = {
        "schema_version": 1,
        "kind": "sealed_legacy_pilot_oracle",
        "status": "complete",
        "publication_method": _PUBLICATION_METHOD,
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
        "worker_output_digest": worker_output_digest,
    }
    return LegacyOracleReceiptV1.model_validate(
        {**values, "receipt_digest": canonical_digest(values)}
    )


def _verify_all_frozen_identities() -> tuple[str, str, str, str, str]:
    _require_write_seal(WORKER_PATH, "reviewed legacy worker", owner_too=True)
    _require_write_seal(ENVIRONMENT_MANIFEST, "reviewed environment manifest", owner_too=True)
    _require_write_seal(GIT_PATH, "reviewed /usr/bin/git", owner_too=False)
    if _file_digest(GIT_PATH) != GIT_SHA256:
        raise ValueError("reviewed /usr/bin/git identity changed")
    if _file_digest(WORKER_PATH) != WORKER_SHA256:
        raise ValueError("reviewed legacy worker identity changed")
    revision = _git("rev-parse", "HEAD")
    tree = _git("rev-parse", "HEAD^{tree}")
    if revision != LEGACY_REVISION or tree != LEGACY_SOURCE_TREE:
        raise ValueError("legacy checkout revision or source tree is not frozen v1")
    if _git("status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("legacy checkout must be clean outside ignored .venv evidence")
    _verify_read_only_tree(LEGACY_ROOT / "src")
    _verify_read_only_tree(LEGACY_ROOT / ".venv")
    _require_write_seal(LEGACY_ROOT / "pyproject.toml", "legacy project file", owner_too=True)
    _require_write_seal(LEGACY_ROOT / "uv.lock", "legacy lock file", owner_too=True)
    executable_digest = _verify_legacy_executable_tree()
    environment_digest = _verify_environment_manifest()
    return revision, tree, executable_digest, environment_digest, _file_digest(WORKER_PATH)


def _verify_legacy_executable_tree() -> str:
    entries: list[dict[str, str]] = []
    for line in _git("ls-tree", "-r", "--full-tree", "HEAD").splitlines():
        metadata, relative = line.split("\t", 1)
        mode, object_type, _object_id = metadata.split()
        executable = relative in {"pyproject.toml", "uv.lock"} or relative.startswith(
            "src/leo_tracker/"
        )
        if not executable:
            continue
        if object_type != "blob" or mode not in {"100644", "100755"}:
            raise ValueError(f"unsupported legacy executable tree entry: {relative}")
        path = _safe_input_file(LEGACY_ROOT / relative, "legacy executable source")
        executable_bit = bool(path.lstat().st_mode & stat.S_IXUSR)
        if executable_bit != (mode == "100755"):
            raise ValueError(f"legacy executable mode changed: {relative}")
        entries.append({"path": relative, "mode": mode, "sha256": _file_digest(path)})
    digest = canonical_digest(entries)
    if digest != LEGACY_EXECUTABLE_TREE_DIGEST or not entries:
        raise ValueError("legacy executable source/dependency content is not frozen v1")
    if _file_digest(LEGACY_ROOT / "uv.lock") != LEGACY_UV_LOCK_SHA256:
        raise ValueError("legacy dependency lock content is not frozen v1")
    return digest


def _verify_environment_manifest() -> str:
    manifest_path = _safe_input_file(ENVIRONMENT_MANIFEST, "environment manifest")
    if _file_digest(manifest_path) != ENVIRONMENT_MANIFEST_FILE_SHA256:
        raise ValueError("reviewed environment manifest file changed")
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    claimed = document.pop("manifest_digest", None)
    digest = canonical_digest(document)
    if claimed != ENVIRONMENT_MANIFEST_DIGEST or digest != ENVIRONMENT_MANIFEST_DIGEST:
        raise ValueError("environment manifest semantic digest changed")
    if (
        document.get("source_revision") != LEGACY_REVISION
        or document.get("fixed_legacy_root") != str(LEGACY_ROOT)
        or document.get("python_relative_path") != ".venv/bin/python"
    ):
        raise ValueError("environment manifest targets the wrong legacy environment")
    venv = LEGACY_ROOT / ".venv"
    expected_paths: set[str] = set()
    for entry in document.get("venv_entries", []):
        relative = _safe_manifest_relative(entry.get("path"))
        expected_paths.add(relative)
        _verify_manifest_entry(venv / relative, entry, relative_label=relative)
    actual_paths = _nofollow_inventory(venv)
    if actual_paths != expected_paths:
        raise ValueError("legacy .venv inventory differs from the frozen manifest")
    for entry in document.get("external_executable_files", []):
        path = Path(str(entry.get("path")))
        _verify_manifest_entry(path, entry, relative_label=str(path))
    _safe_python_executable(LEGACY_PYTHON)
    return digest


def _nofollow_inventory(root: Path) -> set[str]:
    inventory: set[str] = set()
    for directory, names, files in os.walk(root, followlinks=False):
        parent = Path(directory)
        for name in tuple(names):
            candidate = parent / name
            if stat.S_ISLNK(candidate.lstat().st_mode):
                inventory.add(str(candidate.relative_to(root)))
                names.remove(name)
        for name in files:
            inventory.add(str((parent / name).relative_to(root)))
    return inventory


def _verify_manifest_entry(path: Path, entry: object, *, relative_label: str) -> None:
    if not isinstance(entry, dict):
        raise ValueError("environment manifest entry must be an object")
    candidate = _lexical_absolute(path, "environment file")
    _reject_symlink_components(candidate.parent, "environment file parent")
    info = candidate.lstat()
    if entry.get("kind") == "symlink":
        if not stat.S_ISLNK(info.st_mode) or os.readlink(candidate) != entry.get("target"):
            raise ValueError(f"environment symlink changed: {relative_label}")
        return
    if entry.get("kind") != "file" or not stat.S_ISREG(info.st_mode):
        raise ValueError(f"environment file type changed: {relative_label}")
    if (
        info.st_size != entry.get("size")
        or stat.S_IMODE(info.st_mode) != entry.get("mode")
        or _file_digest(candidate) != entry.get("sha256")
    ):
        raise ValueError(f"environment file content changed: {relative_label}")


def _snapshot_iq(root_fd: int, source_fd: int, expected_digest: str) -> int:
    name = f".legacy-oracle-iq-snapshot-{os.getpid()}-{secrets.token_hex(8)}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    target_fd = os.open(name, flags, 0o400, dir_fd=root_fd)
    digest = hashlib.sha256()
    size = 0
    try:
        os.lseek(source_fd, 0, os.SEEK_SET)
        while block := os.read(source_fd, 1024 * 1024):
            digest.update(block)
            size += len(block)
            _write_all(target_fd, block)
        os.fsync(target_fd)
        if size != IQ_BYTES or f"sha256:{digest.hexdigest()}" != expected_digest:
            raise ValueError("IQ snapshot content does not match the reviewed digest/geometry")
    except BaseException:
        os.close(target_fd)
        os.unlink(name, dir_fd=root_fd)
        os.fsync(root_fd)
        raise
    os.close(target_fd)
    snapshot_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root_fd)
    os.unlink(name, dir_fd=root_fd)
    os.fsync(root_fd)
    return snapshot_fd


def _atomic_create_confined(root_fd: int, name: str, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    descriptor = os.open(name, flags, 0o440, dir_fd=root_fd)
    try:
        _write_all(descriptor, payload)
        os.fchmod(descriptor, 0o440)
        os.fsync(descriptor)
    except BaseException:
        os.close(descriptor)
        os.unlink(name, dir_fd=root_fd)
        os.fsync(root_fd)
        raise
    os.close(descriptor)
    os.fsync(root_fd)


def _acquire_qualification_lock(root_fd: int) -> int:
    name = ".legacy-oracle.lock"
    flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
    descriptor = os.open(name, flags, 0o600, dir_fd=root_fd)
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077:
        os.close(descriptor)
        raise ValueError("qualification lock has unsafe type, links, or permissions")
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(descriptor)
        raise RuntimeError("another legacy oracle qualification is active") from exc
    os.fsync(root_fd)
    return descriptor


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("short write while publishing oracle evidence")
        view = view[written:]


def _assert_output_absent(root_fd: int, name: str) -> None:
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root_fd)
    except FileNotFoundError:
        return
    else:
        os.close(descriptor)
        raise FileExistsError(f"oracle receipt already exists: {name}")


def _safe_input_file(path: Path, label: str) -> Path:
    candidate = _lexical_absolute(path, label)
    _reject_symlink_components(candidate, label)
    if not stat.S_ISREG(candidate.lstat().st_mode):
        raise ValueError(f"{label} must be a non-symlink regular file")
    return candidate


def _safe_directory(path: Path, label: str) -> Path:
    candidate = _lexical_absolute(path, label)
    _reject_symlink_components(candidate, label)
    if not stat.S_ISDIR(candidate.lstat().st_mode):
        raise ValueError(f"{label} must be a non-symlink directory")
    return candidate


def _safe_python_executable(path: Path) -> Path:
    candidate = _lexical_absolute(path, "legacy Python")
    if candidate != LEGACY_PYTHON:
        raise ValueError("legacy worker reported an unreviewed Python path")
    _reject_symlink_components(candidate.parent, "legacy Python parent")
    info = candidate.lstat()
    if not stat.S_ISLNK(info.st_mode):
        raise ValueError("frozen legacy Python must be the reviewed venv symlink")
    link = Path(os.readlink(candidate))
    target = link if link.is_absolute() else candidate.parent / link
    target = _lexical_absolute(target, "legacy Python target")
    target = _resolve_local_symlinks(target, "legacy Python target")
    target_info = target.lstat()
    if (
        not stat.S_ISREG(target_info.st_mode)
        or stat.S_IMODE(target_info.st_mode) & 0o022
        or not os.access(candidate, os.X_OK)
    ):
        raise ValueError("legacy Python target must be an executable regular file")
    return candidate


def _require_write_seal(path: Path, label: str, *, owner_too: bool) -> None:
    candidate = _lexical_absolute(path, label)
    _reject_symlink_components(candidate.parent, f"{label} parent")
    info = candidate.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"{label} must be a regular file")
    forbidden = 0o222 if owner_too else 0o022
    if stat.S_IMODE(info.st_mode) & forbidden:
        raise ValueError(f"{label} is not write-sealed")


def _verify_read_only_tree(root: Path) -> None:
    for directory, names, files in os.walk(root, followlinks=False):
        parent = Path(directory)
        if stat.S_IMODE(parent.lstat().st_mode) & 0o222:
            raise ValueError(f"reviewed tree directory is writable: {parent}")
        for name in names + files:
            candidate = parent / name
            info = candidate.lstat()
            if not stat.S_ISLNK(info.st_mode) and stat.S_IMODE(info.st_mode) & 0o222:
                raise ValueError(f"reviewed tree entry is writable: {candidate}")


def _resolve_local_symlinks(path: Path, label: str) -> Path:
    pending = list(path.parts[1:])
    current = Path(path.anchor)
    followed = 0
    while pending:
        current /= pending.pop(0)
        info = current.lstat()
        if not stat.S_ISLNK(info.st_mode):
            continue
        followed += 1
        if followed > 16:
            raise ValueError(f"{label} has too many symlink hops")
        link = Path(os.readlink(current))
        replacement = link if link.is_absolute() else current.parent / link
        replacement = _lexical_absolute(replacement, label)
        pending = list(replacement.parts[1:]) + pending
        current = Path(replacement.anchor)
    return current


def _lexical_absolute(path: Path, label: str) -> Path:
    candidate = Path(os.path.abspath(os.fspath(path)))
    if candidate == Path("/mnt/qnap01") or Path("/mnt/qnap01") in candidate.parents:
        raise ValueError(f"{label} cannot be beneath read-only /mnt/qnap01")
    return candidate


def _reject_symlink_components(path: Path, label: str) -> None:
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise ValueError(f"{label} cannot traverse a symlink: {current}")


def _safe_leaf_name(value: str) -> str:
    candidate = PurePath(value)
    if not value or candidate.is_absolute() or len(candidate.parts) != 1 or value in {".", ".."}:
        raise ValueError("receipt name must be one relative filename")
    return value


def _safe_manifest_relative(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("environment manifest path must be text")
    candidate = PurePath(value)
    unsafe = (
        candidate.is_absolute()
        or not candidate.parts
        or any(part in {".", ".."} for part in candidate.parts)
    )
    if unsafe:
        raise ValueError("environment manifest path escapes the venv")
    return value


def _open_directory(path: Path) -> int:
    return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)


def _git(*arguments: str) -> str:
    result = subprocess.run(  # noqa: S603 - absolute reviewed git identity
        [
            str(GIT_PATH),
            "-c",
            f"safe.directory={LEGACY_ROOT}",
            "-C",
            str(LEGACY_ROOT),
            *arguments,
        ],
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


def _bytes_digest(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _read_json_fd(descriptor: int, maximum_bytes: int) -> object:
    size = os.fstat(descriptor).st_size
    if size > maximum_bytes:
        raise ValueError("legacy oracle evidence exceeds its bounded size")
    os.lseek(descriptor, 0, os.SEEK_SET)
    payload = bytearray()
    while block := os.read(descriptor, min(1024 * 1024, maximum_bytes + 1 - len(payload))):
        payload.extend(block)
        if len(payload) > maximum_bytes:
            raise ValueError("legacy oracle evidence exceeds its bounded size")
    return json.loads(payload)


def _validate_digest(value: str, label: str) -> str:
    if len(value) != 71 or not value.startswith("sha256:"):
        raise ValueError(f"{label} must be a tagged SHA-256 digest")
    try:
        bytes.fromhex(value.removeprefix("sha256:"))
    except ValueError as exc:
        raise ValueError(f"{label} must be a tagged SHA-256 digest") from exc
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the frozen qualification-only oracle")
    parser.add_argument("--iq-path", type=Path, required=True)
    parser.add_argument("--iq-sha256", required=True)
    parser.add_argument("--receiver-center-hz", type=float, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--receipt-name", required=True)
    arguments = parser.parse_args(argv)
    receipt = run_legacy_oracle(
        iq_path=arguments.iq_path,
        expected_iq_sha256=arguments.iq_sha256,
        receiver_center_hz=arguments.receiver_center_hz,
        evidence_root=arguments.evidence_root,
        receipt_name=arguments.receipt_name,
    )
    print(receipt.receipt_digest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
