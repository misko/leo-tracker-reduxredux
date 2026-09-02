"""Fail-closed protected-corpus and browser release qualification.

The command intentionally orchestrates the same scientific and browser tests as
CI.  Test-owned PostgreSQL schemas and temporary RecordingStore roots keep it
away from the production catalog and recordings.  Every invocation gets a new,
write-once evidence directory containing the exact definition, command logs,
test results, and a digest inventory.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from leo.contracts.digests import canonical_json_bytes
from leo.qualification.release_contract import (
    MAXIMUM_JUNIT_BYTES,
    RELEASE_QUALIFICATION_V3_ALL_COMMAND_NAMES,
    RELEASE_QUALIFICATION_V3_COMMAND_NAMES,
    RELEASE_QUALIFICATION_V3_JUNIT_PATHS,
    RELEASE_QUALIFICATION_V3_LANE_INPUT_PATHS,
    RELEASE_QUALIFICATION_V3_RESULT_PATHS,
    RELEASE_QUALIFICATION_V3_SCHEMA,
    release_qualification_v3_command_documents,
    release_qualification_v3_definition,
    release_qualification_v3_inventory_digest,
    release_qualification_v3_lane_input_digests,
    release_qualification_v3_runtime_digest,
    summarize_pytest_junit_v1,
    validate_pytest_junit_summary_v1,
    validate_reusable_release_qualification_v3_lane,
)

_QNAP_ROOT = Path("/mnt/qnap01")
_DEPLOYMENT_ROOT = Path("/opt/leo-tracker")
_PRODUCTION_DATABASE = "leo_tracker"
_SCHEMA = RELEASE_QUALIFICATION_V3_SCHEMA
_DATABASE_COMMAND_NAMES = frozenset(
    {
        "current-native-postgresql",
        "historical-recording-postgresql",
        "production-chromium-e2e",
    }
)
_MAXIMUM_RESOURCE_UNITS = 4
_REUSE_MAXIMUM_AGE_SECONDS = 3 * 24 * 60 * 60
_REUSE_MAXIMUM_CANDIDATES = 64
_IGNORED_INPUT_DIRECTORIES = frozenset(
    {"__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
)
_SOURCE_MARKER = ".leo-release-source.json"
_SOURCE_MARKER_SCHEMA = "org.leo.release-source/v1"
_QUALIFICATION_DATABASE_LOCK = Path("/var/lib/leo/.cache/qualification-database.lock")
_CHILD_ENVIRONMENT_ALLOWLIST = frozenset(
    {
        "LANG",
        "LC_ALL",
        "PATH",
        "PLAYWRIGHT_BROWSERS_PATH",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "TZ",
    }
)


@dataclass(frozen=True, slots=True)
class QualificationCommand:
    name: str
    argv: tuple[str, ...]
    cwd: Path
    log_relative_path: str
    resource_units: int
    database_access: bool
    depends_on: tuple[str, ...]
    release_blocking: bool
    command_sha256: str
    reuse_key_sha256: str


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    revision: str
    tree: str
    kind: str


def run_release_qualification(
    *,
    project_root: Path,
    database_url: str,
    corpus_root: Path,
    native_corpus_root: Path | None = None,
    evidence_root: Path,
    run_id: str | None = None,
    maximum_resource_units: int | None = None,
    include_historical: bool = False,
) -> Path:
    """Run bounded current-format gates and seal a deterministic V3 receipt."""

    _reject_qnap_argument(project_root, "project root")
    _reject_qnap_argument(corpus_root, "protected corpus root")
    _reject_qnap_argument(evidence_root, "qualification evidence root")
    project_root = _existing_directory(project_root, "project root")
    corpus_root = _existing_directory(corpus_root, "protected corpus root")
    native_corpus_root = (
        _existing_directory(native_corpus_root or corpus_root, "native-rate corpus root")
        if include_historical
        else corpus_root
    )
    evidence_root = _writable_root(evidence_root)
    _reject_qnap(project_root, "project root")
    _reject_qnap(corpus_root, "protected corpus root")
    _reject_qnap(native_corpus_root, "native-rate corpus root")
    _reject_qnap(evidence_root, "qualification evidence root")
    database_identity = _validate_qualification_database(database_url)
    initial_schemas = _qualification_schemas(database_url)
    if initial_schemas != ("public",):
        raise ValueError(
            "qualification database must start with only the public schema; found "
            + ", ".join(initial_schemas)
        )
    source_identity = _source_identity(project_root)
    revision = source_identity.revision
    _validate_deployed_release(project_root, revision)

    resource_units = maximum_resource_units
    if resource_units is None:
        resource_units = min(_MAXIMUM_RESOURCE_UNITS, max(2, os.cpu_count() or 2))
    if not 2 <= resource_units <= _MAXIMUM_RESOURCE_UNITS:
        raise ValueError("maximum resource units must be between 2 and 4")

    identifier = run_id or _automatic_run_id(revision)
    _validate_run_id(identifier)
    run_root = evidence_root / identifier
    run_root.mkdir(mode=0o750)
    logs_root = run_root / "logs"
    results_root = run_root / "results"
    logs_root.mkdir(mode=0o750)
    results_root.mkdir(mode=0o750)

    started = datetime.now(UTC)
    with tempfile.TemporaryDirectory(prefix="leo-release-qualification-") as temporary:
        scratch_root = Path(temporary).resolve()
        scratch_web = scratch_root / "web"
        shutil.copytree(project_root / "web", scratch_web, symlinks=True)
        shutil.rmtree(scratch_web / "dist", ignore_errors=True)
        shutil.rmtree(scratch_web / "node_modules/.cache", ignore_errors=True)
        web_dist = scratch_root / "web-dist"
        command_documents = release_qualification_v3_command_documents(
            include_historical=include_historical
        )
        lane_input_digests = _lane_input_digests(
            project_root,
            command_documents,
            python_version=platform.python_version(),
            platform_identity=platform.platform(),
        )
        definition = release_qualification_v3_definition(
            run_id=identifier,
            started_utc=_utc_text(started),
            git_revision=revision,
            git_tree=source_identity.tree,
            source_identity_kind=source_identity.kind,
            python_version=platform.python_version(),
            platform_identity=platform.platform(),
            uv_lock_sha256=_sha256(project_root / "uv.lock"),
            package_lock_sha256=_sha256(project_root / "web" / "package-lock.json"),
            corpus_manifest_sha256=_sha256(project_root / "corpus" / "manifest.json"),
            database_identity=database_identity,
            protected_corpus_root=str(corpus_root),
            native_rate_corpus_root=str(native_corpus_root),
            maximum_resource_units=resource_units,
            include_historical=include_historical,
            lane_input_digests=lane_input_digests,
        )
        commands = _materialize_v3_commands(
            definition,
            project_root=project_root,
            run_root=run_root,
            scratch_root=scratch_root,
        )
        required_names = (
            RELEASE_QUALIFICATION_V3_ALL_COMMAND_NAMES
            if include_historical
            else RELEASE_QUALIFICATION_V3_COMMAND_NAMES
        )
        if tuple(command.name for command in commands) != required_names:
            raise RuntimeError("release qualification command inventory changed")
        _create_json(run_root / "definition.json", definition)

        reused_outcomes, reused_lanes = _materialize_reusable_lanes(
            evidence_root=evidence_root,
            current_run_root=run_root,
            project_root=project_root,
            definition=definition,
            commands=commands,
        )
        execution_web_dist = (
            project_root / "web" / "dist" if "production-web-build" in reused_outcomes else web_dist
        )

        environment = _isolated_environment(
            database_url=database_url,
            corpus_root=corpus_root,
            native_corpus_root=native_corpus_root,
            web_dist=execution_web_dist,
            scratch_root=scratch_root,
        )
        outcomes = _run_commands_bounded(
            commands,
            environment=environment,
            run_root=run_root,
            results_root=results_root,
            web_dist=web_dist,
            database_url=database_url,
            maximum_resource_units=resource_units,
            initial_outcomes=reused_outcomes,
        )
        passed = all(outcome["passed"] for outcome in outcomes)

    finished = datetime.now(UTC)
    evidence = _evidence_inventory(run_root)
    receipt = {
        "schema": _SCHEMA,
        "run_id": identifier,
        "status": "passed" if passed else "failed",
        "passed": passed,
        "started_utc": _utc_text(started),
        "finished_utc": _utc_text(finished),
        "duration_seconds": (finished - started).total_seconds(),
        "git_revision": revision,
        "git_tree": source_identity.tree,
        "source_identity_kind": source_identity.kind,
        "maximum_resource_units": resource_units,
        "include_historical": include_historical,
        "reused_lanes": reused_lanes,
        "definition_relative_path": "definition.json",
        "definition_sha256": _sha256(run_root / "definition.json"),
        "commands": outcomes,
        "evidence": evidence,
    }
    receipt_path = run_root / "receipt.json"
    _create_json(receipt_path, receipt)
    _seal_tree(run_root)
    if not passed:
        raise QualificationFailed(receipt_path)
    return receipt_path


class QualificationFailed(RuntimeError):
    """The lane ran to a sealed failing receipt."""

    def __init__(self, receipt_path: Path) -> None:
        self.receipt_path = receipt_path
        super().__init__(f"release qualification failed; receipt: {receipt_path}")


def _run_commands_bounded(
    commands: Sequence[QualificationCommand],
    *,
    environment: Mapping[str, str],
    run_root: Path,
    results_root: Path,
    web_dist: Path,
    database_url: str,
    maximum_resource_units: int,
    initial_outcomes: Mapping[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Execute a small dependency graph with weighted and database bounds."""

    outcomes = dict(initial_outcomes or {})
    if not set(outcomes) <= {command.name for command in commands}:
        raise RuntimeError("initial qualification outcome inventory is not a command subset")
    pending = [command for command in commands if command.name not in outcomes]
    running: dict[Future[dict[str, Any]], QualificationCommand] = {}
    running_units = 0
    database_running = False
    with ThreadPoolExecutor(
        max_workers=maximum_resource_units,
        thread_name_prefix="release-qualification",
    ) as executor:
        while pending or running:
            progressed = False
            for command in tuple(pending):
                failed_dependencies = tuple(
                    dependency
                    for dependency in command.depends_on
                    if dependency in outcomes and not outcomes[dependency]["passed"]
                )
                if failed_dependencies:
                    outcomes[command.name] = _blocked_command_outcome(
                        command,
                        run_root=run_root,
                        results_root=results_root,
                        failed_dependencies=failed_dependencies,
                    )
                    pending.remove(command)
                    progressed = True

            for command in tuple(pending):
                if any(dependency not in outcomes for dependency in command.depends_on):
                    continue
                if running_units + command.resource_units > maximum_resource_units:
                    continue
                if command.database_access and database_running:
                    continue
                future = executor.submit(
                    _execute_command,
                    command,
                    environment=environment,
                    run_root=run_root,
                    results_root=results_root,
                    web_dist=web_dist,
                    database_url=database_url,
                )
                running[future] = command
                running_units += command.resource_units
                database_running = database_running or command.database_access
                pending.remove(command)
                progressed = True

            if running:
                completed, _remaining = wait(tuple(running), return_when=FIRST_COMPLETED)
                for future in completed:
                    command = running.pop(future)
                    running_units -= command.resource_units
                    if command.database_access:
                        database_running = False
                    try:
                        outcomes[command.name] = future.result()
                    except Exception as error:  # fail closed and preserve a sealed receipt
                        outcomes[command.name] = _exception_command_outcome(
                            command,
                            run_root=run_root,
                            results_root=results_root,
                            error=error,
                        )
                progressed = True
            if not progressed:
                unresolved = ", ".join(command.name for command in pending)
                raise RuntimeError(
                    f"release qualification lane graph cannot progress: {unresolved}"
                )
    return [outcomes[command.name] for command in commands]


