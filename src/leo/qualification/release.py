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

_QNAP_ROOT = Path("/mnt/qnap01")
_DEPLOYMENT_ROOT = Path("/opt/leo-tracker")
_PRODUCTION_DATABASE = "leo_tracker"
_SCHEMA = "org.leo.release-qualification/v1"


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
    evidence_root: Path,
    run_id: str | None = None,
) -> Path:
    """Run the protected corpus and compiled-browser gates and seal a receipt."""

    _reject_qnap_argument(project_root, "project root")
    _reject_qnap_argument(corpus_root, "protected corpus root")
    _reject_qnap_argument(evidence_root, "qualification evidence root")
    project_root = _existing_directory(project_root, "project root")
    corpus_root = _existing_directory(corpus_root, "protected corpus root")
    evidence_root = _writable_root(evidence_root)
    _reject_qnap(project_root, "project root")
    _reject_qnap(corpus_root, "protected corpus root")
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
        browser_output = results_root / "playwright"
        corpus_junit = results_root / "real-corpus.junit.xml"
        commands = (
            QualificationCommand(
                "protected-real-corpus",
                (
                    "uv",
                    "run",
                    "--frozen",
                    "--no-sync",
                    "pytest",
                    "-p",
                    "no:cacheprovider",
                    (
                        "tests/analysis/test_standard_real_corpus_e2e.py::"
                        "test_trial132_one_path_one_coarse_window_benchmark_smoke"
                    ),
                    (
                        "tests/integration/test_standard_v2_operational_vertical.py::"
                        "test_standard_v2_four_path_operational_vertical"
                    ),
                    f"--junitxml={corpus_junit}",
                ),
                project_root,
                "logs/01-protected-real-corpus.log",
            ),
            QualificationCommand(
                "production-web-build",
                (
                    "npm",
                    "--prefix",
                    str(scratch_web),
                    "run",
                    "build",
                    "--",
                    "--outDir",
                    str(web_dist),
                ),
                project_root,
                "logs/02-production-web-build.log",
            ),
            QualificationCommand(
                "production-chromium-e2e",
                (
                    "npm",
                    "run",
                    "test:e2e:production",
                    "--",
                    "--output",
                    str(browser_output),
                ),
                project_root / "web",
                "logs/03-production-chromium-e2e.log",
            ),
        )
        definition = {
            "schema": _SCHEMA,
            "run_id": identifier,
            "started_utc": _utc_text(started),
            "source": {
                "git_revision": revision,
                "git_clean": True,
                "python": platform.python_version(),
                "platform": platform.platform(),
                "uv_lock_sha256": _sha256(project_root / "uv.lock"),
                "package_lock_sha256": _sha256(project_root / "web" / "package-lock.json"),
                "corpus_manifest_sha256": _sha256(project_root / "corpus" / "manifest.json"),
            },
            "isolation": {
                "database": database_identity,
                "database_policy": "dedicated qualification database; unique test schemas",
                "database_initial_schemas": list(initial_schemas),
                "generated_data": "test-owned temporary RecordingStore roots",
                "protected_corpus_root": str(corpus_root),
                "protected_corpus_access": "read-only",
                "qnap_access": "forbidden",
            },
            "commands": [
                _command_document(command, project_root, run_root, scratch_root)
                for command in commands
            ],
        }
        _create_json(run_root / "definition.json", definition)

        environment = _isolated_environment(
            database_url=database_url,
            corpus_root=corpus_root,
            web_dist=web_dist,
        )
        outcomes: list[dict[str, Any]] = []
        passed = True
        for command in commands:
            command_started = datetime.now(UTC)
            log_path = run_root / command.log_relative_path
            exit_code = _run_command(command, environment, log_path)
            validation_error = None
            if exit_code == 0:
                validation_error = _validate_command_evidence(
                    command.name,
                    corpus_junit=corpus_junit,
                    web_dist=web_dist,
                    results_root=results_root,
                    database_url=database_url,
                )
                if validation_error is not None:
                    exit_code = 70
                    _create_text(
                        results_root / f"{command.name}.validation-error.txt",
                        validation_error + "\n",
                    )
            command_finished = datetime.now(UTC)
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
        result = subprocess.run(  # noqa: S603 - argv is a closed internal inventory
            command.argv,
            cwd=command.cwd,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
        log.flush()
        os.fsync(log.fileno())
    os.chmod(log_path, 0o440)
    return result.returncode


def _isolated_environment(
    *,
    database_url: str,
    corpus_root: Path,
    web_dist: Path,
) -> dict[str, str]:
    environment = dict(os.environ)
    for key in ("LEO_DATABASE_URL", "LEO_BULK_ROOT", "LEO_WEB_DIST"):
        environment.pop(key, None)
    environment.update(
        {
            "LEO_TEST_DATABASE_URL": database_url,
            "LEO_E2E_DATABASE_URL": database_url,
            "LEO_REAL_CORPUS_ROOT": str(corpus_root),
            "LEO_E2E_WEB_DIST": str(web_dist),
        }
    )
    return environment


def _validate_command_evidence(
    command_name: str,
    *,
    corpus_junit: Path,
    web_dist: Path,
    results_root: Path,
    database_url: str,
) -> str | None:
    if command_name == "protected-real-corpus":
        if not corpus_junit.is_file() or corpus_junit.is_symlink():
            return "pytest exited successfully without the required real-corpus JUnit receipt"
    elif command_name == "production-web-build":
        index = web_dist / "index.html"
        if not index.is_file() or index.is_symlink():
            return "web build exited successfully without a compiled index.html"
        files = [
            {
                "relative_path": path.relative_to(web_dist).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in sorted(web_dist.rglob("*"))
            if path.is_file() and not path.is_symlink()
        ]
        _create_json(
            results_root / "web-build.json",
            {"schema": _SCHEMA, "kind": "compiled-web-inventory", "files": files},
        )
    if command_name in {"protected-real-corpus", "production-chromium-e2e"}:
        schema_error = _validate_database_cleanup(database_url)
        if schema_error is not None:
            return schema_error
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


def _command_document(
    command: QualificationCommand,
    project_root: Path,
    run_root: Path,
    scratch_root: Path,
) -> dict[str, Any]:
    replacements = (
        (str(run_root), "$EVIDENCE_ROOT/$RUN_ID"),
        (str(scratch_root), "$SCRATCH_ROOT"),
    )
    argv = list(command.argv)
    for source, replacement in replacements:
        argv = [item.replace(source, replacement) for item in argv]
    return {
        "name": command.name,
        "argv": argv,
        "cwd": str(command.cwd.relative_to(project_root) or Path(".")),
        "log_relative_path": command.log_relative_path,
    }


def _evidence_inventory(run_root: Path) -> list[dict[str, Any]]:
    inventory = []
    for path in sorted(run_root.rglob("*")):
        if not path.is_file() or path.name == "receipt.json":
            continue
        inventory.append(
            {
                "relative_path": path.relative_to(run_root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    return inventory


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
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_file():
            os.chmod(path, stat.S_IRUSR | stat.S_IRGRP)
        elif path.is_dir():
            os.chmod(path, stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP)
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
