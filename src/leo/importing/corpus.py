"""Fail-closed, read/copy-only TEST-corpus materialization.

Sources are opened only in binary read mode. Publication may create and clean
up local staging paths below the configured corpus root, but there is no source
mutation operation in this component's vocabulary or public API.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal

CORPUS_SCHEMA = "org.leo.test-corpus/v1"
CORPUS_SCHEMA_V2 = "org.leo.test-corpus/v2"
FIXTURE_SCHEMA = "org.leo.test-fixture/v1"
HOLD_SCHEMA = "org.leo.test-corpus-hold/v1"
FIXTURE_MANIFEST_NAME = "fixture-manifest.json"
HOLD_RECEIPT_NAME = "retention-hold.json"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_FORBIDDEN_MUTATION_TOKENS = frozenset({"delete", "move", "rename", "unlink", "remove"})
_READ_ONLY_SOURCE_ROOT = Path("/mnt/qnap01")
_TOP_LEVEL_KEYS = frozenset({"schema", "corpus_id", "policy", "fixtures"})
_POLICY_KEYS = frozenset(
    {
        "source_access",
        "source_type",
        "tags",
        "retention_hold",
        "default_local_root",
        "license",
        "redistribution",
    }
)
_FIXTURE_KEYS = frozenset({"fixture_id", "requirement", "role", "metadata", "artifacts"})
_ARTIFACT_KEYS = frozenset(
    {
        "artifact_id",
        "kind",
        "source_absolute_path",
        "source_byte_count",
        "source_sha256",
        "selected_byte_offset",
        "selected_byte_count",
        "selected_sha256",
        "target_relative_path",
    }
)
_UNAVAILABLE_AVAILABILITY_KEYS = frozenset(
    {
        "source_present",
        "frozen_calibration_present",
        "execution_eligible",
        "execution_status",
        "result_status",
        "parity_status",
        "blocker",
        "recovery_audit",
        "decision_adr",
    }
)
_UNAVAILABLE_TRUTH_KEYS = frozenset(
    {
        "tier",
        "label",
        "target_present",
        "calibrated_detection",
        "specificity_claimed",
        "detection_claimed",
        "parity_claimed",
        "payload_decoded",
        "attribution_claimed",
    }
)


class CorpusImportError(RuntimeError):
    """Base error for corpus validation or materialization failures."""


class ManifestValidationError(CorpusImportError):
    """The import manifest is not a closed, read-only corpus declaration."""


class SourceVerificationError(CorpusImportError):
    """A source object or selected byte range did not match its declaration."""


class TargetBoundaryError(CorpusImportError):
    """A requested local target escapes the configured corpus root."""


class ExistingFixtureConflictError(CorpusImportError):
    """An existing fixture is not byte-identical to the requested fixture."""


@dataclass(frozen=True, slots=True)
class ImportArtifact:
    artifact_id: str
    kind: str
    source_path: Path
    source_byte_count: int
    source_sha256: str
    selected_byte_offset: int
    selected_byte_count: int
    selected_sha256: str
    target_relative_path: PurePosixPath


@dataclass(frozen=True, slots=True)
class FixtureSpec:
    fixture_id: str
    requirement: Literal["REQUIRED", "PLANNED", "UNAVAILABLE_HISTORICAL_EVIDENCE"]
    role: str
    metadata: Mapping[str, Any]
    artifacts: tuple[ImportArtifact, ...]


@dataclass(frozen=True, slots=True)
class CorpusManifest:
    corpus_id: str
    default_local_root: Path
    fixtures: tuple[FixtureSpec, ...]

    def required_fixtures(self) -> tuple[FixtureSpec, ...]:
        return tuple(item for item in self.fixtures if item.requirement == "REQUIRED")


@dataclass(frozen=True, slots=True)
class MaterializationResult:
    fixture_id: str
    directory: Path
    status: Literal["created", "already_present"]


@dataclass(frozen=True, slots=True)
class _SourceSnapshot:
    device: int
    inode: int
    mode: int
    size: int
    mtime_ns: int
    ctime_ns: int

    @classmethod
    def from_stat(cls, value: os.stat_result) -> _SourceSnapshot:
        return cls(
            value.st_dev,
            value.st_ino,
            value.st_mode,
            value.st_size,
            value.st_mtime_ns,
            value.st_ctime_ns,
        )


def load_corpus_manifest(path: Path) -> CorpusManifest:
    """Load a closed manifest whose only supported source access is read-only."""

    try:
        document = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestValidationError(f"cannot read corpus manifest {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise ManifestValidationError("corpus manifest must be a JSON object")
    _reject_mutation_concepts(document)
    _require_exact_keys(document, _TOP_LEVEL_KEYS, "corpus manifest")
    schema = document["schema"]
    if schema not in {CORPUS_SCHEMA, CORPUS_SCHEMA_V2}:
        raise ManifestValidationError(f"unsupported corpus schema: {document['schema']!r}")
    corpus_id = _safe_identifier(document["corpus_id"], "corpus_id")
    policy = _mapping(document["policy"], "policy")
    _require_exact_keys(policy, _POLICY_KEYS, "policy")
    if policy["source_access"] != "read_only":
        raise ManifestValidationError("policy.source_access must be 'read_only'")
    if policy["source_type"] != "TEST":
        raise ManifestValidationError("policy.source_type must be 'TEST'")
    if policy["tags"] != ["TEST"]:
        raise ManifestValidationError("policy.tags must be exactly ['TEST']")
    if policy["retention_hold"] != "indefinite":
        raise ManifestValidationError("policy.retention_hold must be 'indefinite'")
    if policy["license"] != "NOASSERTION":
        raise ManifestValidationError("policy.license must remain 'NOASSERTION'")
    if policy["redistribution"] != "not-assessed":
        raise ManifestValidationError("policy.redistribution must be 'not-assessed'")
    default_root = Path(_nonempty_string(policy["default_local_root"], "default_local_root"))
    if not default_root.is_absolute():
        raise ManifestValidationError("policy.default_local_root must be absolute")

    raw_fixtures = document["fixtures"]
    if not isinstance(raw_fixtures, list) or not raw_fixtures:
        raise ManifestValidationError("fixtures must be a non-empty array")
    fixtures = tuple(
        _parse_fixture(item, index, schema=schema) for index, item in enumerate(raw_fixtures)
    )
    fixture_ids = [item.fixture_id for item in fixtures]
    if len(fixture_ids) != len(set(fixture_ids)):
        raise ManifestValidationError("fixture_id values must be unique")
    if not any(item.requirement == "REQUIRED" for item in fixtures):
        raise ManifestValidationError("corpus must declare at least one REQUIRED fixture")
    return CorpusManifest(corpus_id, default_root, fixtures)


class FixtureImporter:
    """Materialize verified slices below one explicitly configured local root."""

    def __init__(self, local_corpus_root: Path) -> None:
        if not local_corpus_root.is_absolute():
            raise TargetBoundaryError("local corpus root must be absolute")
        self._root = local_corpus_root.resolve(strict=False)
        if self._root == _READ_ONLY_SOURCE_ROOT or _READ_ONLY_SOURCE_ROOT in self._root.parents:
            raise TargetBoundaryError("local corpus root cannot be beneath read-only /mnt/qnap01")

    @property
    def local_corpus_root(self) -> Path:
        return self._root

    def materialize_required(self, manifest: CorpusManifest) -> tuple[MaterializationResult, ...]:
        """Materialize every REQUIRED fixture and fail on the first mismatch."""

        return tuple(self.materialize(item) for item in manifest.required_fixtures())

    def materialize(self, fixture: FixtureSpec) -> MaterializationResult:
        """Create one fixture, or verify and reuse an identical existing fixture."""

        if fixture.requirement == "UNAVAILABLE_HISTORICAL_EVIDENCE":
            raise ManifestValidationError(
                f"fixture {fixture.fixture_id} is {fixture.requirement} and is not executable"
            )
        self._prepare_root()
        final_directory = self._fixture_directory(fixture.fixture_id)
        expected_manifest = _fixture_manifest_document(fixture)
        expected_hold = _hold_receipt_document(fixture)
        if final_directory.exists() or final_directory.is_symlink():
            self._verify_existing(final_directory, fixture, expected_manifest, expected_hold)
            return MaterializationResult(fixture.fixture_id, final_directory, "already_present")

        stage = self._root / f".{fixture.fixture_id}.{uuid.uuid4().hex}.partial"
        self._assert_below_root(stage)
        stage.mkdir(mode=0o750)
        try:
            for artifact in fixture.artifacts:
                self._copy_verified_slice(artifact, stage)
            _write_protected_json(stage / FIXTURE_MANIFEST_NAME, expected_manifest)
            _write_protected_json(stage / HOLD_RECEIPT_NAME, expected_hold)
            _fsync_directory(stage)
            try:
                os.rename(stage, final_directory)
            except FileExistsError:
                self._verify_existing(final_directory, fixture, expected_manifest, expected_hold)
                return MaterializationResult(fixture.fixture_id, final_directory, "already_present")
            _fsync_directory(self._root)
        except Exception:
            if stage.exists():
                shutil.rmtree(stage)
            raise
        return MaterializationResult(fixture.fixture_id, final_directory, "created")

    def _prepare_root(self) -> None:
        self._root.mkdir(mode=0o750, parents=True, exist_ok=True)
        if not self._root.is_dir() or self._root.is_symlink():
            raise TargetBoundaryError("local corpus root must be a real directory")
        if self._root.resolve(strict=True) != self._root:
            raise TargetBoundaryError("local corpus root resolution changed")

    def _fixture_directory(self, fixture_id: str) -> Path:
        _safe_identifier(fixture_id, "fixture_id")
        target = self._root / fixture_id
        self._assert_below_root(target)
        return target

    def _assert_below_root(self, target: Path) -> None:
        try:
            target.resolve(strict=False).relative_to(self._root)
        except ValueError as exc:
            raise TargetBoundaryError(
                f"target is outside configured local corpus root: {target}"
            ) from exc

    def _copy_verified_slice(self, artifact: ImportArtifact, stage: Path) -> None:
        source = artifact.source_path
        if not source.is_absolute():
            raise ManifestValidationError(f"source path must be absolute: {source}")
        try:
            source_resolved = source.resolve(strict=True)
        except OSError as exc:
            raise SourceVerificationError(f"source is unavailable: {source}") from exc
        try:
            source_resolved.relative_to(self._root)
        except ValueError:
            pass
        else:
            raise TargetBoundaryError("a corpus target cannot be used as an import source")

        destination = stage.joinpath(*artifact.target_relative_path.parts)
        self._assert_below_root(destination)
        destination.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
        with source.open("rb") as stream:
            before = _SourceSnapshot.from_stat(os.fstat(stream.fileno()))
            if not stat.S_ISREG(before.mode):
                raise SourceVerificationError(f"source is not a regular file: {source}")
            if before.size != artifact.source_byte_count:
                raise SourceVerificationError(
                    f"source size mismatch for {source}: "
                    f"expected {artifact.source_byte_count}, got {before.size}"
                )
            source_digest = _hash_stream(stream)
            if source_digest != artifact.source_sha256:
                raise SourceVerificationError(
                    f"source SHA-256 mismatch for {source}: "
                    f"expected {artifact.source_sha256}, got {source_digest}"
                )
            stream.seek(artifact.selected_byte_offset)
            selected_digest = hashlib.sha256()
            remaining = artifact.selected_byte_count
            with destination.open("xb") as output:
                while remaining:
                    block = stream.read(min(8 * 1024 * 1024, remaining))
                    if not block:
                        raise SourceVerificationError(
                            f"source ended inside selected range: {source}"
                        )
                    output.write(block)
                    selected_digest.update(block)
                    remaining -= len(block)
                output.flush()
                os.fsync(output.fileno())
            after = _SourceSnapshot.from_stat(os.fstat(stream.fileno()))
        if after != before:
            raise SourceVerificationError(f"source changed while importing: {source}")
        copied_digest = selected_digest.hexdigest()
        if copied_digest != artifact.selected_sha256:
            raise SourceVerificationError(
                f"selected SHA-256 mismatch for {source}: "
                f"expected {artifact.selected_sha256}, got {copied_digest}"
            )
        _verify_local_file(destination, artifact.selected_byte_count, artifact.selected_sha256)
        destination.chmod(0o440)

    def _verify_existing(
        self,
        directory: Path,
        fixture: FixtureSpec,
        expected_manifest: Mapping[str, Any],
        expected_hold: Mapping[str, Any],
    ) -> None:
        self._assert_below_root(directory)
        if directory.is_symlink() or not directory.is_dir():
            raise ExistingFixtureConflictError(
                f"fixture target is not a real directory: {directory}"
            )
        expected_documents = (
            (directory / FIXTURE_MANIFEST_NAME, expected_manifest),
            (directory / HOLD_RECEIPT_NAME, expected_hold),
        )
        for path, document in expected_documents:
            self._assert_below_root(path)
            if not path.is_file() or path.is_symlink():
                raise ExistingFixtureConflictError(
                    f"existing fixture is missing protected document: {path}"
                )
            if path.read_bytes() != _encode_json(document):
                raise ExistingFixtureConflictError(f"existing protected document differs: {path}")
        for artifact in fixture.artifacts:
            path = directory.joinpath(*artifact.target_relative_path.parts)
            self._assert_below_root(path)
            if path.is_symlink():
                raise ExistingFixtureConflictError(f"existing fixture payload is a symlink: {path}")
            try:
                _verify_local_file(path, artifact.selected_byte_count, artifact.selected_sha256)
            except SourceVerificationError as exc:
                raise ExistingFixtureConflictError(str(exc)) from exc


def _parse_fixture(value: object, index: int, *, schema: object) -> FixtureSpec:
    document = _mapping(value, f"fixtures[{index}]")
    _require_exact_keys(document, _FIXTURE_KEYS, f"fixtures[{index}]")
    fixture_id = _safe_identifier(document["fixture_id"], f"fixtures[{index}].fixture_id")
    requirement = document["requirement"]
    allowed_requirements = {"REQUIRED", "PLANNED"}
    if schema == CORPUS_SCHEMA_V2:
        allowed_requirements.add("UNAVAILABLE_HISTORICAL_EVIDENCE")
    if requirement not in allowed_requirements:
        allowed = ", ".join(sorted(allowed_requirements))
        raise ManifestValidationError(f"fixtures[{index}].requirement must be one of {allowed}")
    role = _nonempty_string(document["role"], f"fixtures[{index}].role")
    metadata = _mapping(document["metadata"], f"fixtures[{index}].metadata")
    if requirement == "UNAVAILABLE_HISTORICAL_EVIDENCE":
        _validate_unavailable_historical_evidence(metadata, index)
    raw_artifacts = document["artifacts"]
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        raise ManifestValidationError(f"fixtures[{index}].artifacts must be non-empty")
    artifacts = tuple(
        _parse_artifact(item, index, artifact_index)
        for artifact_index, item in enumerate(raw_artifacts)
    )
    artifact_ids = [item.artifact_id for item in artifacts]
    targets = [item.target_relative_path for item in artifacts]
    if len(artifact_ids) != len(set(artifact_ids)):
        raise ManifestValidationError(f"fixtures[{index}] artifact_id values must be unique")
    if len(targets) != len(set(targets)):
        raise ManifestValidationError(
            f"fixtures[{index}] target_relative_path values must be unique"
        )
    return FixtureSpec(fixture_id, requirement, role, dict(metadata), artifacts)


def _validate_unavailable_historical_evidence(
    metadata: Mapping[str, Any], fixture_index: int
) -> None:
    """Make an unavailable historical declaration impossible to treat as a result."""

    location = f"fixtures[{fixture_index}].metadata"
    availability = _mapping(metadata.get("availability"), f"{location}.availability")
    _require_exact_keys(
        availability,
        _UNAVAILABLE_AVAILABILITY_KEYS,
        f"{location}.availability",
    )
    required = {
        "source_present": False,
        "frozen_calibration_present": False,
        "execution_eligible": False,
        "execution_status": "not_executed",
        "result_status": "not_available",
        "parity_status": "not_executable",
    }
    for key, expected in required.items():
        if availability.get(key) != expected:
            raise ManifestValidationError(
                f"{location}.availability.{key} must be {expected!r} for unavailable evidence"
            )
    for key in ("blocker", "recovery_audit", "decision_adr"):
        _nonempty_string(availability.get(key), f"{location}.availability.{key}")
    truth = _mapping(metadata.get("truth"), f"{location}.truth")
    _require_exact_keys(truth, _UNAVAILABLE_TRUTH_KEYS, f"{location}.truth")
    forbidden_claims = {
        "target_present": None,
        "calibrated_detection": False,
        "specificity_claimed": False,
        "detection_claimed": False,
        "parity_claimed": False,
        "payload_decoded": False,
        "attribution_claimed": False,
    }
    for key, expected in forbidden_claims.items():
        if key not in truth or truth[key] != expected:
            raise ManifestValidationError(
                f"{location}.truth.{key} must be {expected!r} for unavailable evidence"
            )


def _parse_artifact(value: object, fixture_index: int, artifact_index: int) -> ImportArtifact:
    location = f"fixtures[{fixture_index}].artifacts[{artifact_index}]"
    document = _mapping(value, location)
    _require_exact_keys(document, _ARTIFACT_KEYS, location)
    artifact_id = _safe_identifier(document["artifact_id"], f"{location}.artifact_id")
    kind = _safe_identifier(document["kind"], f"{location}.kind")
    source_path = Path(_nonempty_string(document["source_absolute_path"], location))
    if not source_path.is_absolute():
        raise ManifestValidationError(f"{location}.source_absolute_path must be absolute")
    source_byte_count = _nonnegative_int(
        document["source_byte_count"], f"{location}.source_byte_count"
    )
    source_sha256 = _digest(document["source_sha256"], f"{location}.source_sha256")
    selected_offset = _nonnegative_int(
        document["selected_byte_offset"], f"{location}.selected_byte_offset"
    )
    selected_count = _positive_int(
        document["selected_byte_count"], f"{location}.selected_byte_count"
    )
    selected_sha256 = _digest(document["selected_sha256"], f"{location}.selected_sha256")
    if selected_offset + selected_count > source_byte_count:
        raise ManifestValidationError(f"{location} selected byte range exceeds source size")
    target = _target_path(document["target_relative_path"], location)
    return ImportArtifact(
        artifact_id,
        kind,
        source_path,
        source_byte_count,
        source_sha256,
        selected_offset,
        selected_count,
        selected_sha256,
        target,
    )


def _fixture_manifest_document(fixture: FixtureSpec) -> dict[str, Any]:
    return {
        "schema": FIXTURE_SCHEMA,
        "fixture_id": fixture.fixture_id,
        "requirement": fixture.requirement,
        "role": fixture.role,
        "source_type": "TEST",
        "tags": ["TEST"],
        "retention": {
            "hold": "indefinite",
            "protected": True,
            "reason": "TEST-corpus scientific regression fixture",
        },
        "metadata": fixture.metadata,
        "artifacts": [
            {
                "artifact_id": item.artifact_id,
                "kind": item.kind,
                "relative_path": item.target_relative_path.as_posix(),
                "byte_count": item.selected_byte_count,
                "sha256": item.selected_sha256,
                "source": {
                    "absolute_path": str(item.source_path),
                    "byte_count": item.source_byte_count,
                    "sha256": item.source_sha256,
                    "selected_byte_offset": item.selected_byte_offset,
                    "selected_byte_count": item.selected_byte_count,
                    "selected_sha256": item.selected_sha256,
                    "access": "read_only",
                },
            }
            for item in fixture.artifacts
        ],
    }


def _hold_receipt_document(fixture: FixtureSpec) -> dict[str, Any]:
    return {
        "schema": HOLD_SCHEMA,
        "fixture_id": fixture.fixture_id,
        "source_type": "TEST",
        "tags": ["TEST"],
        "hold": "indefinite",
        "protected": True,
        "reason": "Required TEST-corpus evidence is retention-ineligible",
    }


def _reject_mutation_concepts(value: object, location: str = "manifest") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ManifestValidationError(f"{location} contains a non-string key")
            tokens = set(re.split(r"[^a-z0-9]+", key.lower()))
            if tokens & _FORBIDDEN_MUTATION_TOKENS:
                raise ManifestValidationError(
                    f"source mutation concept is forbidden at {location}.{key}"
                )
            _reject_mutation_concepts(item, f"{location}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_mutation_concepts(item, f"{location}[{index}]")
    elif isinstance(value, str):
        tokens = set(re.split(r"[^a-z0-9]+", value.lower()))
        if tokens & _FORBIDDEN_MUTATION_TOKENS:
            raise ManifestValidationError(f"source mutation concept is forbidden at {location}")


def _require_exact_keys(
    value: Mapping[str, object], allowed: frozenset[str], location: str
) -> None:
    keys = set(value)
    if keys != allowed:
        missing = sorted(allowed - keys)
        extra = sorted(keys - allowed)
        raise ManifestValidationError(f"{location} keys differ; missing={missing}, extra={extra}")


def _mapping(value: object, location: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ManifestValidationError(f"{location} must be an object")
    return value


def _nonempty_string(value: object, location: str) -> str:
    if not isinstance(value, str) or not value:
        raise ManifestValidationError(f"{location} must be a non-empty string")
    return value


def _safe_identifier(value: object, location: str) -> str:
    text = _nonempty_string(value, location)
    if _SAFE_ID.fullmatch(text) is None:
        raise ManifestValidationError(f"{location} is not a safe identifier")
    return text


def _digest(value: object, location: str) -> str:
    text = _nonempty_string(value, location)
    if _SHA256.fullmatch(text) is None:
        raise ManifestValidationError(f"{location} must be a lowercase SHA-256")
    return text


def _nonnegative_int(value: object, location: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ManifestValidationError(f"{location} must be a non-negative integer")
    return value


def _positive_int(value: object, location: str) -> int:
    result = _nonnegative_int(value, location)
    if result == 0:
        raise ManifestValidationError(f"{location} must be positive")
    return result


def _target_path(value: object, location: str) -> PurePosixPath:
    text = _nonempty_string(value, f"{location}.target_relative_path")
    target = PurePosixPath(text)
    if target.is_absolute() or not target.parts:
        raise TargetBoundaryError(f"{location}.target_relative_path must be relative")
    if any(part in {"", ".", ".."} for part in target.parts):
        raise TargetBoundaryError(f"{location}.target_relative_path contains an unsafe segment")
    if target.name in {FIXTURE_MANIFEST_NAME, HOLD_RECEIPT_NAME}:
        raise TargetBoundaryError(
            f"{location}.target_relative_path collides with a protected document"
        )
    return target


def _hash_stream(stream: Any) -> str:
    stream.seek(0)
    digest = hashlib.sha256()
    while block := stream.read(8 * 1024 * 1024):
        digest.update(block)
    return digest.hexdigest()


def _verify_local_file(path: Path, byte_count: int, sha256: str) -> None:
    if not path.is_file():
        raise SourceVerificationError(f"local copied slice is absent: {path}")
    if path.stat().st_size != byte_count:
        raise SourceVerificationError(f"local copied slice size mismatch: {path}")
    with path.open("rb") as stream:
        digest = _hash_stream(stream)
    if digest != sha256:
        raise SourceVerificationError(f"local copied slice SHA-256 mismatch: {path}")


def _encode_json(document: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _write_protected_json(path: Path, document: Mapping[str, Any]) -> None:
    with path.open("xb") as stream:
        stream.write(_encode_json(document))
        stream.flush()
        os.fsync(stream.fileno())
    path.chmod(0o440)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
