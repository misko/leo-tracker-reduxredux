"""Fail-closed protected-corpus and browser release qualification.

The command intentionally orchestrates the same scientific and browser tests as
CI.  Test-owned PostgreSQL schemas and temporary RecordingStore roots keep it
away from the production catalog and recordings.  Every invocation gets a new,
write-once evidence directory containing the exact definition, command logs,
test results, and a digest inventory.
"""

from __future__ import annotations

import argparse
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
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.schema import DropSchema

from leo.contracts.digests import canonical_json_bytes
from leo.qualification.release_contract import (
    MAXIMUM_JUNIT_BYTES,
    RELEASE_QUALIFICATION_V2_COMMAND_NAMES,
    RELEASE_QUALIFICATION_V2_JUNIT_PATHS,
    RELEASE_QUALIFICATION_V2_RESULT_PATHS,
    RELEASE_QUALIFICATION_V2_SCHEMA,
    release_qualification_v2_definition,
    summarize_pytest_junit_v1,
)

_QNAP_ROOT = Path("/mnt/qnap01")
_DEPLOYMENT_ROOT = Path("/opt/leo-tracker")
_PRODUCTION_DATABASE = "leo_tracker"
_SCHEMA = RELEASE_QUALIFICATION_V2_SCHEMA
_REQUIRED_COMMAND_NAMES = RELEASE_QUALIFICATION_V2_COMMAND_NAMES
_DATABASE_COMMAND_NAMES = frozenset(
    {
        "protected-real-corpus",
        "standard-native-postgresql",
        "production-chromium-e2e",
    }
)
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