def _execute_command(
    command: QualificationCommand,
    *,
    environment: Mapping[str, str],
    run_root: Path,
    results_root: Path,
    web_dist: Path,
    database_url: str,
) -> dict[str, Any]:
    command_started = datetime.now(UTC)
    log_path = run_root / command.log_relative_path
    exit_code = 70
    validation_error = None
    cleanup_error = None
    try:
        exit_code = _run_command(command, environment, log_path)
        if exit_code == 0:
            validation_error = _validate_command_evidence(
                command.name,
                run_root=run_root,
                web_dist=web_dist,
                results_root=results_root,
            )
    finally:
        if command.database_access:
            try:
                cleanup_error = _validate_database_cleanup(database_url)
            except Exception as error:  # fail closed on an unavailable cleanup proof
                cleanup_error = (
                    "qualification database cleanup could not be verified: "
                    f"{type(error).__name__}: {error}"
                )
    if cleanup_error is not None:
        validation_error = _combine_validation_errors(validation_error, cleanup_error)
    if validation_error is not None:
        exit_code = 70
        validation_path = results_root / f"{command.name}.validation-error.txt"
        if not validation_path.exists():
            _create_text(validation_path, validation_error + "\n")
    command_finished = datetime.now(UTC)
    return _command_outcome(
        command,
        run_root=run_root,
        started=command_started,
        finished=command_finished,
        exit_code=exit_code,
        validation_error=validation_error,
    )


