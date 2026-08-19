"""Fail-closed preflight for protected local detector fixtures."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any

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


class FixturePreflightStatus(StrEnum):
    READY = "ready"
    PLANNED = "planned"
    UNAVAILABLE_HISTORICAL_EVIDENCE = "unavailable_historical_evidence"
    MISSING = "missing"
    CORRUPT = "corrupt"


class RequiredFixtureError(RuntimeError):
    """One or more REQUIRED fixtures are missing or corrupt."""


@dataclass(frozen=True, slots=True)
class FixturePreflight:
    fixture_id: str
    requirement: str
    status: FixturePreflightStatus
    reason: str
    directory: Path


@dataclass(frozen=True, slots=True)
class CorpusPreflightReport:
    checks: tuple[FixturePreflight, ...]

    def by_id(self, fixture_id: str) -> FixturePreflight:
        try:
            return next(item for item in self.checks if item.fixture_id == fixture_id)
        except StopIteration as exc:
            raise KeyError(fixture_id) from exc

    def require_ready(self) -> None:
        failures = tuple(
            item
            for item in self.checks
            if item.requirement == "REQUIRED" and item.status is not FixturePreflightStatus.READY
        )
        if failures:
            summary = "; ".join(
                f"{item.fixture_id}: {item.status.value} ({item.reason})" for item in failures
            )
            raise RequiredFixtureError(f"REQUIRED corpus preflight failed: {summary}")


def inspect_corpus(
    manifest_path: Path,
    *,
    local_corpus_root: Path | None = None,
) -> CorpusPreflightReport:
    """Inspect every declaration, including non-executable historical evidence."""

    document = _read_object(manifest_path)
    schema = document.get("schema")
    if schema not in {
        "org.leo.test-corpus/v1",
        "org.leo.test-corpus/v2",
    }:
        raise ValueError("unsupported corpus manifest schema")
    policy = _object(document.get("policy"), "policy")
    root = local_corpus_root or Path(str(policy.get("default_local_root")))
    if not root.is_absolute():
        raise ValueError("local corpus root must be absolute")
    root = root.resolve(strict=False)
    fixtures = document.get("fixtures")
    if not isinstance(fixtures, list):
        raise ValueError("corpus fixtures must be an array")
    checks = tuple(
        _inspect_fixture(_object(item, "fixture"), root, schema=str(schema)) for item in fixtures
    )
    return CorpusPreflightReport(checks)


def preflight_corpus(
    manifest_path: Path,
    *,
    local_corpus_root: Path | None = None,
) -> CorpusPreflightReport:
    """Inspect the corpus and raise if any REQUIRED declaration is not ready."""

    report = inspect_corpus(manifest_path, local_corpus_root=local_corpus_root)
    report.require_ready()
    return report


def _inspect_fixture(document: dict[str, Any], root: Path, *, schema: str) -> FixturePreflight:
    fixture_id = str(document.get("fixture_id", ""))
    requirement = str(document.get("requirement", ""))
    fixture_name = PurePosixPath(fixture_id)
    if (
        not fixture_id
        or fixture_name.is_absolute()
        or len(fixture_name.parts) != 1
        or fixture_name.parts[0] in {"", ".", ".."}
    ):
        raise ValueError("fixture_id must be one safe path component")
    directory = root / fixture_id
    if requirement == "PLANNED":
        metadata = _object(document.get("metadata"), f"{fixture_id}.metadata")
        availability = metadata.get("availability")
        blocker = (
            str(availability.get("blocker", "fixture is not promoted to REQUIRED"))
            if isinstance(availability, dict)
            else "fixture is not promoted to REQUIRED"
        )
        return FixturePreflight(
            fixture_id,
            requirement,
            FixturePreflightStatus.PLANNED,
            blocker,
            directory,
        )
    if requirement == "UNAVAILABLE_HISTORICAL_EVIDENCE":
        if schema != "org.leo.test-corpus/v2":
            raise ValueError("unavailable historical evidence requires corpus schema v2")
        metadata = _object(document.get("metadata"), f"{fixture_id}.metadata")
        availability = _object(metadata.get("availability"), f"{fixture_id}.metadata.availability")
        if set(availability) != _UNAVAILABLE_AVAILABILITY_KEYS:
            raise ValueError(
                f"unavailable historical fixture {fixture_id} has unexpected availability fields"
            )
        if (
            availability.get("source_present") is not False
            or availability.get("frozen_calibration_present") is not False
            or availability.get("execution_eligible") is not False
            or availability.get("execution_status") != "not_executed"
            or availability.get("result_status") != "not_available"
            or availability.get("parity_status") != "not_executable"
        ):
            raise ValueError(
                f"unavailable historical fixture {fixture_id} has executable/present claims"
            )
        truth = _object(metadata.get("truth"), f"{fixture_id}.metadata.truth")
        if set(truth) != _UNAVAILABLE_TRUTH_KEYS:
            raise ValueError(
                f"unavailable historical fixture {fixture_id} has unexpected truth fields"
            )
        forbidden_claims = {
            "target_present": None,
            "calibrated_detection": False,
            "specificity_claimed": False,
            "detection_claimed": False,
            "parity_claimed": False,
            "payload_decoded": False,
            "attribution_claimed": False,
        }
        if any(
            key not in truth or truth[key] != expected for key, expected in forbidden_claims.items()
        ):
            raise ValueError(
                f"unavailable historical fixture {fixture_id} has scientific-result claims"
            )
        for key in ("blocker", "recovery_audit", "decision_adr"):
            if not isinstance(availability.get(key), str) or not availability[key].strip():
                raise ValueError(f"unavailable historical fixture {fixture_id} lacks {key} lineage")
        blocker = str(availability.get("blocker", "historical evidence is unavailable"))
        return FixturePreflight(
            fixture_id,
            requirement,
            FixturePreflightStatus.UNAVAILABLE_HISTORICAL_EVIDENCE,
            blocker,
            directory,
        )
    if requirement != "REQUIRED":
        raise ValueError(f"unknown fixture requirement for {fixture_id}")
    if not directory.is_dir() or directory.is_symlink():
        return FixturePreflight(
            fixture_id,
            requirement,
            FixturePreflightStatus.MISSING,
            "protected local fixture directory is absent",
            directory,
        )
    try:
        local_manifest = _read_object(directory / "fixture-manifest.json")
        hold = _read_object(directory / "retention-hold.json")
        if local_manifest.get("fixture_id") != fixture_id:
            raise ValueError("local fixture manifest identifies another fixture")
        if local_manifest.get("source_type") != "TEST" or "TEST" not in local_manifest.get(
            "tags", []
        ):
            raise ValueError("fixture is not explicitly tagged TEST")
        retention = _object(local_manifest.get("retention"), "retention")
        if retention.get("protected") is not True or retention.get("hold") != "indefinite":
            raise ValueError("fixture does not carry an indefinite protection hold")
        if hold.get("fixture_id") != fixture_id or hold.get("protected") is not True:
            raise ValueError("retention hold receipt is invalid")
        artifacts = document.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise ValueError("fixture declares no artifacts")
        for raw_artifact in artifacts:
            artifact = _object(raw_artifact, f"{fixture_id}.artifact")
            relative = PurePosixPath(str(artifact.get("target_relative_path", "")))
            if (
                relative.is_absolute()
                or not relative.parts
                or any(part in {"", ".", ".."} for part in relative.parts)
            ):
                raise ValueError("artifact relative path is unsafe")
            path = directory.joinpath(*relative.parts)
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"artifact is absent or a symlink: {relative}")
            expected_bytes = int(artifact["selected_byte_count"])
            if path.stat().st_size != expected_bytes:
                raise ValueError(f"artifact byte count changed: {relative}")
            if _sha256(path) != artifact["selected_sha256"]:
                raise ValueError(f"artifact digest changed: {relative}")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return FixturePreflight(
            fixture_id,
            requirement,
            FixturePreflightStatus.CORRUPT,
            str(exc),
            directory,
        )
    return FixturePreflight(
        fixture_id,
        requirement,
        FixturePreflightStatus.READY,
        "all protected local artifacts match the committed declaration",
        directory,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _read_object(path: Path) -> dict[str, Any]:
    return _object(json.loads(path.read_bytes()), str(path))


def _object(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value