def run_release_qualification(
    *,
    project_root: Path,
    database_url: str,
    corpus_root: Path,
    native_corpus_root: Path | None = None,
    evidence_root: Path,
    run_id: str | None = None,
) -> Path:
    """Run the protected corpus and compiled-browser gates and seal a receipt."""

    _reject_qnap_argument(project_root, "project root")
    _reject_qnap_argument(corpus_root, "protected corpus root")
    _reject_qnap_argument(evidence_root, "qualification evidence root")
    project_root = _existing_directory(project_root, "project root")
    corpus_root = _existing_directory(corpus_root, "protected corpus root")
    native_corpus_root = _existing_directory(
        native_corpus_root or corpus_root,
        "native-rate corpus root",
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
    revision = _git_output(project_root, "rev-parse", "HEAD")
    if _git_output(project_root, "status", "--porcelain"):
        raise ValueError("release qualification requires a clean Git checkout")
    _validate_deployed_release(project_root, revision)

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
        definition = release_qualification_v2_definition(
            run_id=identifier,
            started_utc=_utc_text(started),
            git_revision=revision,
            python_version=platform.python_version(),
            platform_identity=platform.platform(),
            uv_lock_sha256=_sha256(project_root / "uv.lock"),
            package_lock_sha256=_sha256(project_root / "web" / "package-lock.json"),
            corpus_manifest_sha256=_sha256(project_root / "corpus" / "manifest.json"),
            database_identity=database_identity,
            protected_corpus_root=str(corpus_root),
            native_rate_corpus_root=str(native_corpus_root),
        )
        commands = _materialize_v2_commands(
            definition,
            project_root=project_root,
            run_root=run_root,
            scratch_root=scratch_root,
        )
        if tuple(command.name for command in commands) != _REQUIRED_COMMAND_NAMES:
            raise RuntimeError("release qualification command inventory changed")
        _create_json(run_root / "definition.json", definition)

        environment = _isolated_environment(
            database_url=database_url,
            corpus_root=corpus_root,
            native_corpus_root=native_corpus_root,
            web_dist=web_dist,
            scratch_root=scratch_root,
        )
        outcomes: list[dict[str, Any]] = []
        passed = True
        for command in commands:
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
                if command.name in _DATABASE_COMMAND_NAMES:
                    try:
                        cleanup_error = _validate_database_cleanup(database_url)
                    except Exception as error:  # fail closed on an unavailable cleanup proof
                        cleanup_error = (
                            "qualification database cleanup could not be verified: "
                            f"{type(error).__name__}: {error}"
                        )
            if cleanup_error is not None:
                validation_error = _combine_validation_errors(
                    validation_error,
                    cleanup_error,
                )
            if validation_error is not None:
                exit_code = 70
                validation_path = results_root / f"{command.name}.validation-error.txt"
                if not validation_path.exists():
                    _create_text(
                        validation_path,
                        validation_error + "\n",
                    )
            command_finished = datetime.now(UTC)
            result_relative_path = RELEASE_QUALIFICATION_V2_RESULT_PATHS[command.name]
            result_path = run_root / result_relative_path
            outcomes.append(
                {
                    "name": command.name,
                    "exit_code": exit_code,
                    "passed": exit_code == 0,
                    "started_utc": _utc_text(command_started),
                    "finished_utc": _utc_text(command_finished),
                    "duration_seconds": (command_finished - command_started).total_seconds(),
                    "log_relative_path": command.log_relative_path,
                    "log_sha256": _sha256(log_path),
                    "result_relative_path": (
                        result_relative_path if result_path.is_file() else None
                    ),
                    "result_sha256": _sha256(result_path) if result_path.is_file() else None,
                    "validation_error": validation_error,
                }
            )
            if exit_code != 0:
                passed = False
                break

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
        junit_relative = RELEASE_QUALIFICATION_V2_JUNIT_PATHS.get(command_name)
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
                run_root / RELEASE_QUALIFICATION_V2_RESULT_PATHS[command_name],
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
        engine = create_engine(database_url, pool_pre_ping=True)
        try:
            with engine.begin() as connection:
                for schema in leaked:
                    connection.execute(DropSchema(schema, cascade=True))
        finally:
            engine.dispose()
        remaining = _qualification_schemas(database_url)
        cleanup = (
            "recognized test schemas were removed"
            if remaining == ("public",)
            else ("cleanup did not restore the public-only baseline")
        )
        return f"qualification command leaked PostgreSQL schemas {list(leaked)!r}; {cleanup}"
    return f"qualification command created unexpected PostgreSQL schemas {list(leaked)!r}"


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


def _materialize_v2_commands(
    definition: Mapping[str, Any],
    *,
    project_root: Path,
    run_root: Path,
    scratch_root: Path,
) -> tuple[QualificationCommand, ...]:
    documents = definition.get("commands")
    if not isinstance(documents, list):
        raise RuntimeError("release qualification V2 definition has no command inventory")
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
        }:
            raise RuntimeError("release qualification V2 command document is not closed")
        name = document["name"]
        argv = document["argv"]
        cwd = document["cwd"]
        log_relative_path = document["log_relative_path"]
        if (
            not isinstance(name, str)
            or not isinstance(argv, list)
            or not argv
            or any(not isinstance(item, str) or not item for item in argv)
            or cwd not in {".", "web"}
            or not isinstance(log_relative_path, str)
        ):
            raise RuntimeError("release qualification V2 command document is malformed")
        materialized = list(argv)
        for placeholder, value in replacements:
            materialized = [item.replace(placeholder, value) for item in materialized]
        commands.append(
            QualificationCommand(
                name=name,
                argv=tuple(materialized),
                cwd=project_root if cwd == "." else project_root / "web",
                log_relative_path=log_relative_path,
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
        help="Read-only root containing the exact named 2.5/3/5 MS/s recordings.",
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
    return parser


def main(arguments: Sequence[str] | None = None) -> None:
    parser = _parser()
    options = parser.parse_args(arguments)
    if not options.database_url:
        parser.error("--database-url or LEO_QUALIFICATION_DATABASE_URL is required")
    try:
        receipt = run_release_qualification(
            project_root=options.project_root,
            database_url=options.database_url,
            corpus_root=options.corpus_root,
            native_corpus_root=options.native_corpus_root,
            evidence_root=options.evidence_root,
            run_id=options.run_id,
        )
    except QualificationFailed as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.error(str(error))
    print(json.dumps({"passed": True, "receipt": str(receipt)}, sort_keys=True))


if __name__ == "__main__":
    main()