def _blocked_command_outcome(
    command: QualificationCommand,
    *,
    run_root: Path,
    results_root: Path,
    failed_dependencies: Sequence[str],
) -> dict[str, Any]:
    started = datetime.now(UTC)
    reason = "blocked by failed lane dependencies: " + ", ".join(failed_dependencies)
    _create_text(run_root / command.log_relative_path, reason + "\n")
    _create_text(results_root / f"{command.name}.validation-error.txt", reason + "\n")
    return _command_outcome(
        command,
        run_root=run_root,
        started=started,
        finished=datetime.now(UTC),
        exit_code=70,
        validation_error=reason,
    )


def _exception_command_outcome(
    command: QualificationCommand,
    *,
    run_root: Path,
    results_root: Path,
    error: Exception,
) -> dict[str, Any]:
    finished = datetime.now(UTC)
    reason = f"lane execution failed closed: {type(error).__name__}: {error}"
    log_path = run_root / command.log_relative_path
    if not log_path.exists():
        _create_text(log_path, reason + "\n")
    validation_path = results_root / f"{command.name}.validation-error.txt"
    if not validation_path.exists():
        _create_text(validation_path, reason + "\n")
    return _command_outcome(
        command,
        run_root=run_root,
        started=finished,
        finished=finished,
        exit_code=70,
        validation_error=reason,
    )


def _command_outcome(
    command: QualificationCommand,
    *,
    run_root: Path,
    started: datetime,
    finished: datetime,
    exit_code: int,
    validation_error: str | None,
) -> dict[str, Any]:
    log_path = run_root / command.log_relative_path
    result_relative_path = RELEASE_QUALIFICATION_V3_RESULT_PATHS[command.name]
    result_path = run_root / result_relative_path
    return {
        "name": command.name,
        "exit_code": exit_code,
        "passed": exit_code == 0,
        "release_blocking": command.release_blocking,
        "resource_units": command.resource_units,
        "database_access": command.database_access,
        "depends_on": list(command.depends_on),
        "command_sha256": command.command_sha256,
        "reuse_key_sha256": command.reuse_key_sha256,
        "started_utc": _utc_text(started),
        "finished_utc": _utc_text(finished),
        "duration_seconds": (finished - started).total_seconds(),
        "log_relative_path": command.log_relative_path,
        "log_sha256": _sha256(log_path),
        "result_relative_path": result_relative_path if result_path.is_file() else None,
        "result_sha256": _sha256(result_path) if result_path.is_file() else None,
        "validation_error": validation_error,
    }


def _materialize_reusable_lanes(
    *,
    evidence_root: Path,
    current_run_root: Path,
    project_root: Path,
    definition: Mapping[str, Any],
    commands: Sequence[QualificationCommand],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    """Copy strictly revalidated lanes into a new exact-target evidence run."""

    expected_documents = definition.get("commands")
    if not isinstance(expected_documents, list):
        raise RuntimeError("current V3 definition has no command inventory")
    expected_by_name = {
        document["name"]: document
        for document in expected_documents
        if isinstance(document, dict) and isinstance(document.get("name"), str)
    }
    candidates: list[tuple[Path, dict[str, Any], dict[str, Any], str]] = []
    cutoff = datetime.now(UTC).timestamp() - _REUSE_MAXIMUM_AGE_SECONDS
    recent_roots: list[tuple[float, Path]] = []
    for path in evidence_root.iterdir():
        try:
            metadata = path.lstat()
        except OSError:
            continue
        if stat.S_ISDIR(metadata.st_mode) and metadata.st_mtime >= cutoff:
            recent_roots.append((metadata.st_mtime, path))
    ordered_roots = (
        path
        for _modified, path in sorted(
            recent_roots,
            key=lambda item: (item[0], item[1].name),
            reverse=True,
        )[:_REUSE_MAXIMUM_CANDIDATES]
    )
    for candidate_root in ordered_roots:
        if candidate_root == current_run_root:
            continue
        try:
            receipt, source_definition, receipt_sha256 = _validated_reuse_candidate(candidate_root)
        except (OSError, ValueError):
            continue
        candidates.append((candidate_root, receipt, source_definition, receipt_sha256))

    outcomes: dict[str, dict[str, Any]] = {}
    provenance: list[dict[str, str]] = []
    for command in commands:
        expected = expected_by_name[command.name]
        for candidate_root, receipt, source_definition, receipt_sha256 in candidates:
            candidate_documents = source_definition.get("commands")
            if not isinstance(candidate_documents, list):
                continue
            candidate_document = next(
                (
                    document
                    for document in candidate_documents
                    if isinstance(document, dict) and document.get("name") == command.name
                ),
                None,
            )
            candidate_outcomes = receipt.get("commands")
            if not isinstance(candidate_outcomes, list):
                continue
            candidate_outcome = next(
                (
                    outcome
                    for outcome in candidate_outcomes
                    if isinstance(outcome, dict) and outcome.get("name") == command.name
                ),
                None,
            )
            try:
                if candidate_document != expected or candidate_outcome is None:
                    continue
                validate_reusable_release_qualification_v3_lane(candidate_outcome, expected)
                payloads = _validated_reusable_lane_payloads(
                    candidate_root,
                    project_root=project_root,
                    command=command,
                    outcome=candidate_outcome,
                )
            except (OSError, ValueError):
                continue
            for relative_path, payload in payloads.items():
                destination = current_run_root / relative_path
                destination.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
                _create_bytes(destination, payload)
            reused_at = datetime.now(UTC)
            outcomes[command.name] = _command_outcome(
                command,
                run_root=current_run_root,
                started=reused_at,
                finished=reused_at,
                exit_code=0,
                validation_error=None,
            )
            provenance.append(
                {
                    "name": command.name,
                    "reuse_key_sha256": command.reuse_key_sha256,
                    "source_run_id": str(receipt["run_id"]),
                    "source_git_revision": str(receipt["git_revision"]),
                    "source_receipt_sha256": receipt_sha256,
                }
            )
            break
    return outcomes, provenance


def _validated_reuse_candidate(
    root: Path,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    root_metadata = root.lstat()
    if (
        not stat.S_ISDIR(root_metadata.st_mode)
        or root.resolve(strict=True) != root
        or stat.S_IMODE(root_metadata.st_mode) & 0o222
    ):
        raise ValueError("reusable qualification root is not a sealed regular directory")
    _validate_sealed_tree(root)
    receipt_path = root / "receipt.json"
    receipt_payload = _read_sealed_regular_file(receipt_path, "reusable qualification receipt")
    receipt = _strict_json_object(receipt_payload, "reusable qualification receipt")
    if (
        receipt.get("schema") != _SCHEMA
        or receipt.get("run_id") != root.name
        or not _is_hex_digest(receipt.get("git_revision"), length=40)
        or receipt.get("definition_relative_path") != "definition.json"
    ):
        raise ValueError("reusable qualification receipt identity is invalid")
    definition_path = root / "definition.json"
    definition_payload = _read_sealed_regular_file(
        definition_path, "reusable qualification definition"
    )
    if receipt.get("definition_sha256") != hashlib.sha256(definition_payload).hexdigest():
        raise ValueError("reusable qualification definition digest does not match")
    definition = _strict_json_object(definition_payload, "reusable qualification definition")
    if definition.get("schema") != _SCHEMA or definition.get("run_id") != receipt["run_id"]:
        raise ValueError("reusable qualification definition identity does not match")
    if receipt.get("evidence") != _evidence_inventory(root):
        raise ValueError("reusable qualification evidence inventory does not match")
    return receipt, definition, hashlib.sha256(receipt_payload).hexdigest()


def _validated_reusable_lane_payloads(
    source_root: Path,
    *,
    project_root: Path,
    command: QualificationCommand,
    outcome: Mapping[str, Any],
) -> dict[str, bytes]:
    log_relative = command.log_relative_path
    result_relative = RELEASE_QUALIFICATION_V3_RESULT_PATHS[command.name]
    log_payload = _read_sealed_regular_file(
        source_root / log_relative, f"{command.name} reusable log"
    )
    result_payload = _read_sealed_regular_file(
        source_root / result_relative, f"{command.name} reusable result"
    )
    if hashlib.sha256(log_payload).hexdigest() != outcome.get("log_sha256") or hashlib.sha256(
        result_payload
    ).hexdigest() != outcome.get("result_sha256"):
        raise ValueError("reusable qualification lane evidence digest does not match")
    result = _strict_json_object(result_payload, f"{command.name} reusable result")
    payloads = {log_relative: log_payload, result_relative: result_payload}

    junit_relative = RELEASE_QUALIFICATION_V3_JUNIT_PATHS.get(command.name)
    if junit_relative is not None:
        junit_payload = _read_sealed_regular_file(
            source_root / junit_relative, f"{command.name} reusable JUnit receipt"
        )
        validate_pytest_junit_summary_v1(
            result,
            junit_payload,
            command_name=command.name,
            junit_relative_path=junit_relative,
        )
        payloads[junit_relative] = junit_payload
    elif command.name == "production-web-build":
        current_web = _regular_file_inventory(
            project_root / "web" / "dist", "current staged compiled web output"
        )
        if result != {
            "schema": _SCHEMA,
            "kind": "compiled-web-inventory",
            "files": current_web,
        }:
            raise ValueError("reusable web lane differs from current staged compiled output")
    elif command.name == "production-chromium-e2e":
        browser_root = source_root / "results" / "playwright"
        browser_files = (
            []
            if not browser_root.exists()
            else _regular_file_inventory(browser_root, "reusable Playwright output")
        )
        if result != {
            "schema": _SCHEMA,
            "kind": "production-chromium-e2e-result",
            "project": "production-chromium",
            "passed": True,
            "files": browser_files,
        }:
            raise ValueError("reusable Chromium result inventory does not match")
        for item in browser_files:
            relative = f"results/playwright/{item['relative_path']}"
            payloads[relative] = _read_sealed_regular_file(
                source_root / relative, "reusable Playwright evidence"
            )
    return payloads


def _read_sealed_regular_file(
    path: Path,
    label: str,
    *,
    maximum_bytes: int = MAXIMUM_JUNIT_BYTES,
) -> bytes:
    payload = _read_regular_file(path, label, maximum_bytes=maximum_bytes)
    if stat.S_IMODE(path.lstat().st_mode) & 0o222:
        raise ValueError(f"{label} is not sealed read-only")
    return payload


def _validate_sealed_tree(root: Path) -> None:
    for path in root.rglob("*"):
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"reusable qualification evidence contains a symlink: {path}")
        if not (stat.S_ISREG(metadata.st_mode) or stat.S_ISDIR(metadata.st_mode)):
            raise ValueError(f"reusable qualification evidence contains a special file: {path}")
        if stat.S_IMODE(metadata.st_mode) & 0o222:
            raise ValueError(f"reusable qualification evidence is not sealed: {path}")


def _validate_deployed_release(project_root: Path, revision: str) -> None:
    releases_root = _DEPLOYMENT_ROOT / "releases"
    if project_root.parent != releases_root:
        return
    if project_root.name != revision or len(revision) != 40:
        raise ValueError("deployed release path must end in its full Git revision")
    metadata = _DEPLOYMENT_ROOT / "release-metadata" / f"{revision}.txt"
    if metadata.is_symlink() or not metadata.is_file():
        raise ValueError("deployed release has no sealed external metadata")
    metadata_validator = project_root / "deploy/scripts/validate-release-metadata"
    runtime_validator = project_root / "deploy/scripts/validate-published-release"
    python = project_root / ".venv/bin/python"
    for required in (metadata_validator, runtime_validator, python):
        if not required.is_file() or not os.access(required, os.X_OK):
            raise ValueError(f"deployed release validator is absent: {required}")
    staging = releases_root / f".staging-{revision}"
    subprocess.run(
        (str(metadata_validator), str(project_root), str(metadata), revision),
        stdin=subprocess.DEVNULL,
        check=True,
    )
    subprocess.run(
        (str(python), str(runtime_validator), str(project_root), str(staging)),
        stdin=subprocess.DEVNULL,
        check=True,
    )


def _run_command(
    command: QualificationCommand,
    environment: Mapping[str, str],
    log_path: Path,
) -> int:
    descriptor = os.open(
        log_path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o640,
    )
    with os.fdopen(descriptor, "wb") as log:
        try:
            result = subprocess.run(  # noqa: S603 - argv is a closed internal inventory
                command.argv,
                cwd=command.cwd,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
            return_code = result.returncode
        except OSError as error:
            diagnostic = (
                "release qualification could not execute command: "
                f"{type(error).__name__}: {error}\n"
            )
            log.write(diagnostic.encode("utf-8", errors="replace"))
            return_code = 70
        log.flush()
        os.fsync(log.fileno())
    os.chmod(log_path, 0o440)
    return return_code


def _isolated_environment(
    *,
    database_url: str,
    corpus_root: Path,
    native_corpus_root: Path,
    web_dist: Path,
    scratch_root: Path,
) -> dict[str, str]:
    scratch_home = scratch_root / "home"
    scratch_home.mkdir(mode=0o700)
    environment = {
        key: value for key, value in os.environ.items() if key in _CHILD_ENVIRONMENT_ALLOWLIST
    }
    environment.update(
        {
            "HOME": str(scratch_home),
            "PYTHONDONTWRITEBYTECODE": "1",
            "TMPDIR": str(scratch_root),
            "LEO_TEST_DATABASE_URL": database_url,
            "LEO_E2E_DATABASE_URL": database_url,
            "LEO_REAL_CORPUS_ROOT": str(corpus_root),
            "LEO_NATIVE_REAL_CORPUS_ROOT": str(native_corpus_root),
            "LEO_E2E_WEB_DIST": str(web_dist),
        }
    )
    return environment


def _validate_command_evidence(
    command_name: str,
    *,
    run_root: Path,
    web_dist: Path,
    results_root: Path,
) -> str | None:
    try:
        junit_relative = RELEASE_QUALIFICATION_V3_JUNIT_PATHS.get(command_name)
        if junit_relative is not None:
            junit = run_root / junit_relative
            payload = _read_regular_file(
                junit,
                f"{command_name} JUnit receipt",
                maximum_bytes=MAXIMUM_JUNIT_BYTES,
            )
            summary = summarize_pytest_junit_v1(
                payload,
                command_name=command_name,
                junit_relative_path=junit_relative,
            )
            _create_json(
                run_root / RELEASE_QUALIFICATION_V3_RESULT_PATHS[command_name],
                summary,
            )
        elif command_name == "production-web-build":
            files = _regular_file_inventory(web_dist, "compiled web output")
            if not any(item["relative_path"] == "index.html" for item in files):
                return "web build exited successfully without a compiled index.html"
            _create_json(
                results_root / "web-build.json",
                {
                    "schema": _SCHEMA,
                    "kind": "compiled-web-inventory",
                    "files": files,
                },
            )
        elif command_name == "production-chromium-e2e":
            browser_root = results_root / "playwright"
            files = (
                []
                if not browser_root.exists()
                else _regular_file_inventory(browser_root, "Playwright output")
            )
            _create_json(
                results_root / "browser-e2e.json",
                {
                    "schema": _SCHEMA,
                    "kind": "production-chromium-e2e-result",
                    "project": "production-chromium",
                    "passed": True,
                    "files": files,
                },
            )
    except (OSError, ValueError) as error:
        return f"{command_name} result evidence is invalid: {error}"
    return None


def _validate_database_cleanup(database_url: str) -> str | None:
    schemas = _qualification_schemas(database_url)
    if schemas == ("public",):
        return None
    leaked = tuple(schema for schema in schemas if schema != "public")
    controlled_prefixes = ("leo_e2e_", "leo_processing_", "leo_test_")
    if all(schema.startswith(controlled_prefixes) for schema in leaked):
        return (
            f"qualification command leaked PostgreSQL schemas {list(leaked)!r}; "
            "automatic cross-process deletion is forbidden"
        )
    return f"qualification command created unexpected PostgreSQL schemas {list(leaked)!r}"


@contextmanager
def _exclusive_qualification_database_lock():
    """Exclude qualification while shared isolated-schema test gates are active."""

    descriptor = os.open(
        _QUALIFICATION_DATABASE_LOCK,
        os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _qualification_schemas(database_url: str) -> tuple[str, ...]:
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            return tuple(
                connection.execute(
                    text(
                        "SELECT schema_name FROM information_schema.schemata "
                        "WHERE schema_name <> 'information_schema' "
                        "AND schema_name NOT LIKE 'pg_%' ORDER BY schema_name"
                    )
                ).scalars()
            )
    finally:
        engine.dispose()


def _validate_qualification_database(database_url: str) -> str:
    try:
        parsed = make_url(database_url)
    except Exception as error:
        raise ValueError("invalid qualification database URL") from error
    if not parsed.drivername.startswith("postgresql"):
        raise ValueError("qualification database must use PostgreSQL")
    database = parsed.database or ""
    normalized = database.casefold()
    if normalized == _PRODUCTION_DATABASE or not (
        "qualification" in normalized or normalized.endswith("_test")
    ):
        raise ValueError(
            "qualification database name must contain 'qualification' or end in '_test', "
            "and cannot be leo_tracker"
        )
    return parsed.render_as_string(hide_password=True)


def _source_identity(project_root: Path) -> SourceIdentity:
    marker = project_root / _SOURCE_MARKER
    if marker.exists():
        document = _strict_json_object(
            _read_sealed_regular_file(
                marker,
                "release source marker",
                maximum_bytes=4_096,
            ),
            "release source marker",
        )
        if set(document) != {"schema", "revision", "tree"}:
            raise ValueError("release source marker schema is not closed")
        revision = document.get("revision")
        tree = document.get("tree")
        if (
            document.get("schema") != _SOURCE_MARKER_SCHEMA
            or not _is_hex_digest(revision, length=40)
            or not _is_hex_digest(tree, length=40)
        ):
            raise ValueError("release source marker is malformed")
        assert isinstance(revision, str)
        assert isinstance(tree, str)
        return SourceIdentity(revision=revision, tree=tree, kind="sealed-release-marker")

    revision = _git_output(project_root, "rev-parse", "HEAD")
    tree = _git_output(project_root, "rev-parse", "HEAD^{tree}")
    if not _is_hex_digest(revision, length=40) or not _is_hex_digest(tree, length=40):
        raise ValueError("release qualification Git identity is malformed")
    if _git_output(project_root, "status", "--porcelain"):
        raise ValueError("release qualification requires a clean Git checkout")
    return SourceIdentity(revision=revision, tree=tree, kind="clean-git-checkout")


def _lane_input_digests(
    project_root: Path,
    command_documents: Sequence[Mapping[str, Any]],
    *,
    python_version: str,
    platform_identity: str,
) -> dict[str, dict[str, str]]:
    """Hash bounded lane inputs without coupling reuse to the commit revision."""

    command_names = tuple(str(command["name"]) for command in command_documents)
    paths = sorted(
        {path for name in command_names for path in RELEASE_QUALIFICATION_V3_LANE_INPUT_PATHS[name]}
    )
    path_digests = {path: _bounded_path_content_digest(project_root, path) for path in paths}
    runtime = release_qualification_v3_runtime_digest(
        python_version=python_version,
        platform_identity=platform_identity,
    )
    return release_qualification_v3_lane_input_digests(
        command_documents,
        path_digests=path_digests,
        python_runtime_sha256=runtime,
    )


def _bounded_path_content_digest(project_root: Path, relative_path: str) -> str:
    path = project_root / relative_path
    metadata = path.lstat()
    if stat.S_ISREG(metadata.st_mode):
        return _sha256(path)
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError(f"qualification input path is not regular: {relative_path}")
    exclusions = (
        frozenset({"node_modules", "dist", "test-results", "playwright-report"})
        if relative_path == "web"
        else frozenset()
    )
    return _tree_content_digest(path, excluded_directories=exclusions)


def _tree_content_digest(
    root: Path,
    *,
    excluded_directories: frozenset[str] = frozenset(),
) -> str:
    root = root.resolve(strict=True)
    inventory: list[dict[str, Any]] = []
    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        ignored_directories = excluded_directories | _IGNORED_INPUT_DIRECTORIES
        directory_names[:] = sorted(
            name for name in directory_names if name not in ignored_directories
        )
        base = Path(directory)
        for name in directory_names:
            path = base / name
            if path.is_symlink():
                raise ValueError(f"qualification input tree contains a directory symlink: {path}")
        for name in sorted(file_names):
            path = base / name
            metadata = path.lstat()
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError(f"qualification input tree contains a non-regular file: {path}")
            inventory.append(
                {
                    "relative_path": path.relative_to(root).as_posix(),
                    "bytes": metadata.st_size,
                    "sha256": _sha256(path),
                }
            )
    return release_qualification_v3_inventory_digest(inventory)


def _strict_json_object(payload: bytes, label: str) -> dict[str, Any]:
    def closed_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        document: dict[str, Any] = {}
        for key, value in pairs:
            if key in document:
                raise ValueError(f"{label} contains a duplicate JSON key: {key}")
            document[key] = value
        return document

    try:
        document = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=closed_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"{label} contains a non-finite value: {value}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not strict UTF-8 JSON") from error
    if not isinstance(document, dict):
        raise ValueError(f"{label} must be a JSON object")
    return document


def _is_hex_digest(value: object, *, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
    )


def _materialize_v3_commands(
    definition: Mapping[str, Any],
    *,
    project_root: Path,
    run_root: Path,
    scratch_root: Path,
) -> tuple[QualificationCommand, ...]:
    documents = definition.get("commands")
    if not isinstance(documents, list):
        raise RuntimeError("release qualification V3 definition has no command inventory")
    replacements = (
        ("$EVIDENCE_ROOT/$RUN_ID", str(run_root)),
        ("$SCRATCH_ROOT", str(scratch_root)),
    )
    commands: list[QualificationCommand] = []
    for document in documents:
        if not isinstance(document, dict) or set(document) != {
            "name",
            "argv",
            "cwd",
            "log_relative_path",
            "resource_units",
            "database_access",
            "depends_on",
            "release_blocking",
            "lane_metadata",
        }:
            raise RuntimeError("release qualification V3 command document is not closed")
        name = document["name"]
        argv = document["argv"]
        cwd = document["cwd"]
        log_relative_path = document["log_relative_path"]
        resource_units = document["resource_units"]
        database_access = document["database_access"]
        depends_on = document["depends_on"]
        release_blocking = document["release_blocking"]
        lane_metadata = document["lane_metadata"]
        if (
            not isinstance(name, str)
            or not isinstance(argv, list)
            or not argv
            or any(not isinstance(item, str) or not item for item in argv)
            or cwd not in {".", "web"}
            or not isinstance(log_relative_path, str)
            or type(resource_units) is not int
            or not 1 <= resource_units <= _MAXIMUM_RESOURCE_UNITS
            or type(database_access) is not bool
            or not isinstance(depends_on, list)
            or any(not isinstance(item, str) for item in depends_on)
            or type(release_blocking) is not bool
            or not isinstance(lane_metadata, dict)
            or set(lane_metadata)
            != {
                "command_sha256",
                "input_digests",
                "reuse_key_sha256",
            }
            or not _is_hex_digest(lane_metadata["command_sha256"], length=64)
            or not _is_hex_digest(lane_metadata["reuse_key_sha256"], length=64)
        ):
            raise RuntimeError("release qualification V3 command document is malformed")
        materialized = list(argv)
        for placeholder, value in replacements:
            materialized = [item.replace(placeholder, value) for item in materialized]
        commands.append(
            QualificationCommand(
                name=name,
                argv=tuple(materialized),
                cwd=project_root if cwd == "." else project_root / "web",
                log_relative_path=log_relative_path,
                resource_units=resource_units,
                database_access=database_access,
                depends_on=tuple(depends_on),
                release_blocking=release_blocking,
                command_sha256=lane_metadata["command_sha256"],
                reuse_key_sha256=lane_metadata["reuse_key_sha256"],
            )
        )
    return tuple(commands)


def _combine_validation_errors(left: str | None, right: str) -> str:
    return right if left is None else f"{left}; {right}"


def _read_regular_file(
    path: Path,
    label: str,
    *,
    maximum_bytes: int | None = None,
) -> bytes:
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{label} must be a regular non-symlink file")
    if maximum_bytes is not None and metadata.st_size > maximum_bytes:
        raise ValueError(f"{label} exceeds its byte boundary")
    return path.read_bytes()


def _regular_file_inventory(root: Path, label: str) -> list[dict[str, Any]]:
    metadata = root.lstat()
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError(f"{label} root must be a regular non-symlink directory")
    inventory: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        item_metadata = path.lstat()
        if stat.S_ISLNK(item_metadata.st_mode):
            raise ValueError(f"{label} contains a symlink: {path.relative_to(root)}")
        if stat.S_ISDIR(item_metadata.st_mode):
            continue
        if not stat.S_ISREG(item_metadata.st_mode):
            raise ValueError(f"{label} contains a non-regular entry: {path.relative_to(root)}")
        inventory.append(
            {
                "relative_path": path.relative_to(root).as_posix(),
                "bytes": item_metadata.st_size,
                "sha256": _sha256(path),
            }
        )
    return inventory


def _evidence_inventory(run_root: Path) -> list[dict[str, Any]]:
    return [
        item
        for item in _regular_file_inventory(run_root, "release qualification evidence")
        if item["relative_path"] != "receipt.json"
    ]


def _create_json(path: Path, document: Mapping[str, Any]) -> None:
    payload = canonical_json_bytes(dict(document)) + b"\n"
    _create_bytes(path, payload)


def _create_text(path: Path, text: str) -> None:
    _create_bytes(path, text.encode())


def _create_bytes(path: Path, payload: bytes) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o440,
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _seal_tree(root: Path) -> None:
    root_metadata = root.lstat()
    if not stat.S_ISDIR(root_metadata.st_mode):
        raise ValueError("release qualification run root must be a non-symlink directory")
    paths = sorted(
        root.rglob("*"),
        key=lambda path: (len(path.relative_to(root).parts), path.as_posix()),
        reverse=True,
    )
    for path in paths:
        metadata = path.lstat()
        if stat.S_ISREG(metadata.st_mode):
            os.chmod(path, stat.S_IRUSR | stat.S_IRGRP)
        elif stat.S_ISDIR(metadata.st_mode):
            os.chmod(path, stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP)
        else:
            raise ValueError(
                "release qualification evidence contains a symlink or non-regular entry: "
                f"{path.relative_to(root)}"
            )
    os.chmod(root, stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP)


def _git_output(project_root: Path, *arguments: str) -> str:
    result = subprocess.run(  # noqa: S603,S607 - fixed git executable and caller-owned literals
        ("git", *arguments),
        cwd=project_root,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _existing_directory(path: Path, label: str) -> Path:
    if not path.is_absolute():
        raise ValueError(f"{label} must be absolute")
    resolved = path.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError(f"{label} must be a directory")
    return resolved


def _writable_root(path: Path) -> Path:
    if not path.is_absolute():
        raise ValueError("qualification evidence root must be absolute")
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("qualification evidence root cannot be a symlink")
    return path.resolve(strict=True)


def _reject_qnap(path: Path, label: str) -> None:
    if path == _QNAP_ROOT or _QNAP_ROOT in path.parents:
        raise ValueError(f"{label} cannot be beneath /mnt/qnap01")


def _reject_qnap_argument(path: Path, label: str) -> None:
    if not path.is_absolute():
        return
    normalized = Path(os.path.abspath(path))
    _reject_qnap(normalized, label)


def _validate_run_id(run_id: str) -> None:
    if (
        not run_id
        or len(run_id) > 96
        or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
            for character in run_id
        )
    ):
        raise ValueError("run ID must be 1-96 safe filename characters")


def _automatic_run_id(revision: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"release-{timestamp}-{revision[:12]}"


def _utc_text(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run isolated protected-corpus and production Chromium qualification."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Clean deployed Git checkout (default: current directory).",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("LEO_QUALIFICATION_DATABASE_URL"),
        help="Dedicated qualification PostgreSQL URL (or LEO_QUALIFICATION_DATABASE_URL).",
    )
    parser.add_argument(
        "--corpus-root",
        type=Path,
        default=Path(os.environ.get("LEO_QUALIFICATION_CORPUS_ROOT", "/srv/bulk/leo/test-corpus")),
    )
    parser.add_argument(
        "--native-corpus-root",
        type=Path,
        default=Path(
            os.environ.get(
                "LEO_NATIVE_REAL_CORPUS_ROOT",
                "/srv/bulk/leo/recordings/2026/08/25",
            )
        ),
        help="Read-only historical root; required only with --include-historical.",
    )
    parser.add_argument(
        "--evidence-root",
        type=Path,
        default=Path(
            os.environ.get(
                "LEO_RELEASE_QUALIFICATION_ROOT",
                "/srv/bulk/leo/qualification/release",
            )
        ),
    )
    parser.add_argument("--run-id", help="Optional unique stable evidence directory name.")
    parser.add_argument(
        "--maximum-resource-units",
        type=int,
        help="Bounded scheduler capacity (2-4; default: min(host CPUs, 4)).",
    )
    parser.add_argument(
        "--include-historical",
        action="store_true",
        help="Run non-release-blocking historical recording-format lanes explicitly.",
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> None:
    parser = _parser()
    options = parser.parse_args(arguments)
    if not options.database_url:
        parser.error("--database-url or LEO_QUALIFICATION_DATABASE_URL is required")
    try:
        with _exclusive_qualification_database_lock():
            receipt = run_release_qualification(
                project_root=options.project_root,
                database_url=options.database_url,
                corpus_root=options.corpus_root,
                native_corpus_root=options.native_corpus_root,
                evidence_root=options.evidence_root,
                run_id=options.run_id,
                maximum_resource_units=options.maximum_resource_units,
                include_historical=options.include_historical,
            )
    except QualificationFailed as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.error(str(error))
    print(json.dumps({"passed": True, "receipt": str(receipt)}, sort_keys=True))


if __name__ == "__main__":
    main()
