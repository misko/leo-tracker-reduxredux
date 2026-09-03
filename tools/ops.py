#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import errno
import fcntl
import fnmatch
import grp
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "config/ops-components.json"
PROTECTED_DATABASES = frozenset({"leo_tracker", "postgres", "template0", "template1"})
RELEASE_ROOT = Path("/opt/leo-tracker")
PRODUCTION_ENVIRONMENT = Path("/etc/leo/leo.env")
PRODUCTION_ACQUISITION_ENVIRONMENT = Path("/etc/leo/acquisition.env")
PRODUCTION_WORKER_ENVIRONMENT = Path("/etc/leo/worker.env")
QUALIFICATION_DATABASE_LOCK = Path("/var/lib/leo/.cache/qualification-database.lock")
DEPLOYMENT_EVIDENCE_ROOT = Path("/srv/bulk/leo/qualification/deployment")
QNAP_ROOT = Path("/mnt/qnap01")
PRODUCTION_CAPTURE_POLICY = "production-direct-async-2p5-10-15-25-hold-exact-lo-6-v2"
DEFAULT_RELEASE_RETENTION = 10
MINIMUM_RELEASE_RETENTION = 2
FAST_DEPLOY_TARGET_SECONDS = 30.0

_FAST_DEPLOY_ALLOWED_PATTERNS = (
    "src/leo/api/**",
    "src/leo/application/**",
    "src/leo/presentation/**",
    "tests/api/**",
    "tests/application/**",
    "tests/presentation/**",
    "web/**",
    "docs/**",
    "reports/**",
    "*.md",
)
_FAST_DEPLOY_DENIED_PATTERNS = (
    "web/package.json",
    "web/package-lock.json",
)
_FAST_DEPLOY_RUNTIME_PATTERNS = (
    "src/leo/api/**",
    "src/leo/application/**",
    "src/leo/presentation/**",
    "web/**",
)

_REVISION_PATTERN = re.compile(r"[0-9a-f]{40}")

_SELECTOR_COMPONENTS = ("global", "api", "worker", "acquisition")
_WORKER_UNITS = tuple(f"leo-worker@{index}.service" for index in range(1, 21))
_WORKER_UNIT_PATTERN = "leo-worker@*.service"
_LEO_TIMER_UNITS = (
    "leo-persistent-hop-analysis.timer",
    "leo-qualification.timer",
    "leo-reconcile.timer",
    "leo-release-qualification.timer",
    "leo-retention.timer",
    "leo-tle-collection.timer",
)
_LEO_SERVICE_UNITS = (
    "leo-acquisition.service",
    "leo-acquisition-soak.service",
    "leo-api.service",
    "leo-persistent-hop-analysis.service",
    "leo-qualification.service",
    "leo-reconcile.service",
    "leo-release-qualification.service",
    "leo-retention.service",
    "leo-tle-collection.service",
)
_REVIEWED_CONTINUITY_ENVIRONMENT = {
    "LEO_CAPTURE_PROFILE": "starlink-ch4-lower-2p5m-60s-native-bandwidth-v4",
    "LEO_CAPTURE_PROFILE_5M": "starlink-ch4-lower-5m-60s-native-bandwidth-v4",
    "LEO_MIXED_RATE_POLICY": "production-direct-async-2p5-10-15-25-hold-exact-lo-6-v2",
    "LEO_DIRECT_ASYNC_ENABLED": "true",
    "LEO_CAPTURE_INTERVAL_SECONDS": "180",
    "LEO_QUALIFICATION_PROFILE": ("starlink-ch4-lower-2p5m-60s-rx1-centered-continuity-v2"),
    "LEO_SOAK_PROFILE": "starlink-ch4-lower-2p5m-60s-continuity-v2",
    "LEO_SCANNER_ENABLED": "false",
    "LEO_SCANNER_CAPTURE_MODE": "persistent_hop",
    "LEO_SCANNER_RADIO_ID": "radio_pluto_5d4d",
    "LEO_SCANNER_INTERVAL_SECONDS": "1200",
    "LEO_SCANNER_MAXIMUM_LATENESS_SECONDS": "300",
    "LEO_SCANNER_RUN_SECONDS": "300",
    "LEO_SCANNER_DWELL_MS": "120",
    "LEO_SCANNER_GAIN_DB": "40.0",
    "LEO_SCANNER_MARGIN_GATE": "0.025",
    "LEO_SCANNER_REPORT_ROOT": "/srv/bulk/leo/scanner-reports",
    "LEO_SCANNER_PERSISTENT_TRANSITION_GUARD_US": "1000",
    "LEO_SCANNER_PERSISTENT_SAMPLES_PER_BLOCK": "131072",
    "LEO_SCANNER_PERSISTENT_KERNEL_BUFFERS": "8",
    "LEO_SCANNER_PERSISTENT_READ_AHEAD_VISITS": "8",
    "LEO_SCANNER_PERSISTENT_QUEUE_CAPACITY_VISITS": "64",
    "LEO_SCANNER_PERSISTENT_IIOD_PORT": "30432",
}
_ADDITIVE_REVIEWED_ENVIRONMENT_KEYS = frozenset(
    {
        "LEO_CAPTURE_PROFILE_5M",
        "LEO_MIXED_RATE_POLICY",
        "LEO_DIRECT_ASYNC_ENABLED",
        "LEO_SCANNER_RUN_SECONDS",
        "LEO_SCANNER_CAPTURE_MODE",
        "LEO_SCANNER_PERSISTENT_TRANSITION_GUARD_US",
        "LEO_SCANNER_PERSISTENT_SAMPLES_PER_BLOCK",
        "LEO_SCANNER_PERSISTENT_KERNEL_BUFFERS",
        "LEO_SCANNER_PERSISTENT_READ_AHEAD_VISITS",
        "LEO_SCANNER_PERSISTENT_QUEUE_CAPACITY_VISITS",
        "LEO_SCANNER_PERSISTENT_IIOD_PORT",
    }
)

_CLI_NOT_FOUND_EXIT_CODE = 11

_DEFAULT_TEST_NODE_SHARDS = {
    "tests/processing/test_mixed_rate_standard_native_operational_vertical.py": tuple(
        "tests/processing/test_mixed_rate_standard_native_operational_vertical.py::"
        "test_real_postgres_direct_async_capture_analysis_png_and_browser_vertical"
        f"[{rate_hz}]"
        for rate_hz in (10_000_000, 15_000_000, 25_000_000)
    ),
}


class OpsError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Component:
    name: str
    patterns: tuple[str, ...]
    tests: tuple[str, ...]
    runtime_patterns: tuple[str, ...]
    impact: tuple[str, ...]
    postgres: bool = False
    web: bool = False
    exclusive: bool = False
    fallback: bool = False


@dataclass(frozen=True, slots=True)
class Gate:
    name: str
    command: tuple[str, ...]
    needs_postgres: bool = False


@dataclass(frozen=True, slots=True)
class ReleaseRecord:
    revision: str
    state: str
    release_path: Path | None
    metadata_path: Path
    archive_path: Path
    size_bytes: int
    published_mtime_ns: int
    metadata_sha256: str


def _run_git(*arguments: str) -> str:
    completed = subprocess.run(
        ("git", *arguments), cwd=ROOT, check=True, text=True, stdout=subprocess.PIPE
    )
    return completed.stdout.strip()


def load_components(path: Path = MANIFEST_PATH) -> tuple[Component, ...]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != 2:
        raise OpsError("unsupported component manifest schema")
    return tuple(
        Component(
            name=item["name"],
            patterns=tuple(item["patterns"]),
            tests=tuple(item.get("tests", ())),
            runtime_patterns=tuple(item.get("runtime_patterns", ())),
            impact=tuple(item.get("impact", ())),
            postgres=bool(item.get("postgres", False)),
            web=bool(item.get("web", False)),
            exclusive=bool(item.get("exclusive", False)),
            fallback=bool(item.get("fallback", False)),
        )
        for item in document["components"]
    )


def components_for_paths(
    paths: tuple[str, ...], components: tuple[Component, ...]
) -> tuple[Component, ...]:
    selected: dict[str, Component] = {}
    unclassified: list[str] = []
    for path in paths:
        matches = [
            component
            for component in components
            if any(fnmatch.fnmatchcase(path, pattern) for pattern in component.patterns)
        ]
        exclusive_matches = [component for component in matches if component.exclusive]
        if exclusive_matches:
            matches = exclusive_matches
        elif any(not component.fallback for component in matches):
            matches = [component for component in matches if not component.fallback]
        if not matches:
            unclassified.append(path)
        for component in matches:
            selected[component.name] = component
    if unclassified:
        raise OpsError("unclassified changed paths: " + ", ".join(sorted(unclassified)))
    return tuple(selected[name] for name in sorted(selected))


def runtime_impacts_for_paths(
    paths: tuple[str, ...], components: tuple[Component, ...]
) -> tuple[str, ...]:
    """Return runtime effects without treating test selection as deployment impact."""

    return tuple(
        sorted(
            {
                impact
                for component in components
                if any(
                    fnmatch.fnmatchcase(path, pattern)
                    for path in paths
                    for pattern in component.runtime_patterns
                )
                for impact in component.impact
            }
        )
    )


def changed_paths(*, all_paths: bool = False, base_revision: str | None = None) -> tuple[str, ...]:
    if all_paths:
        return tuple(line for line in _run_git("ls-files").splitlines() if line)
    head = _run_git("rev-parse", "HEAD")
    origin = _run_git("rev-parse", "origin/main")
    base = _run_git("merge-base", head, origin)
    paths = set(_git_lines("diff", "--name-only"))
    paths.update(_git_lines("diff", "--cached", "--name-only"))
    paths.update(_git_lines("ls-files", "--others", "--exclude-standard"))
    if base_revision is not None:
        if paths:
            raise OpsError("--base requires a clean worktree")
        comparison = _run_git("rev-parse", "--verify", f"{base_revision}^{{commit}}")
        paths.update(_git_lines("diff", "--name-only", f"{comparison}..{head}"))
    elif not paths:
        comparison = f"{head}^" if head == origin and _has_parent(head) else base
        paths.update(_git_lines("diff", "--name-only", f"{comparison}..{head}"))
    return tuple(sorted(path for path in paths if path))


def _has_parent(revision: str) -> bool:
    return (
        subprocess.run(
            ("git", "rev-parse", "--verify", f"{revision}^"),
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def _git_lines(*arguments: str) -> tuple[str, ...]:
    output = _run_git(*arguments)
    return tuple(output.splitlines()) if output else ()


def safe_child_environment(*, needs_postgres: bool) -> dict[str, str]:
    environment = dict(os.environ)
    environment.pop("LEO_DATABASE_URL", None)
    environment.pop("LEO_E2E_DATABASE_URL", None)
    if needs_postgres:
        raw_url = environment.get("LEO_TEST_DATABASE_URL")
        if not raw_url:
            raise OpsError(
                "selected PostgreSQL gates require explicit LEO_TEST_DATABASE_URL; "
                "production defaults are forbidden"
            )
        _validate_test_database_url(raw_url)
    else:
        environment.pop("LEO_TEST_DATABASE_URL", None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    cache_root = Path("/tmp") / f"leo-ops-cache-{os.getuid()}"
    cache_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    environment["MYPY_CACHE_DIR"] = str(cache_root / "mypy")
    environment["RUFF_CACHE_DIR"] = str(cache_root / "ruff")
    release_tools = Path("/opt/leo-tracker/current/.release-tools")
    try:
        resolved_release_tools = release_tools.resolve(strict=True)
        sealed_uv_available = (resolved_release_tools / "uv").is_file()
    except OSError:
        sealed_uv_available = False
    if sealed_uv_available:
        environment["PATH"] = f"{resolved_release_tools}:{environment.get('PATH', '')}"
    return environment


def _validate_test_database_url(raw_url: str) -> None:
    parsed = urlparse(raw_url.replace("postgresql+psycopg", "postgresql", 1))
    database = parsed.path.lstrip("/").casefold()
    if parsed.scheme != "postgresql" or not database:
        raise OpsError("LEO_TEST_DATABASE_URL must be an explicit PostgreSQL database URL")
    if database in PROTECTED_DATABASES:
        raise OpsError(f"refusing protected test database {database!r}")
    if "qualification" not in database and not database.endswith("_test"):
        raise OpsError(f"test database {database!r} must contain 'qualification' or end in '_test'")


def selected_gates(
    paths: tuple[str, ...],
    components: tuple[Component, ...],
    *,
    all_tests: bool,
    release: bool,
    fast: bool = False,
) -> tuple[Gate, ...]:
    # Deleted Python paths still select their owning component and deployment
    # impact, but file-oriented formatters cannot be invoked on an absent path.
    python_paths = tuple(path for path in paths if path.endswith(".py") and (ROOT / path).is_file())
    source_changed = any(path.startswith("src/") for path in python_paths)
    gates: list[Gate] = []
    if python_paths:
        gates.extend(
            (
                Gate(
                    "ruff-check",
                    _python_tool("ruff", "check", "--force-exclude", *python_paths),
                ),
                Gate(
                    "ruff-format",
                    _python_tool("ruff", "format", "--check", "--force-exclude", *python_paths),
                ),
            )
        )
    if source_changed or all_tests:
        mypy_targets = tuple(path for path in python_paths if path.startswith("src/"))
        gates.append(
            Gate(
                "mypy",
                _python_tool("mypy", *(mypy_targets if fast else ("src",))),
            )
        )
    changed_test_paths = sorted(
        path
        for path in paths
        if path.startswith("tests/")
        and Path(path).name.startswith("test_")
        and path.endswith(".py")
        and not path.endswith("/conftest.py")
        and (ROOT / path).is_file()
    )
    if all_tests:
        assigned: set[str] = set()
        for component in components:
            declared_paths = tuple(
                path for path in component.tests if path not in assigned and (ROOT / path).exists()
            )
            assigned.update(declared_paths)
            component_paths = tuple(
                expanded for path in declared_paths for expanded in _expand_test_shard(path)
            )
            for index, path in enumerate(component_paths, start=1):
                expression = "not real_corpus and not legacy_oracle"
                if not component.postgres:
                    expression += " and not postgres"
                gates.append(
                    Gate(
                        f"pytest-{component.name}-{index}",
                        _python_tool(
                            "pytest",
                            "-q",
                            "-p",
                            "no:cacheprovider",
                            "-m",
                            expression,
                            path,
                        ),
                        needs_postgres=component.postgres,
                    )
                )
        test_paths: list[str] = []
    elif changed_test_paths:
        # Component changes are required to carry component-owned tests. Running the
        # exact changed tests avoids recursively selecting a multi-minute directory.
        requested_test_paths = (
            changed_test_paths
            if fast
            else sorted(
                set(changed_test_paths).union(
                    path
                    for component in components
                    if component.exclusive
                    for path in component.tests
                )
            )
        )
        test_paths = sorted(
            {shard for path in requested_test_paths for shard in _expand_test_shard(path)}
        )
        for index, path in enumerate(test_paths, start=1):
            owners = tuple(
                component
                for component in components
                if any(fnmatch.fnmatchcase(path, pattern) for pattern in component.patterns)
            )
            exclusive_owners = tuple(component for component in owners if component.exclusive)
            effective_owners = exclusive_owners or owners
            needs_postgres = any(component.postgres for component in effective_owners)
            if fast and needs_postgres:
                continue
            expression = "not real_corpus and not legacy_oracle"
            if not needs_postgres:
                expression += " and not postgres"
            gates.append(
                Gate(
                    f"pytest-changed-{index}",
                    _python_tool(
                        "pytest",
                        "-q",
                        "-p",
                        "no:cacheprovider",
                        "-m",
                        expression,
                        path,
                    ),
                    needs_postgres=needs_postgres,
                )
            )
        test_paths = []
    elif fast:
        test_paths = []
    elif any(component.exclusive for component in components):
        test_paths = sorted(
            path for component in components if component.exclusive for path in component.tests
        )
    else:
        test_paths = sorted({path for component in components for path in component.tests})
    if test_paths:
        expanded_test_paths = tuple(
            sorted({shard for path in test_paths for shard in _expand_test_shard(path)})
        )
        for index, path in enumerate(expanded_test_paths, start=1):
            owners = tuple(
                component
                for component in components
                if any(fnmatch.fnmatchcase(path, pattern) for pattern in component.patterns)
            )
            needs_postgres = any(component.postgres for component in owners)
            expression = "not real_corpus and not legacy_oracle"
            if not needs_postgres:
                expression += " and not postgres"
            gates.append(
                Gate(
                    f"pytest-components-{index}",
                    _python_tool(
                        "pytest",
                        "-q",
                        "-p",
                        "no:cacheprovider",
                        "-m",
                        expression,
                        path,
                    ),
                    needs_postgres=needs_postgres,
                )
            )
    if any(component.web for component in components) or all_tests:
        npm = shutil.which("npm") or "/usr/bin/npm"
        gates.extend(
            (
                Gate("web-test", (npm, "test", "--", "--run")),
                Gate("web-build", (npm, "run", "build")),
            )
        )
    if release:
        gates.append(
            Gate(
                "release-instructions",
                _python_tool("pytest", "-q", "tests/qualification/test_release_qualification.py"),
            )
        )
    unique: dict[str, Gate] = {gate.name: gate for gate in gates}
    return tuple(unique[name] for name in sorted(unique))


def _expand_test_shard(path: str) -> tuple[str, ...]:
    if path in _DEFAULT_TEST_NODE_SHARDS:
        return _DEFAULT_TEST_NODE_SHARDS[path]
    location = ROOT / path
    if not location.is_dir():
        return (path,)
    files = (
        item.relative_to(ROOT).as_posix()
        for item in sorted(location.glob("test_*.py"))
        if item.is_file()
    )
    expanded = tuple(shard for item in files for shard in _expand_test_shard(item))
    return expanded or (path,)


def _python_tool(name: str, *arguments: str) -> tuple[str, ...]:
    executable = ROOT / ".venv/bin" / name
    if executable.is_file() and os.access(executable, os.X_OK):
        return (str(executable), *arguments)
    uv = shutil.which("uv")
    if uv is None:
        raise OpsError(f"{name} is unavailable; create .venv or install uv")
    return (uv, "run", name, *arguments)


def _execute_gate(gate: Gate) -> dict[str, Any]:
    started = time.monotonic()
    cwd = ROOT / "web" if gate.name.startswith("web-") else ROOT
    try:
        environment = safe_child_environment(needs_postgres=gate.needs_postgres)
        command = gate.command
        if gate.needs_postgres and _local_service_test_delegation_available(environment):
            leo_uid = _service_account_uid()
            cache_root = f"/tmp/leo-ops-cache-{leo_uid}"
            command = (
                "/usr/bin/sudo",
                "-n",
                "-u",
                "leo",
                "/usr/bin/flock",
                "--shared",
                str(QUALIFICATION_DATABASE_LOCK),
                "/usr/bin/env",
                "HOME=/var/lib/leo",
                f"LEO_TEST_DATABASE_URL={environment['LEO_TEST_DATABASE_URL']}",
                "PYTHONDONTWRITEBYTECODE=1",
                f"MYPY_CACHE_DIR={cache_root}/mypy",
                f"RUFF_CACHE_DIR={cache_root}/ruff",
                *gate.command,
            )
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        output = completed.stdout
        exit_code = completed.returncode
        if exit_code == 5 and ("deselected" in output or "collected 0 items" in output):
            exit_code = 0
    except OSError as error:
        output = f"unable to execute gate: {error}\n"
        exit_code = 127
    return {
        "name": gate.name,
        "command": list(gate.command),
        "duration_seconds": round(time.monotonic() - started, 6),
        "exit_code": exit_code,
        "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
        "output": output,
    }


def _local_service_test_delegation_available(environment: dict[str, str]) -> bool:
    if os.geteuid() == 0 or os.environ.get("USER") == "leo":
        return False
    parsed = urlparse(
        environment["LEO_TEST_DATABASE_URL"].replace("postgresql+psycopg", "postgresql", 1)
    )
    return (
        not parsed.hostname
        and parsed.path.lstrip("/") == "leo_qualification"
        and Path("/usr/bin/sudo").is_file()
        and subprocess.run(
            ("/usr/bin/sudo", "-n", "-u", "leo", "/usr/bin/true"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def _service_account_uid() -> int:
    import pwd

    return pwd.getpwnam("leo").pw_uid


def overlay_digest(paths: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    digest.update(_run_git("rev-parse", "HEAD").encode())
    for path_text in paths:
        digest.update(b"\0")
        digest.update(path_text.encode())
        path = ROOT / path_text
        if path.is_file():
            digest.update(path.read_bytes())
        else:
            digest.update(b"<deleted>")
    return digest.hexdigest()


def _test(args: argparse.Namespace) -> int:
    if args.fast and (args.all or args.release):
        raise OpsError("--fast cannot be combined with --all or --release")
    components = load_components()
    paths = changed_paths(
        all_paths=args.all or args.release,
        base_revision=args.base,
    )
    selected = components_for_paths(paths, components)
    gates = selected_gates(
        paths,
        selected,
        all_tests=args.all or args.release,
        release=args.release,
        fast=args.fast,
    )
    plan = {
        "tier": "fast-iteration" if args.fast else "deployment",
        "paths": list(paths),
        "components": [component.name for component in selected],
        "gates": [
            {"name": gate.name, "command": list(gate.command), "postgres": gate.needs_postgres}
            for gate in gates
        ],
    }
    if args.explain:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    if not gates:
        print("No executable gates selected; classified documentation/metadata-only change.")
        return 0
    _prepare_web_dependencies(gates)
    started = time.monotonic()
    postgres_gates = tuple(gate for gate in gates if gate.needs_postgres)
    portable_gates = tuple(gate for gate in gates if not gate.needs_postgres)
    with (
        concurrent.futures.ThreadPoolExecutor(
            max_workers=min(8, len(portable_gates)) or 1
        ) as portable_executor,
        concurrent.futures.ThreadPoolExecutor(
            max_workers=min(4, len(postgres_gates)) or 1
        ) as postgres_executor,
    ):
        futures = {
            gate.name: (postgres_executor if gate.needs_postgres else portable_executor).submit(
                _execute_gate, gate
            )
            for gate in gates
        }
        results = [futures[gate.name].result() for gate in gates]
    for result in results:
        status = "PASS" if result["exit_code"] == 0 else "FAIL"
        print(f"[{status}] {result['name']} {result['duration_seconds']:.2f}s")
        if result["exit_code"] != 0:
            print(result["output"], end="" if result["output"].endswith("\n") else "\n")
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "kind": "leo-test-receipt",
        "revision": _run_git("rev-parse", "HEAD"),
        "overlay_digest": overlay_digest(paths),
        "manifest_sha256": hashlib.sha256(MANIFEST_PATH.read_bytes()).hexdigest(),
        "duration_seconds": round(time.monotonic() - started, 6),
        "passed": all(result["exit_code"] == 0 for result in results),
        "plan": plan,
        "results": [
            {key: value for key, value in item.items() if key != "output"} for item in results
        ],
    }
    receipt_path = (
        Path(args.json)
        if args.json
        else ROOT / ".leo/test-receipts" / (str(receipt["overlay_digest"]) + ".json")
    )
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"receipt: {receipt_path}")
    return 0 if receipt["passed"] else 1


def _prepare_web_dependencies(gates: tuple[Gate, ...]) -> None:
    if not any(gate.name.startswith("web-") for gate in gates):
        return
    if (ROOT / "web/node_modules/.bin/vitest").is_file():
        return
    npm = shutil.which("npm") or "/usr/bin/npm"
    subprocess.run(
        (npm, "ci", "--no-audit", "--no-fund"),
        cwd=ROOT / "web",
        env=safe_child_environment(needs_postgres=False),
        check=True,
    )


def _is_revision(value: str) -> bool:
    return _REVISION_PATTERN.fullmatch(value) is not None


def _assert_not_qnap(path: Path) -> None:
    if not path.is_absolute():
        raise OpsError(f"release-retention path must be absolute: {path}")
    if path == QNAP_ROOT or QNAP_ROOT in path.parents:
        raise OpsError(f"QNAP cannot be a release-retention path: {path}")


def _validate_owned_directory(
    path: Path,
    *,
    expected_uid: int,
    expected_gid: int,
) -> os.stat_result:
    _assert_not_qnap(path)
    try:
        info = path.lstat()
    except FileNotFoundError as error:
        raise OpsError(f"required release-retention directory is absent: {path}") from error
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise OpsError(f"release-retention directory must not be a symlink: {path}")
    if info.st_uid != expected_uid or info.st_gid != expected_gid:
        raise OpsError(f"release-retention directory has unexpected ownership: {path}")
    if stat.S_IMODE(info.st_mode) & 0o022:
        raise OpsError(f"release-retention directory is group/world writable: {path}")
    return info


def _validate_release_metadata(
    path: Path,
    *,
    expected_uid: int,
    expected_gid: int,
) -> tuple[os.stat_result, str]:
    _assert_not_qnap(path)
    try:
        info = path.lstat()
    except FileNotFoundError as error:
        raise OpsError(f"release metadata is absent: {path}") from error
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise OpsError(f"release metadata must be a regular non-symlink file: {path}")
    if info.st_uid != expected_uid or info.st_gid != expected_gid:
        raise OpsError(f"release metadata has unexpected ownership: {path}")
    if stat.S_IMODE(info.st_mode) != 0o440:
        raise OpsError(f"release metadata mode must be 0440: {path}")
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise OpsError(f"release metadata is unreadable: {path}") from error
    return info, digest


def _release_size_bytes(path: Path) -> int:
    completed = subprocess.run(
        ("/usr/bin/du", "-x", "-s", "-B1", "--", str(path)),
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    try:
        size = int(completed.stdout.split(maxsplit=1)[0])
    except (IndexError, ValueError) as error:
        raise OpsError(f"cannot parse release size for {path}") from error
    if size < 0:
        raise OpsError(f"release size is negative for {path}")
    return size


def _release_inventory(
    *,
    release_root: Path = RELEASE_ROOT,
    expected_uid: int = 0,
    expected_gid: int | None = None,
) -> tuple[tuple[ReleaseRecord, ...], int]:
    group_id = grp.getgrnam("leo").gr_gid if expected_gid is None else expected_gid
    _validate_owned_directory(
        release_root,
        expected_uid=expected_uid,
        expected_gid=group_id,
    )
    releases_root = release_root / "releases"
    metadata_root = release_root / "release-metadata"
    history_root = release_root / "retired-release-metadata"
    releases_info = _validate_owned_directory(
        releases_root,
        expected_uid=expected_uid,
        expected_gid=group_id,
    )
    _validate_owned_directory(
        metadata_root,
        expected_uid=expected_uid,
        expected_gid=group_id,
    )

    release_paths: dict[str, Path] = {}
    for path in releases_root.iterdir():
        if not _is_revision(path.name):
            raise OpsError(f"noncanonical entry exists in release inventory: {path}")
        info = _validate_owned_directory(
            path,
            expected_uid=expected_uid,
            expected_gid=group_id,
        )
        if info.st_dev != releases_info.st_dev:
            raise OpsError(f"release directory is a separate mount: {path}")
        release_paths[path.name] = path

    metadata_paths: dict[str, Path] = {}
    metadata_details: dict[str, tuple[os.stat_result, str]] = {}
    for path in metadata_root.iterdir():
        revision = path.name.removesuffix(".txt")
        if path.name != f"{revision}.txt" or not _is_revision(revision):
            raise OpsError(f"noncanonical entry exists in release metadata: {path}")
        metadata_paths[revision] = path
        metadata_details[revision] = _validate_release_metadata(
            path,
            expected_uid=expected_uid,
            expected_gid=group_id,
        )

    archived: dict[str, tuple[Path, str]] = {}
    if history_root.exists() or history_root.is_symlink():
        history_info = _validate_owned_directory(
            history_root,
            expected_uid=expected_uid,
            expected_gid=group_id,
        )
        if history_info.st_dev != releases_info.st_dev:
            raise OpsError("retired release metadata must share the release filesystem")
        for path in history_root.iterdir():
            revision = path.name.removesuffix(".txt")
            if path.name != f"{revision}.txt" or not _is_revision(revision):
                raise OpsError(f"noncanonical retired release metadata exists: {path}")
            _info, digest = _validate_release_metadata(
                path,
                expected_uid=expected_uid,
                expected_gid=group_id,
            )
            archived[revision] = (path, digest)

    records: list[ReleaseRecord] = []
    for revision in sorted(set(release_paths) | set(metadata_paths)):
        release_path = release_paths.get(revision)
        metadata_path = metadata_paths.get(revision)
        archive = archived.get(revision)
        if release_path is not None and metadata_path is None:
            raise OpsError(f"published release has no canonical metadata: {release_path}")
        if metadata_path is None:
            raise AssertionError("metadata path was unexpectedly absent")
        metadata_info, metadata_digest = metadata_details[revision]
        if archive is not None and archive[1] != metadata_digest:
            raise OpsError(f"retired and canonical metadata disagree for release {revision}")
        if release_path is None:
            if archive is None:
                raise OpsError(
                    f"canonical metadata has no release or retirement archive: {metadata_path}"
                )
            state = "retirement-metadata-pending"
            size_bytes = 0
        else:
            state = "retirement-started" if archive is not None else "published"
            size_bytes = _release_size_bytes(release_path)
        records.append(
            ReleaseRecord(
                revision=revision,
                state=state,
                release_path=release_path,
                metadata_path=metadata_path,
                archive_path=(
                    archive[0] if archive is not None else history_root / f"{revision}.txt"
                ),
                size_bytes=size_bytes,
                published_mtime_ns=metadata_info.st_mtime_ns,
                metadata_sha256=metadata_digest,
            )
        )
    return tuple(records), len(archived)


def _release_revisions_in_text(text: str, *, release_root: Path) -> set[str]:
    prefix = re.escape(str(release_root / "releases") + os.sep)
    return set(re.findall(prefix + r"([0-9a-f]{40})(?=/|\s|\x00|$)", text))


def _runtime_release_references(
    *,
    release_root: Path = RELEASE_ROOT,
    proc_root: Path = Path("/proc"),
) -> set[str]:
    references: set[str] = set()
    try:
        processes = tuple(path for path in proc_root.iterdir() if path.name.isdigit())
    except OSError as error:
        raise OpsError(f"cannot enumerate process references beneath {proc_root}") from error

    def vanished(error: OSError) -> bool:
        return error.errno in {errno.ENOENT, errno.ESRCH}

    for process in processes:
        for name in ("exe", "cwd"):
            try:
                target = os.readlink(process / name)
            except OSError as error:
                if vanished(error):
                    continue
                raise OpsError(f"cannot inspect runtime reference {process / name}") from error
            references.update(_release_revisions_in_text(target, release_root=release_root))
        file_descriptors = process / "fd"
        try:
            descriptors = tuple(file_descriptors.iterdir())
        except OSError as error:
            if vanished(error):
                descriptors = ()
            else:
                raise OpsError(f"cannot inspect runtime file descriptors for {process}") from error
        for descriptor in descriptors:
            try:
                target = os.readlink(descriptor)
            except OSError as error:
                if vanished(error):
                    continue
                raise OpsError(f"cannot inspect runtime file descriptor {descriptor}") from error
            references.update(_release_revisions_in_text(target, release_root=release_root))
        for name in ("cmdline", "maps"):
            try:
                content = (process / name).read_bytes().decode(errors="replace")
            except OSError as error:
                if vanished(error):
                    continue
                raise OpsError(f"cannot inspect runtime process data {process / name}") from error
            references.update(_release_revisions_in_text(content, release_root=release_root))
    return references


def _previous_deployment_revisions(
    *,
    selected_revisions: set[str],
    evidence_root: Path = DEPLOYMENT_EVIDENCE_ROOT,
) -> tuple[set[str], set[str]]:
    previous: set[str] = set()
    unresolved = set(selected_revisions)
    if not evidence_root.is_dir() or evidence_root.is_symlink():
        return previous, unresolved
    for path in sorted(
        evidence_root.glob("deploy-*.json"), key=lambda item: item.name, reverse=True
    ):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        target = document.get("target_revision")
        prior = document.get("previous_revision")
        if (
            target in unresolved
            and document.get("kind") == "leo-deployment-receipt"
            and document.get("healthy") is True
            and isinstance(prior, str)
            and _is_revision(prior)
            and prior != target
        ):
            previous.add(prior)
            unresolved.remove(str(target))
        if not unresolved:
            break
    return previous, unresolved


def _release_plan_digest(document: dict[str, Any]) -> str:
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def _release_retention_plan(
    *,
    keep: int,
    explicitly_protected: tuple[str, ...] = (),
    release_root: Path = RELEASE_ROOT,
    evidence_root: Path = DEPLOYMENT_EVIDENCE_ROOT,
    proc_root: Path = Path("/proc"),
    expected_uid: int = 0,
    expected_gid: int | None = None,
) -> dict[str, Any]:
    if keep < MINIMUM_RELEASE_RETENTION:
        raise OpsError(f"release retention must keep at least {MINIMUM_RELEASE_RETENTION} releases")
    invalid_protections = tuple(
        revision for revision in explicitly_protected if not _is_revision(revision)
    )
    if invalid_protections:
        raise OpsError("invalid explicitly protected release: " + ", ".join(invalid_protections))
    records, retired_metadata_count = _release_inventory(
        release_root=release_root,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    by_revision = {record.revision: record for record in records}
    selectors = _selected_selector_revisions(release_root=release_root)
    selected_revisions = set(selectors.values())
    unavailable_selectors = tuple(
        sorted(
            revision
            for revision in selected_revisions
            if revision not in by_revision or by_revision[revision].release_path is None
        )
    )
    if unavailable_selectors:
        raise OpsError(
            "selected releases are absent from the published inventory: "
            + ", ".join(unavailable_selectors)
        )
    runtime_revisions = _runtime_release_references(
        release_root=release_root,
        proc_root=proc_root,
    )
    unknown_runtime = tuple(sorted(runtime_revisions - set(by_revision)))
    if unknown_runtime:
        raise OpsError(
            "running processes reference releases outside the published inventory: "
            + ", ".join(unknown_runtime)
        )
    missing_explicit = tuple(sorted(set(explicitly_protected) - set(by_revision)))
    if missing_explicit:
        raise OpsError("explicitly protected releases are absent: " + ", ".join(missing_explicit))

    previous_revisions, unresolved_history = _previous_deployment_revisions(
        selected_revisions=selected_revisions,
        evidence_root=evidence_root,
    )
    unavailable_previous = tuple(sorted(previous_revisions - set(by_revision)))
    history_complete = not unresolved_history and not unavailable_previous
    newest = tuple(
        record.revision
        for record in sorted(
            (record for record in records if record.state == "published"),
            key=lambda record: (record.published_mtime_ns, record.revision),
            reverse=True,
        )[:keep]
    )
    reasons: dict[str, set[str]] = {revision: set() for revision in by_revision}
    for component, revision in selectors.items():
        reasons[revision].add(f"selector:{component}")
    for revision in runtime_revisions:
        reasons[revision].add("runtime")
    for revision in previous_revisions & set(by_revision):
        reasons[revision].add("previous-deployment")
    for revision in explicitly_protected:
        reasons[revision].add("operator")
    for revision in newest:
        reasons[revision].add("retention-window")

    inventory: list[dict[str, Any]] = []
    for record in sorted(
        records,
        key=lambda item: (item.published_mtime_ns, item.revision),
        reverse=True,
    ):
        protection = sorted(reasons[record.revision])
        inventory.append(
            {
                "revision": record.revision,
                "state": record.state,
                "size_bytes": record.size_bytes,
                "published_mtime_ns": record.published_mtime_ns,
                "metadata_sha256": record.metadata_sha256,
                "archive_path": str(record.archive_path),
                "protected_reasons": protection,
                "action": "keep" if protection else "retire",
            }
        )
    candidates = [item for item in inventory if item["action"] == "retire"]
    warnings: list[str] = []
    if unresolved_history:
        warnings.append(
            "no healthy deployment receipt resolves previous releases for: "
            + ", ".join(sorted(unresolved_history))
        )
    if unavailable_previous:
        warnings.append(
            "deployment receipts reference unavailable previous releases: "
            + ", ".join(unavailable_previous)
        )
    document: dict[str, Any] = {
        "schema_version": 1,
        "kind": "leo-release-retention-plan",
        "release_root": str(release_root),
        "keep": keep,
        "explicitly_protected": sorted(set(explicitly_protected)),
        "selectors": selectors,
        "runtime_revisions": sorted(runtime_revisions),
        "previous_revisions": sorted(previous_revisions & set(by_revision)),
        "history_complete": history_complete,
        "retired_metadata_count": retired_metadata_count,
        "inventory_count": len(inventory),
        "inventory_bytes": sum(int(item["size_bytes"]) for item in inventory),
        "candidate_count": len(candidates),
        "candidate_bytes": sum(int(item["size_bytes"]) for item in candidates),
        "warnings": warnings,
        "inventory": inventory,
    }
    document["plan_sha256"] = _release_plan_digest(document)
    return document


def _ensure_retired_metadata_root(
    *,
    release_root: Path,
    expected_uid: int,
    expected_gid: int,
) -> Path:
    path = release_root / "retired-release-metadata"
    releases_info = _validate_owned_directory(
        release_root / "releases",
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    if not path.exists() and not path.is_symlink():
        path.mkdir(mode=0o750)
        os.chown(path, expected_uid, expected_gid)
        os.chmod(path, 0o750)
    info = _validate_owned_directory(
        path,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    if info.st_dev != releases_info.st_dev:
        raise OpsError("retired release metadata must share the release filesystem")
    return path


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _archive_release_metadata(
    *,
    revision: str,
    metadata: Path,
    expected_digest: str,
    release_root: Path,
    expected_uid: int,
    expected_gid: int,
) -> Path:
    _info, observed_digest = _validate_release_metadata(
        metadata,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    if observed_digest != expected_digest:
        raise OpsError(f"release metadata changed after planning: {revision}")
    history_root = _ensure_retired_metadata_root(
        release_root=release_root,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    archive = history_root / f"{revision}.txt"
    if archive.exists() or archive.is_symlink():
        _archive_info, archive_digest = _validate_release_metadata(
            archive,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
        )
        if archive_digest != expected_digest:
            raise OpsError(f"retired release metadata conflicts for {revision}")
        return archive
    content = metadata.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected_digest:
        raise OpsError(f"release metadata changed while archiving: {revision}")
    temporary = history_root / f".{revision}.{os.getpid()}.tmp"
    try:
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chown(temporary, expected_uid, expected_gid)
        os.chmod(temporary, 0o440)
        os.replace(temporary, archive)
        _fsync_directory(history_root)
    finally:
        temporary.unlink(missing_ok=True)
    return archive


def _remove_release_tree(
    *,
    release: Path,
    release_root: Path,
    expected_uid: int,
    expected_gid: int,
) -> None:
    releases_root = release_root / "releases"
    if release.parent != releases_root or not _is_revision(release.name):
        raise OpsError(f"release cleanup target is not one exact canonical SHA: {release}")
    releases_info = _validate_owned_directory(
        releases_root,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    release_info = _validate_owned_directory(
        release,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    if release_info.st_dev != releases_info.st_dev:
        raise OpsError(f"release cleanup target is a separate mount: {release}")
    subprocess.run(
        ("/usr/bin/rm", "-rf", "--one-file-system", "--", str(release)),
        check=True,
    )
    if release.exists() or release.is_symlink():
        raise OpsError(f"release cleanup did not remove its exact target: {release}")
    _fsync_directory(releases_root)


def _retire_release(
    item: dict[str, Any],
    *,
    release_root: Path,
    expected_uid: int,
    expected_gid: int,
) -> Path:
    revision = str(item["revision"])
    if not _is_revision(revision) or item.get("action") != "retire":
        raise OpsError("retirement item is not an exact planned release candidate")
    metadata = release_root / "release-metadata" / f"{revision}.txt"
    archive = _archive_release_metadata(
        revision=revision,
        metadata=metadata,
        expected_digest=str(item["metadata_sha256"]),
        release_root=release_root,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    release = release_root / "releases" / revision
    if release.exists() or release.is_symlink():
        _remove_release_tree(
            release=release,
            release_root=release_root,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
        )
    _info, observed_digest = _validate_release_metadata(
        metadata,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    if observed_digest != item["metadata_sha256"]:
        raise OpsError(f"release metadata changed before canonical retirement: {revision}")
    metadata.unlink()
    _fsync_directory(metadata.parent)
    return archive


def _write_release_retention_evidence(
    *,
    evidence_root: Path,
    name: str,
    document: dict[str, Any],
    expected_uid: int,
    expected_gid: int,
) -> Path:
    _assert_not_qnap(evidence_root)
    try:
        root_info = evidence_root.lstat()
    except FileNotFoundError as error:
        raise OpsError(f"deployment evidence root is unavailable: {evidence_root}") from error
    if not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode):
        raise OpsError("deployment evidence root must be a real directory")
    if stat.S_IMODE(root_info.st_mode) & 0o022:
        raise OpsError("deployment evidence root must not be group/world writable")
    destination = evidence_root / name
    content = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    if destination.exists() or destination.is_symlink():
        _info, _digest = _validate_release_metadata(
            destination,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
        )
        if destination.read_bytes() != content:
            raise OpsError(
                f"release-retention evidence already exists with other content: {destination}"
            )
        return destination
    temporary = evidence_root / f".{name}.{os.getpid()}.tmp"
    try:
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chown(temporary, expected_uid, expected_gid)
        os.chmod(temporary, 0o440)
        os.replace(temporary, destination)
        _fsync_directory(evidence_root)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def _apply_release_retention(
    *,
    expected_plan: str,
    keep: int,
    explicitly_protected: tuple[str, ...] = (),
    release_root: Path = RELEASE_ROOT,
    evidence_root: Path = DEPLOYMENT_EVIDENCE_ROOT,
    proc_root: Path = Path("/proc"),
    expected_uid: int = 0,
    expected_gid: int | None = None,
    operator: str | None = None,
) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_plan):
        raise OpsError("--expect-plan must be one lowercase SHA-256 digest")
    group_id = grp.getgrnam("leo").gr_gid if expected_gid is None else expected_gid
    lock_path = release_root / ".ops-deploy.lock"
    if lock_path.is_symlink():
        raise OpsError("deployment lock must not be a symlink")
    lock_path.touch(mode=0o600, exist_ok=True)
    lock_info = lock_path.lstat()
    if (
        not stat.S_ISREG(lock_info.st_mode)
        or lock_info.st_uid != expected_uid
        or stat.S_IMODE(lock_info.st_mode) & 0o077
    ):
        raise OpsError("deployment lock must be an owner-only regular file")
    with lock_path.open("r+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise OpsError(
                "another deployment or release-retention operation holds the host lock"
            ) from error
        plan = _release_retention_plan(
            keep=keep,
            explicitly_protected=explicitly_protected,
            release_root=release_root,
            evidence_root=evidence_root,
            proc_root=proc_root,
            expected_uid=expected_uid,
            expected_gid=group_id,
        )
        if plan["plan_sha256"] != expected_plan:
            raise OpsError(
                "release-retention plan changed; review a new --plan before applying "
                f"(observed {plan['plan_sha256']})"
            )
        if not plan["history_complete"]:
            raise OpsError("release-retention history is incomplete; resolve plan warnings first")
        plan_receipt = _write_release_retention_evidence(
            evidence_root=evidence_root,
            name=f"release-retention-plan-{expected_plan}.json",
            document=plan,
            expected_uid=expected_uid,
            expected_gid=group_id,
        )
        candidates = [item for item in plan["inventory"] if item["action"] == "retire"]
        retired: list[dict[str, Any]] = []
        for item in reversed(candidates):
            revision = str(item["revision"])
            selectors = _selected_selector_revisions(release_root=release_root)
            if revision in selectors.values():
                raise OpsError(f"release became selected during retirement: {revision}")
            runtime = _runtime_release_references(
                release_root=release_root,
                proc_root=proc_root,
            )
            if revision in runtime:
                raise OpsError(f"release became runtime-referenced during retirement: {revision}")
            archive = _retire_release(
                item,
                release_root=release_root,
                expected_uid=expected_uid,
                expected_gid=group_id,
            )
            retired.append(
                {
                    "revision": revision,
                    "size_bytes": item["size_bytes"],
                    "metadata_sha256": item["metadata_sha256"],
                    "archive_path": str(archive),
                }
            )
        completion: dict[str, Any] = {
            "schema_version": 1,
            "kind": "leo-release-retention-receipt",
            "plan_sha256": expected_plan,
            "plan_receipt": str(plan_receipt),
            "applied_utc": datetime.now(UTC).isoformat(),
            "operator": operator
            or os.environ.get("SUDO_USER")
            or os.environ.get("USER")
            or str(os.getuid()),
            "retired_count": len(retired),
            "retired_bytes": sum(int(item["size_bytes"]) for item in retired),
            "retired": retired,
        }
        completion_path = _write_release_retention_evidence(
            evidence_root=evidence_root,
            name=f"release-retention-complete-{expected_plan}.json",
            document=completion,
            expected_uid=expected_uid,
            expected_gid=group_id,
        )
        completion["receipt"] = str(completion_path)
        return completion


def _releases(args: argparse.Namespace) -> int:
    if os.geteuid() != 0:
        raise OpsError("complete release inventory requires root; rerun with sudo")
    protections = tuple(args.protect or ())
    if args.apply:
        if args.expect_plan is None:
            raise OpsError("--apply requires --expect-plan from a reviewed plan")
        completion = _apply_release_retention(
            expected_plan=args.expect_plan,
            keep=args.keep,
            explicitly_protected=protections,
        )
        print(json.dumps(completion, indent=2, sort_keys=True))
        return 0
    if args.expect_plan is not None:
        raise OpsError("--expect-plan is valid only with --apply")
    plan = _release_retention_plan(
        keep=args.keep,
        explicitly_protected=protections,
    )
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


def _warn_release_pressure(*, release_root: Path = RELEASE_ROOT) -> None:
    try:
        releases = tuple(
            path
            for path in (release_root / "releases").iterdir()
            if _is_revision(path.name) and path.is_dir() and not path.is_symlink()
        )
    except OSError:
        return
    if len(releases) > DEFAULT_RELEASE_RETENTION:
        print(
            "RELEASE-RETENTION "
            f"inventory={len(releases)} keep={DEFAULT_RELEASE_RETENTION} "
            "review='sudo ./ops releases --plan --keep 10'",
            file=sys.stderr,
        )


def _deployment_plan(args: argparse.Namespace) -> dict[str, Any]:
    stage_only = bool(getattr(args, "stage_only", False))
    fast = bool(getattr(args, "fast", False))
    if stage_only and args.revision is None:
        raise OpsError("--stage-only requires an explicit --revision FULL_SHA")
    if stage_only and args.plan:
        raise OpsError("--stage-only cannot be combined with --plan")
    if stage_only and args.full:
        raise OpsError("--stage-only cannot be combined with --full")
    if stage_only and fast:
        raise OpsError("--stage-only cannot be combined with --fast")
    if args.full and fast:
        raise OpsError("--full cannot be combined with --fast")
    if _run_git("status", "--porcelain"):
        raise OpsError("deployment planning requires a clean worktree")
    target = args.revision or _run_git("rev-parse", "origin/main")
    if len(target) != 40 or any(character not in "0123456789abcdef" for character in target):
        raise OpsError("deployment revision must be one full lowercase Git SHA")
    origin = _run_git("rev-parse", "origin/main")
    local_head = _run_git("rev-parse", "HEAD") if stage_only and target != origin else None
    if target != origin and target != local_head:
        raise OpsError(
            "deployment target must equal the locally fetched origin/main; "
            "stage-only may instead use the clean local HEAD"
        )
    current = _selected_release_revision()
    current_api = _selected_component_release_revision("api") if fast else None
    comparison = current_api if fast and current_api is not None else current
    paths = (
        tuple(_git_lines("diff", "--name-only", f"{comparison}..{target}")) if comparison else ()
    )
    components = components_for_paths(paths, load_components())
    impact = list(runtime_impacts_for_paths(paths, components))
    rejected_fast_paths = _fast_deploy_rejected_paths(paths) if fast else ()
    fast_runtime_change = any(
        any(fnmatch.fnmatchcase(path, pattern) for pattern in _FAST_DEPLOY_RUNTIME_PATTERNS)
        for path in paths
    )
    fast_eligible = fast and fast_runtime_change and not rejected_fast_paths
    service_impact = {name for name in ("api", "worker", "acquisition") if name in impact}
    guarded_full_cutover = bool(
        args.full or {"deployment", "migration"}.intersection(impact) or len(service_impact) > 1
    )
    mode = (
        "fast-api-only"
        if fast_eligible
        else "full"
        if guarded_full_cutover
        else f"{next(iter(service_impact))}-only"
        if service_impact and service_impact != {"api"}
        else "no-op"
        if not service_impact
        else "minimal"
    )
    full_cutover = bool(impact) and not fast_eligible and guarded_full_cutover
    return {
        "schema_version": 1,
        "kind": "leo-deployment-plan",
        "current_revision": current,
        "current_api_revision": current_api,
        "comparison_revision": comparison,
        "target_revision": target,
        "changed_paths": list(paths),
        "components": [component.name for component in components],
        "impact": impact,
        "mode": mode,
        "services_to_restart": (
            ["api"]
            if fast_eligible
            else [name for name in ("api", "worker", "acquisition") if name in impact]
        ),
        "migration_required": False if fast_eligible else "migration" in impact,
        "worker_fence_required": False if fast_eligible else "worker" in impact,
        "capture_policy_id": PRODUCTION_CAPTURE_POLICY if full_cutover else None,
        "fast_requested": fast,
        "fast_eligible": fast_eligible,
        "fast_rejected_paths": list(rejected_fast_paths),
        "fast_target_seconds": FAST_DEPLOY_TARGET_SECONDS if fast else None,
    }


def _fast_deploy_rejected_paths(paths: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        sorted(
            path
            for path in paths
            if any(fnmatch.fnmatchcase(path, pattern) for pattern in _FAST_DEPLOY_DENIED_PATTERNS)
            or not any(
                fnmatch.fnmatchcase(path, pattern) for pattern in _FAST_DEPLOY_ALLOWED_PATTERNS
            )
        )
    )


def _deploy(args: argparse.Namespace) -> int:
    document = _deployment_plan(args)
    if args.plan:
        print(json.dumps(document, indent=2, sort_keys=True))
        return 0
    impact = set(document["impact"])
    target = str(document["target_revision"])
    current = document["current_revision"]
    if args.stage_only:
        if os.geteuid() != 0:
            raise OpsError("release staging requires root; rerun with sudo")
        _stage_release(target)
        print(f"STAGED-ONLY revision={target} release={RELEASE_ROOT / 'releases' / target}")
        _warn_release_pressure()
        return 0
    if not impact:
        print(f"NO-OP target={target} has no runtime impact")
        return 0
    if bool(getattr(args, "fast", False)):
        rejected = tuple(document["fast_rejected_paths"])
        if rejected:
            raise OpsError(
                "fast deploy refuses changes outside the API/UI boundary: " + ", ".join(rejected)
            )
        if not document["fast_eligible"]:
            raise OpsError("fast deploy requires at least one API/UI runtime change")
        if os.geteuid() != 0:
            raise OpsError("mutating deployment requires root; rerun with sudo")
        current_api = document.get("current_api_revision")
        if current is None or current_api is None:
            raise OpsError("fast deploy requires reviewed global and API component selectors")
        _require_passing_release_qualification(str(current))
        _require_matching_test_receipt(
            target=target,
            changed=tuple(document["changed_paths"]),
        )
        return _deploy_api_release(
            target=target,
            previous=str(current_api),
            plan=document,
            require_pre_staged=True,
        )
    service_impact = {name for name in ("api", "worker", "acquisition") if name in impact}
    full_cutover = bool(
        args.full or {"deployment", "migration"}.intersection(impact) or len(service_impact) > 1
    )
    if full_cutover:
        if os.geteuid() != 0:
            raise OpsError("mutating deployment requires root; rerun with sudo")
        if current is None:
            raise OpsError("an existing immutable release is required for guarded cutover")
        _require_matching_test_receipt(
            target=target,
            changed=tuple(document["changed_paths"]),
        )
        return _deploy_full_release(target=target, previous=str(current), plan=document)
    if os.geteuid() != 0:
        raise OpsError("mutating deployment requires root; rerun with sudo")
    component = next(iter(service_impact))
    current_component = _selected_component_release_revision(component)
    if current is None or current_component is None:
        raise OpsError(
            "component selectors require one reviewed --full rollout before minimal deploy"
        )
    _require_matching_test_receipt(target=target, changed=tuple(document["changed_paths"]))
    if component == "api":
        return _deploy_api_release(target=target, previous=str(current_component), plan=document)
    return _deploy_component_release(
        component=component,
        target=target,
        previous=str(current_component),
        plan=document,
    )


def _require_matching_test_receipt(*, target: str, changed: tuple[str, ...]) -> Path:
    receipt_root = ROOT / ".leo/test-receipts"
    for path in sorted(receipt_root.glob("*.json"), reverse=True):
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (
            receipt.get("kind") == "leo-test-receipt"
            and receipt.get("revision") == target
            and receipt.get("passed") is True
            and receipt.get("plan", {}).get("tier") != "fast-iteration"
            and set(receipt.get("plan", {}).get("paths", ())) >= set(changed)
        ):
            return path
    raise OpsError(
        "no passing exact-revision test receipt covers the deployment delta; "
        f"run ./ops test --base {str(_selected_component_release_revision('api'))}"
    )


def _deploy_api_release(
    *,
    target: str,
    previous: str,
    plan: dict[str, Any],
    require_pre_staged: bool = False,
) -> int:
    lock_path = RELEASE_ROOT / ".ops-deploy.lock"
    lock_path.touch(mode=0o600, exist_ok=True)
    with lock_path.open("r+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise OpsError("another deployment holds the host lock") from error
        started = time.monotonic()
        if require_pre_staged:
            _require_pre_staged_release(target)
        _stage_release(target)
        selector = ROOT / "deploy/scripts/select-component-release"
        restart = RELEASE_ROOT / "releases" / target / "deploy/scripts/restart-current-api"
        subprocess.run((str(selector), "api", target), check=True)
        try:
            subprocess.run((str(restart),), check=True)
        except subprocess.CalledProcessError:
            subprocess.run((str(selector), "api", previous), check=True)
            rollback = RELEASE_ROOT / "releases" / previous / "deploy/scripts/restart-current-api"
            subprocess.run((str(rollback),), check=True)
            raise
        DEPLOYMENT_EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        receipt_path = DEPLOYMENT_EVIDENCE_ROOT / f"deploy-{stamp}-{target}.json"
        duration_seconds = round(time.monotonic() - started, 6)
        receipt = {
            "schema_version": 1,
            "kind": "leo-deployment-receipt",
            "mode": "fast-api-only" if require_pre_staged else "api-only",
            "previous_revision": previous,
            "target_revision": target,
            "duration_seconds": duration_seconds,
            "target_seconds": (FAST_DEPLOY_TARGET_SECONDS if require_pre_staged else None),
            "met_target": (
                duration_seconds <= FAST_DEPLOY_TARGET_SECONDS if require_pre_staged else None
            ),
            "pre_staged": require_pre_staged,
            "plan": plan,
            "healthy": True,
        }
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        _seal_evidence_file(receipt_path)
        print(f"DEPLOYED component=api revision={target} receipt={receipt_path}")
        if require_pre_staged and duration_seconds > FAST_DEPLOY_TARGET_SECONDS:
            print(
                "FAST-DEPLOY-WARNING "
                f"duration={duration_seconds:.3f}s "
                f"target={FAST_DEPLOY_TARGET_SECONDS:.0f}s",
                file=sys.stderr,
            )
        _warn_release_pressure()
    return 0


def _deploy_component_release(
    *,
    component: str,
    target: str,
    previous: str,
    plan: dict[str, Any],
) -> int:
    """Cut over one prequalified worker or acquisition component transactionally."""

    if component not in {"worker", "acquisition"}:
        raise OpsError("narrow component deployment supports only worker or acquisition")
    lock_path = RELEASE_ROOT / ".ops-deploy.lock"
    lock_path.touch(mode=0o600, exist_ok=True)
    with lock_path.open("r+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise OpsError("another deployment holds the host lock") from error
        started = time.monotonic()
        _stage_release(target)
        release_receipt = _release_qualification(target)
        release = RELEASE_ROOT / "releases" / target
        previous_release = RELEASE_ROOT / "releases" / previous
        selector = release / "deploy/scripts/select-component-release"
        restart = release / f"deploy/scripts/restart-current-{component}s"
        if component == "acquisition":
            restart = release / "deploy/scripts/restart-current-acquisition"
            environment_path = PRODUCTION_ACQUISITION_ENVIRONMENT
            old_environment = environment_path.read_bytes()
            write_environment = _write_acquisition_release_environment
            previous_acquisition_state = _acquisition_desired_state(previous_release)
        else:
            environment_path = PRODUCTION_WORKER_ENVIRONMENT
            old_environment = _ensure_worker_release_environment(environment_path, previous)
            write_environment = _write_worker_release_environment
            _fence_previous_release(release=release, previous=previous, target=target)
        selected = False
        environment_written = False
        try:
            subprocess.run((str(selector), component, target), check=True)
            selected = True
            write_environment(environment_path, old_environment, target)
            environment_written = True
            _verify_cutover(
                target=target,
                release_receipt=release_receipt,
                release=release,
                component=component,
            )
            subprocess.run((str(restart),), check=True)
        except Exception:
            if selected:
                subprocess.run((str(selector), component, previous), check=True)
            if environment_written:
                _restore_environment(environment_path, old_environment)
            if selected and environment_written:
                rollback = previous_release / restart.relative_to(release)
                subprocess.run((str(rollback),), check=True)
                if component == "acquisition" and previous_acquisition_state == "running":
                    _resume_acquisition_after_rollback(previous_release)
            raise
        receipt_path = _write_deployment_receipt(
            target=target,
            previous=previous,
            mode=f"{component}-only",
            started=started,
            plan=plan,
            release_receipt=release_receipt,
        )
        print(f"DEPLOYED component={component} revision={target} receipt={receipt_path}")
        _warn_release_pressure()
    return 0


def _require_pre_staged_release(
    target: str,
    *,
    release_root: Path = RELEASE_ROOT,
) -> Path:
    release = release_root / "releases" / target
    metadata = release_root / "release-metadata" / f"{target}.txt"
    if not release.is_dir() or release.is_symlink():
        raise OpsError(
            "fast deploy requires an already-staged immutable release; run "
            f"sudo ./ops deploy --stage-only --revision {target}"
        )
    if not metadata.is_file() or metadata.is_symlink():
        raise OpsError("fast deploy target has no sealed publication metadata")
    return release


def _deploy_full_release(*, target: str, previous: str, plan: dict[str, Any]) -> int:
    if plan.get("capture_policy_id") != PRODUCTION_CAPTURE_POLICY:
        raise OpsError("deployment plan lost the production capture-policy authority")
    lock_path = RELEASE_ROOT / ".ops-deploy.lock"
    lock_path.touch(mode=0o600, exist_ok=True)
    with lock_path.open("r+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise OpsError("another deployment holds the host lock") from error
        started = time.monotonic()
        _stage_release(target)
        release_receipt = _release_qualification(target)
        release = RELEASE_ROOT / "releases" / target
        previous_selectors = _selected_selector_revisions()
        if previous_selectors["global"] != previous:
            raise OpsError("global selector changed while the deployment plan was being applied")
        environment_path = PRODUCTION_ENVIRONMENT
        old_environment = environment_path.read_bytes()
        worker_environment_path = PRODUCTION_WORKER_ENVIRONMENT
        old_worker_environment = _ensure_worker_release_environment(
            worker_environment_path,
            previous_selectors["worker"],
        )
        acquisition_environment_path = PRODUCTION_ACQUISITION_ENVIRONMENT
        old_acquisition_environment = acquisition_environment_path.read_bytes()
        database_url = _environment_values(old_environment)["LEO_DATABASE_URL"]
        migration_changed = _migration_required(release=release, database_url=database_url)
        quiesced = False
        try:
            _quiesce_runtime()
            quiesced = True
            if migration_changed:
                _backup_database(target=target, database_url=database_url)
                _run_as_leo(
                    (
                        str(release / ".venv/bin/alembic"),
                        "-c",
                        str(release / "alembic.ini"),
                        "upgrade",
                        "head",
                    ),
                    extra_environment={"LEO_DATABASE_URL": database_url},
                )
            _write_deployment_environment(environment_path, old_environment, target)
            _write_worker_release_environment(
                worker_environment_path,
                old_worker_environment,
                target,
            )
            _write_acquisition_release_environment(
                acquisition_environment_path,
                old_acquisition_environment,
                target,
            )
            _select_all_components(release=release, revision=target)
            _fence_previous_release(release=release, previous=previous, target=target)
            _install_units(release)
            _verify_cutover(
                target=target,
                release_receipt=release_receipt,
                release=release,
            )
            _start_runtime()
            _verify_runtime(target)
        except Exception as cutover_error:
            if quiesced:
                try:
                    if migration_changed:
                        # A previous release may not be compatible with the migrated
                        # schema.  It is still mandatory to leave every target
                        # process stopped instead of allowing a partial start to run.
                        _quiesce_runtime()
                    else:
                        _restore_full_release(
                            selector_revisions=previous_selectors,
                            selector_release=release,
                            environment_path=environment_path,
                            old_environment=old_environment,
                            worker_environment_path=worker_environment_path,
                            old_worker_environment=old_worker_environment,
                            acquisition_environment_path=acquisition_environment_path,
                            old_acquisition_environment=old_acquisition_environment,
                        )
                except Exception as rollback_error:
                    raise OpsError(
                        f"cutover failed ({cutover_error}); rollback failed ({rollback_error})"
                    ) from rollback_error
            raise
        receipt_path = _write_deployment_receipt(
            target=target,
            previous=previous,
            mode="full",
            started=started,
            plan=plan,
            release_receipt=release_receipt,
        )
        print(f"DEPLOYED mode=full revision={target} receipt={receipt_path}")
        _warn_release_pressure()
    return 0


def _select_all_components(*, release: Path, revision: str) -> None:
    _select_component_revisions(
        release=release,
        revisions={component: revision for component in _SELECTOR_COMPONENTS},
    )


def _select_component_revisions(*, release: Path, revisions: dict[str, str]) -> None:
    if set(revisions) != set(_SELECTOR_COMPONENTS):
        raise OpsError("component selector snapshot is incomplete")
    selector = release / "deploy/scripts/select-component-release"
    for component in _SELECTOR_COMPONENTS:
        subprocess.run((str(selector), component, revisions[component]), check=True)


def _release_qualification(target: str) -> Path:
    existing = _passing_release_qualification(target)
    if existing is not None:
        return existing
    release = RELEASE_ROOT / "releases" / target
    evidence_root = Path("/srv/bulk/leo/qualification/release")
    run_id = f"release-{target[:7]}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    command = (
        str(release / ".venv/bin/leo-release-qualify"),
        "--project-root",
        str(release),
        "--database-url",
        "postgresql+psycopg:///leo_qualification",
        "--corpus-root",
        "/srv/bulk/leo/test-corpus",
        "--evidence-root",
        str(evidence_root),
        "--run-id",
        run_id,
    )
    completed = _run_as_leo(
        command,
        extra_environment={
            "HOME": "/var/lib/leo",
            "PATH": (
                f"{release}/.release-tools:{release}/.venv/bin:"
                f"{release}/web/node_modules/.bin:/usr/local/bin:/usr/bin"
            ),
            "PLAYWRIGHT_BROWSERS_PATH": "/var/lib/leo/.cache/ms-playwright",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "safe.directory",
            "GIT_CONFIG_VALUE_0": str(release),
        },
        capture_output=True,
    )
    try:
        receipt_path = Path(json.loads(completed.stdout.splitlines()[-1])["receipt"])
    except (IndexError, KeyError, TypeError, ValueError) as error:
        raise OpsError("release qualification did not return a receipt") from error
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise OpsError("release qualification receipt is unreadable") from error
    if receipt.get("git_revision") != target or receipt.get("passed") is not True:
        raise OpsError("release qualification receipt does not pass for the exact target")
    return receipt_path


def _passing_release_qualification(target: str) -> Path | None:
    evidence_root = Path("/srv/bulk/leo/qualification/release")
    for receipt_path in sorted(evidence_root.glob("*/receipt.json"), reverse=True):
        if not _is_sealed_evidence_file(receipt_path):
            continue
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if receipt.get("git_revision") == target and receipt.get("passed") is True:
            return receipt_path
    return None


def _require_passing_release_qualification(
    target: str,
    *,
    deployment_root: Path = DEPLOYMENT_EVIDENCE_ROOT,
    release_evidence_root: Path = Path("/srv/bulk/leo/qualification/release"),
) -> Path:
    for deployment_path in sorted(deployment_root.glob("deploy-*.json"), reverse=True):
        if not _is_sealed_evidence_file(deployment_path):
            continue
        try:
            deployment = json.loads(deployment_path.read_text(encoding="utf-8"))
            receipt_path = Path(str(deployment["release_qualification_receipt"]))
        except (KeyError, OSError, TypeError, ValueError):
            continue
        if (
            deployment.get("kind") != "leo-deployment-receipt"
            or deployment.get("mode") != "full"
            or deployment.get("target_revision") != target
            or deployment.get("healthy") is not True
            or not receipt_path.is_absolute()
            or release_evidence_root not in receipt_path.parents
            or not _is_sealed_evidence_file(receipt_path)
        ):
            continue
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if receipt.get("git_revision") == target and receipt.get("passed") is True:
            return receipt_path
    raise OpsError(
        "fast deploy requires a sealed healthy full-deployment receipt and passing "
        f"release qualification for the selected global base {target}"
    )


def _is_sealed_evidence_file(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    return stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o440


def _environment_values(raw: bytes) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in raw.decode().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator:
            raise OpsError("production environment contains an invalid line")
        values[key] = value.strip().strip("'").strip('"')
    return values


def _write_deployment_environment(path: Path, old_environment: bytes, target: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise OpsError("production environment must be a regular non-symlink file")
    if path.read_bytes() != old_environment:
        raise OpsError("production environment changed after the deployment snapshot")
    lines = old_environment.decode().splitlines()
    updates = {
        **_REVIEWED_CONTINUITY_ENVIRONMENT,
        "LEO_PIPELINE_RELEASE_ID": target,
    }
    locations: dict[str, list[int]] = {key: [] for key in updates}
    for index, line in enumerate(lines):
        key, separator, _value = line.partition("=")
        normalized_key = key.strip()
        if separator and normalized_key in locations and not line.lstrip().startswith("#"):
            locations[normalized_key].append(index)
    invalid = tuple(
        key
        for key, matches in locations.items()
        if (len(matches) > 1 or (not matches and key not in _ADDITIVE_REVIEWED_ENVIRONMENT_KEYS))
    )
    if invalid:
        raise OpsError(
            "production environment must contain exactly one binding for: " + ", ".join(invalid)
        )
    insertion_index = locations["LEO_CAPTURE_PROFILE"][0] + 1
    for key, value in updates.items():
        if locations[key]:
            lines[locations[key][0]] = f"{key}={value}"
    additions = [f"{key}={value}" for key, value in updates.items() if not locations[key]]
    lines[insertion_index:insertion_index] = additions
    temporary = path.with_name(f".{path.name}.ops-{os.getpid()}")
    try:
        temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.chown(temporary, 0, grp.getgrnam("leo").gr_gid)
        os.chmod(temporary, 0o640)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_acquisition_release_environment(
    path: Path,
    old_environment: bytes,
    target: str,
) -> None:
    """Atomically bind acquisition provenance to the selected component release."""

    if path.is_symlink() or not path.is_file():
        raise OpsError("acquisition environment must be a regular non-symlink file")
    if path.read_bytes() != old_environment:
        raise OpsError("acquisition environment changed after the deployment snapshot")
    lines = old_environment.decode().splitlines()
    release_key = "LEO_ACQUISITION_RELEASE_ID"
    binary_key = "LEO_SCANNER_PERSISTENT_IIOD_BINARY_PATH"
    scanner_key = "LEO_SCANNER_ENABLED"
    locations = {
        key: [
            index
            for index, line in enumerate(lines)
            if not line.lstrip().startswith("#")
            and line.partition("=")[1]
            and line.partition("=")[0].strip() == key
        ]
        for key in (release_key, binary_key, scanner_key)
    }
    if len(locations[release_key]) != 1 or any(
        len(locations[key]) > 1 for key in (binary_key, scanner_key)
    ):
        raise OpsError(
            "acquisition environment must contain exactly one release binding and at most "
            "one persistent-hop iiOD binary and scanner-enable binding"
        )
    binary_path = f"/opt/leo-tracker/releases/{target}/runtime/scanner-iiod/iiod"
    release_location = locations[release_key][0]
    lines[release_location] = f"{release_key}={target}"
    updates = {binary_key: binary_path, scanner_key: "false"}
    for key, value in updates.items():
        if locations[key]:
            lines[locations[key][0]] = f"{key}={value}"
    additions = [f"{key}={value}" for key, value in updates.items() if not locations[key]]
    lines[release_location + 1 : release_location + 1] = additions
    temporary = path.with_name(f".{path.name}.ops-{os.getpid()}")
    try:
        temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.chown(temporary, 0, grp.getgrnam("leo").gr_gid)
        os.chmod(temporary, 0o640)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _ensure_worker_release_environment(path: Path, revision: str) -> bytes:
    """Create the component binding once, then return its exact snapshot."""

    if path.is_symlink():
        raise OpsError("worker environment must be a regular non-symlink file")
    if not path.exists():
        temporary = path.with_name(f".{path.name}.ops-create-{os.getpid()}")
        try:
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o640,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(f"LEO_PIPELINE_RELEASE_ID={revision}\n")
            os.chown(temporary, 0, grp.getgrnam("leo").gr_gid)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    if not path.is_file() or path.is_symlink():
        raise OpsError("worker environment must be a regular non-symlink file")
    content = path.read_bytes()
    lines = content.decode().splitlines()
    locations = [
        index
        for index, line in enumerate(lines)
        if not line.lstrip().startswith("#")
        and line.partition("=")[1]
        and line.partition("=")[0].strip() == "LEO_PIPELINE_RELEASE_ID"
    ]
    if len(locations) != 1:
        raise OpsError(
            "worker environment must contain exactly one LEO_PIPELINE_RELEASE_ID binding"
        )
    if _environment_values(content)["LEO_PIPELINE_RELEASE_ID"] != revision:
        raise OpsError("worker environment does not match the selected worker release")
    return content


def _write_worker_release_environment(path: Path, old_environment: bytes, target: str) -> None:
    """Atomically bind worker provenance to the selected component release."""

    if path.is_symlink() or not path.is_file():
        raise OpsError("worker environment must be a regular non-symlink file")
    if path.read_bytes() != old_environment:
        raise OpsError("worker environment changed after the deployment snapshot")
    lines = old_environment.decode().splitlines()
    locations = [
        index
        for index, line in enumerate(lines)
        if not line.lstrip().startswith("#")
        and line.partition("=")[1]
        and line.partition("=")[0].strip() == "LEO_PIPELINE_RELEASE_ID"
    ]
    if len(locations) != 1:
        raise OpsError(
            "worker environment must contain exactly one LEO_PIPELINE_RELEASE_ID binding"
        )
    lines[locations[0]] = f"LEO_PIPELINE_RELEASE_ID={target}"
    temporary = path.with_name(f".{path.name}.ops-{os.getpid()}")
    try:
        temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.chown(temporary, 0, grp.getgrnam("leo").gr_gid)
        os.chmod(temporary, 0o640)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _migration_required(*, release: Path, database_url: str) -> bool:
    target = _run_as_leo(
        (str(release / ".venv/bin/alembic"), "-c", str(release / "alembic.ini"), "heads"),
        extra_environment={"PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
    ).stdout.split()[0]
    current_output = _run_as_leo(
        (str(release / ".venv/bin/alembic"), "-c", str(release / "alembic.ini"), "current"),
        extra_environment={"LEO_DATABASE_URL": database_url},
        capture_output=True,
    ).stdout
    current = current_output.split()[0]
    return current != target


def _backup_database(*, target: str, database_url: str) -> Path:
    parsed = urlparse(database_url.replace("postgresql+psycopg", "postgresql", 1))
    if parsed.path.lstrip("/") != "leo_tracker":
        raise OpsError("production backup requires the exact leo_tracker database")
    root = Path("/srv/bulk/leo/backups/postgresql")
    root.mkdir(parents=True, exist_ok=True)
    destination = root / f"pre-cutover-{target}.dump"
    temporary = destination.with_suffix(".dump.partial")
    _run_as_leo(("/usr/bin/pg_dump", "-Fc", "-d", "leo_tracker", "-f", str(temporary)))
    os.replace(temporary, destination)
    return destination


def _quiesce_runtime() -> None:
    # Timers are stopped first so no passive unit can be activated while the
    # corresponding services are being drained.  The inventory mirrors every
    # service and timer shipped beneath deploy/systemd.
    subprocess.run(
        ("/usr/bin/systemctl", "stop", *_LEO_TIMER_UNITS),
        check=False,
    )
    subprocess.run(
        ("/usr/bin/systemctl", "stop", *_LEO_SERVICE_UNITS),
        check=False,
    )
    subprocess.run(
        (
            "/usr/bin/systemctl",
            "kill",
            "--kill-who=all",
            "--signal=SIGKILL",
            _WORKER_UNIT_PATTERN,
        ),
        check=False,
    )
    subprocess.run(
        ("/usr/bin/systemctl", "stop", _WORKER_UNIT_PATTERN),
        check=False,
    )
    _verify_runtime_quiesced()


def _verify_runtime_quiesced() -> None:
    completed = subprocess.run(
        (
            "/usr/bin/systemctl",
            "list-units",
            "leo-*",
            "--state=active,activating,reloading",
            "--no-legend",
            "--no-pager",
            "--plain",
        ),
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    active_units = tuple(
        line.split(maxsplit=1)[0] for line in completed.stdout.splitlines() if line.strip()
    )
    if active_units:
        raise OpsError(
            "canonical LEO units remain active after quiesce: " + ", ".join(active_units)
        )


def _fence_previous_release(*, release: Path, previous: str, target: str) -> None:
    _fence_active_release(
        release=release,
        fenced_revision=previous,
        replacement_revision=target,
        operation_kind="deploy",
        operator="ops-deploy",
    )


def _fence_target_release_for_rollback(*, release: Path, target: str, previous: str) -> None:
    _fence_active_release(
        release=release,
        fenced_revision=target,
        replacement_revision=previous,
        operation_kind="rollback",
        operator="ops-rollback",
        allow_absent=True,
    )


def _trailing_json_command_result(output: str | None) -> dict[str, Any]:
    """Decode the final JSON object without treating validator prelude lines as JSON."""

    if not isinstance(output, str):
        raise ValueError("command output is not text")
    decoder = json.JSONDecoder()
    candidate_offsets = tuple(match.end() for match in re.finditer(r"(?m)^[ \t]*(?=\{)", output))
    for offset in reversed(candidate_offsets):
        try:
            result, end = decoder.raw_decode(output, offset)
        except json.JSONDecodeError:
            continue
        if output[end:].strip() or not isinstance(result, dict):
            continue
        return result
    raise ValueError("command output has no trailing JSON object")


def _fence_active_release(
    *,
    release: Path,
    fenced_revision: str,
    replacement_revision: str,
    operation_kind: str,
    operator: str,
    allow_absent: bool = False,
) -> None:
    operation_id = (
        f"{operation_kind}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{fenced_revision}"
    )
    command = (
        str(release / ".venv/bin/leo"),
        "process",
        "stop-and-fence",
        "--release",
        fenced_revision,
        "--operation-id",
        operation_id,
        "--operator",
        operator,
        "--reason",
        f"{operation_kind} replacement by {replacement_revision}",
        "--all-active-for-release",
        "--yes",
        "--json",
    )
    try:
        _run_as_leo(
            command,
            source_environment=True,
            capture_output=allow_absent,
        )
    except subprocess.CalledProcessError as error:
        if not allow_absent or error.returncode != _CLI_NOT_FOUND_EXIT_CODE:
            raise
        try:
            result = _trailing_json_command_result(error.stdout)
        except (TypeError, ValueError) as decode_error:
            raise error from decode_error
        expected_message = f"pipeline release is absent: {fenced_revision}"
        if (
            result.get("command") != "process.stop-and-fence"
            or result.get("exit_code") != _CLI_NOT_FOUND_EXIT_CODE
            or result.get("message") != expected_message
            or result.get("payload") is not None
        ):
            raise error
        print(f"FENCE-NO-OP release={fenced_revision} reason=absent")


def _install_units(release: Path) -> None:
    systemd_root = release / "deploy/systemd"
    units = sorted(path for path in systemd_root.glob("leo-*.*") if path.is_file())
    for unit in units:
        if unit.is_symlink():
            raise OpsError(f"systemd unit must be a regular non-symlink file: {unit}")
        subprocess.run(
            (
                "/usr/bin/install",
                "-o",
                "root",
                "-g",
                "root",
                "-m",
                "0644",
                str(unit),
                "/etc/systemd/system/",
            ),
            check=True,
        )
    drop_in_directories = sorted(systemd_root.glob("leo-*.service.d"))
    for source_directory in drop_in_directories:
        if source_directory.is_symlink() or not source_directory.is_dir():
            raise OpsError(
                f"systemd drop-in source must be a regular directory: {source_directory}"
            )
        destination_directory = Path("/etc/systemd/system") / source_directory.name
        subprocess.run(
            (
                "/usr/bin/install",
                "-d",
                "-o",
                "root",
                "-g",
                "root",
                "-m",
                "0755",
                str(destination_directory),
            ),
            check=True,
        )
        entries = sorted(source_directory.iterdir())
        if not entries:
            raise OpsError(f"systemd drop-in directory is empty: {source_directory}")
        for source in entries:
            if source.is_symlink() or not source.is_file() or source.suffix != ".conf":
                raise OpsError(f"systemd drop-in must be a regular .conf file: {source}")
            subprocess.run(
                (
                    "/usr/bin/install",
                    "-o",
                    "root",
                    "-g",
                    "root",
                    "-m",
                    "0644",
                    str(source),
                    str(destination_directory),
                ),
                check=True,
            )
    subprocess.run(("/usr/bin/systemd-analyze", "verify", *map(str, units)), check=True)
    subprocess.run(("/usr/bin/systemctl", "daemon-reload"), check=True)


def _verify_cutover(
    *,
    target: str,
    release_receipt: Path,
    release: Path,
    component: str | None = None,
) -> None:
    standard = Path(
        "/srv/bulk/leo/qualification/standard-cutover/"
        "trial-132-standard-v2-full-review-receipt.json"
    )
    command = [
        str(release / "deploy/scripts/verify-production-cutover"),
        "--revision",
        target,
        "--legacy-user",
        "mouse9911",
        "--release-receipt",
        str(release_receipt),
        "--standard-regression-receipt",
        str(standard),
    ]
    if component is not None:
        command.extend(("--component", component))
    subprocess.run(tuple(command), check=True)


def _start_runtime() -> None:
    subprocess.run(
        (
            "/usr/bin/systemctl",
            "start",
            "leo-api.service",
            *_WORKER_UNITS,
            "leo-acquisition.service",
        ),
        check=True,
    )
    subprocess.run(
        (
            "/usr/bin/systemctl",
            "enable",
            "--now",
            "leo-reconcile.timer",
            "leo-retention.timer",
            "leo-tle-collection.timer",
        ),
        check=True,
    )


def _verify_runtime(target: str) -> None:
    _verify_restored_runtime(
        {component: target for component in _SELECTOR_COMPONENTS},
    )


def _verify_restored_runtime(selector_revisions: dict[str, str]) -> None:
    if set(selector_revisions) != set(_SELECTOR_COMPONENTS):
        raise OpsError("component selector snapshot is incomplete")
    selected = {"global": _selected_release_revision()}
    selected.update(
        {
            component: _selected_component_release_revision(component)
            for component in _SELECTOR_COMPONENTS
            if component != "global"
        }
    )
    for component, revision in selector_revisions.items():
        if selected[component] != revision:
            raise OpsError(f"{component} selector failed exact-release verification")
    _verify_worker_environment_revision(selector_revisions["worker"])
    _verify_acquisition_environment_revision(selector_revisions["acquisition"])
    _wait_for_api()
    states = subprocess.run(
        (
            "/usr/bin/systemctl",
            "is-active",
            "leo-api.service",
            "leo-acquisition.service",
            "leo-worker@1.service",
            "leo-worker@20.service",
        ),
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.splitlines()
    if states != ["active"] * 4:
        raise OpsError(f"runtime service state is not active: {states}")


def _verify_acquisition_environment_revision(expected: str) -> None:
    path = PRODUCTION_ACQUISITION_ENVIRONMENT
    if path.is_symlink() or not path.is_file():
        raise OpsError("acquisition environment must be a regular non-symlink file")
    values = _environment_values(path.read_bytes())
    actual = values.get("LEO_ACQUISITION_RELEASE_ID")
    if actual != expected:
        raise OpsError(
            "acquisition environment release does not match the selected acquisition component"
        )
    expected_binary = f"/opt/leo-tracker/releases/{expected}/runtime/scanner-iiod/iiod"
    configured_binary = values.get("LEO_SCANNER_PERSISTENT_IIOD_BINARY_PATH")
    release_has_binary = Path(expected_binary).is_file()
    if configured_binary != expected_binary and (
        configured_binary is not None or release_has_binary
    ):
        raise OpsError("acquisition persistent-hop iiOD binary does not match the selected release")
    scanner_enabled = values.get("LEO_SCANNER_ENABLED")
    if (release_has_binary and scanner_enabled != "false") or (
        not release_has_binary and scanner_enabled not in {None, "false"}
    ):
        raise OpsError("release-A acquisition environment must keep the scanner disabled")


def _acquisition_desired_state(release: Path) -> str:
    completed = _run_as_leo(
        (str(release / ".venv/bin/leo"), "acquire", "status", "--json"),
        source_environment=True,
        component_environment=PRODUCTION_ACQUISITION_ENVIRONMENT,
        capture_output=True,
    )
    try:
        state = json.loads(completed.stdout)["payload"]["capture_control"]["desired_state"]
    except (KeyError, TypeError, ValueError) as error:
        raise OpsError("capture authority status is malformed") from error
    if state not in {"running", "paused"}:
        raise OpsError("capture authority has an unsupported desired state")
    return str(state)


def _resume_acquisition_after_rollback(release: Path) -> None:
    _run_as_leo(
        (
            str(release / ".venv/bin/leo"),
            "acquire",
            "resume",
            "--operator",
            "ops-rollback",
            "--reason",
            "restore pre-deployment capture authority",
            "--json",
        ),
        source_environment=True,
        component_environment=PRODUCTION_ACQUISITION_ENVIRONMENT,
    )


def _verify_worker_environment_revision(expected: str) -> None:
    path = PRODUCTION_WORKER_ENVIRONMENT
    if path.is_symlink() or not path.is_file():
        raise OpsError("worker environment must be a regular non-symlink file")
    content = path.read_bytes()
    lines = content.decode().splitlines()
    bindings = [
        line
        for line in lines
        if not line.lstrip().startswith("#")
        and line.partition("=")[1]
        and line.partition("=")[0].strip() == "LEO_PIPELINE_RELEASE_ID"
    ]
    if len(bindings) != 1:
        raise OpsError(
            "worker environment must contain exactly one LEO_PIPELINE_RELEASE_ID binding"
        )
    actual = _environment_values(content)["LEO_PIPELINE_RELEASE_ID"]
    if actual != expected:
        raise OpsError("worker environment release does not match the selected worker component")


def _wait_for_api(*, timeout_seconds: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    command = (
        "/usr/bin/curl",
        "--fail",
        "--silent",
        "--show-error",
        "--max-time",
        "2",
        "http://127.0.0.1:8090/api/v1/status",
    )
    while True:
        completed = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if completed.returncode == 0:
            return
        if time.monotonic() >= deadline:
            raise OpsError("API did not become healthy within the bounded startup window")
        time.sleep(0.25)


def _restore_full_release(
    *,
    selector_revisions: dict[str, str],
    selector_release: Path,
    environment_path: Path,
    old_environment: bytes,
    worker_environment_path: Path,
    old_worker_environment: bytes,
    acquisition_environment_path: Path,
    old_acquisition_environment: bytes,
) -> None:
    # A failed start can leave some target services alive.  Never repoint a
    # selector or replace its unit/environment beneath such a process.
    _quiesce_runtime()
    _restore_environment(environment_path, old_environment)
    _restore_environment(worker_environment_path, old_worker_environment)
    _restore_environment(acquisition_environment_path, old_acquisition_environment)
    previous_release = RELEASE_ROOT / "releases" / selector_revisions["global"]
    _select_component_revisions(release=selector_release, revisions=selector_revisions)
    _install_units(previous_release)
    _fence_target_release_for_rollback(
        release=previous_release,
        target=selector_release.name,
        previous=selector_revisions["global"],
    )
    try:
        _start_runtime()
        _verify_restored_runtime(selector_revisions)
    except Exception:
        # Rollback health failure is also fail-closed: do not leave a partly
        # started prior runtime producing or claiming work after this command
        # reports failure.
        _quiesce_runtime()
        raise


def _write_deployment_receipt(
    *,
    target: str,
    previous: str,
    mode: str,
    started: float,
    plan: dict[str, Any],
    release_receipt: Path,
) -> Path:
    root = DEPLOYMENT_EVIDENCE_ROOT
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = root / f"deploy-{stamp}-{target}.json"
    document = {
        "schema_version": 1,
        "kind": "leo-deployment-receipt",
        "mode": mode,
        "previous_revision": previous,
        "target_revision": target,
        "duration_seconds": round(time.monotonic() - started, 6),
        "plan": plan,
        "release_qualification_receipt": str(release_receipt),
        "healthy": True,
    }
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _seal_evidence_file(path)
    return path


def _restore_environment(path: Path, content: bytes) -> None:
    if path.is_symlink() or not path.is_file():
        raise OpsError("production environment must be a regular non-symlink file")
    temporary = path.with_name(f".{path.name}.ops-restore-{os.getpid()}")
    try:
        temporary.write_bytes(content)
        os.chown(temporary, 0, grp.getgrnam("leo").gr_gid)
        os.chmod(temporary, 0o640)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _seal_evidence_file(path: Path) -> None:
    os.chown(path, 0, grp.getgrnam("leo").gr_gid)
    os.chmod(path, 0o440)


def _run_as_leo(
    command: tuple[str, ...],
    *,
    extra_environment: dict[str, str] | None = None,
    source_environment: bool = False,
    component_environment: Path | None = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    if component_environment is not None and not source_environment:
        raise OpsError("a component environment requires the production environment")
    argv: tuple[str, ...]
    if source_environment:
        quoted = " ".join(shlex.quote(item) for item in command)
        component_source = (
            f"source {shlex.quote(str(component_environment))}; "
            if component_environment is not None
            else ""
        )
        argv = (
            "/usr/sbin/runuser",
            "-u",
            "leo",
            "--",
            "/bin/bash",
            "-c",
            (
                "set -a; source /etc/leo/leo.env; "
                f"{component_source}set +a; "
                f"export PYTHONDONTWRITEBYTECODE=1; exec {quoted}"
            ),
        )
    else:
        child_environment = dict(extra_environment or {})
        child_environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment_arguments = tuple(
            f"{key}={value}" for key, value in sorted(child_environment.items())
        )
        argv = (
            "/usr/sbin/runuser",
            "-u",
            "leo",
            "--",
            "/usr/bin/env",
            *environment_arguments,
            *command,
        )
    return subprocess.run(
        argv,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture_output else None,
    )


def _stage_release(target: str) -> None:
    python = next(
        (
            path
            for path in (Path("/usr/bin/python3.14"), Path("/usr/bin/python3.12"))
            if path.is_file()
        ),
        None,
    )
    if python is None:
        raise OpsError("no reviewed versioned system Python is installed")
    current = _selected_release_revision()
    if current is None:
        raise OpsError("global immutable release selector is unavailable")
    uv = Path(f"/opt/leo-tracker/releases/{current}/.release-tools/uv").resolve()
    command = (
        str(ROOT / "deploy/scripts/stage-production-release"),
        "--source",
        str(ROOT),
        "--revision",
        target,
        "--python-bin",
        str(python),
        "--uv-bin",
        str(uv),
        "--execute",
    )
    subprocess.run(command, check=True)


def _selected_release_revision(*, release_root: Path = RELEASE_ROOT) -> str | None:
    selector = release_root / "current"
    if not selector.is_symlink():
        return None
    target = os.readlink(selector)
    prefix = "releases/"
    revision = target.removeprefix(prefix)
    if target == prefix + revision and len(revision) == 40:
        return revision
    raise OpsError("current release selector is not an exact relative SHA")


def _selected_component_release_revision(
    component: str,
    *,
    release_root: Path = RELEASE_ROOT,
) -> str | None:
    selector = release_root / f"current-{component}"
    if not selector.is_symlink():
        return None
    target = os.readlink(selector)
    revision = target.removeprefix("releases/")
    if target == f"releases/{revision}" and len(revision) == 40:
        return revision
    raise OpsError(f"current {component} selector is not an exact relative SHA")


def _selected_selector_revisions(*, release_root: Path = RELEASE_ROOT) -> dict[str, str]:
    selected: dict[str, str | None] = {
        "global": _selected_release_revision(release_root=release_root)
    }
    selected.update(
        {
            component: _selected_component_release_revision(
                component,
                release_root=release_root,
            )
            for component in _SELECTOR_COMPONENTS
            if component != "global"
        }
    )
    missing = tuple(component for component in _SELECTOR_COMPONENTS if selected[component] is None)
    if missing:
        raise OpsError("missing immutable release selectors: " + ", ".join(missing))
    return {component: str(selected[component]) for component in _SELECTOR_COMPONENTS}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="ops")
    commands = result.add_subparsers(dest="command", required=True)
    test = commands.add_parser("test", help="run safe change-aware developer gates")
    test.add_argument(
        "--fast",
        action="store_true",
        help=(
            "run changed-file static checks and changed portable tests only; "
            "the receipt cannot authorize deployment"
        ),
    )
    test.add_argument("--all", action="store_true")
    test.add_argument("--release", action="store_true")
    test.add_argument("--explain", action="store_true")
    test.add_argument("--json")
    test.add_argument("--base")
    deploy = commands.add_parser("deploy", help="plan or perform an exact-main deployment")
    deploy.add_argument("--plan", action="store_true")
    deploy.add_argument(
        "--stage-only",
        action="store_true",
        help=(
            "stage and validate exact origin/main or the clean local HEAD without "
            "cutting over runtime state"
        ),
    )
    deploy.add_argument("--full", action="store_true")
    deploy.add_argument(
        "--fast",
        action="store_true",
        help=("switch only the API to a pre-staged API/UI-only revision; refuse broader changes"),
    )
    deploy.add_argument("--revision")
    releases = commands.add_parser(
        "releases",
        help="plan or apply guarded immutable-release retention",
    )
    mode = releases.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--apply", action="store_true")
    releases.add_argument("--keep", type=int, default=DEFAULT_RELEASE_RETENTION)
    releases.add_argument("--protect", action="append", metavar="FULL_SHA")
    releases.add_argument("--expect-plan", metavar="SHA256")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "test":
            return _test(args)
        if args.command == "deploy":
            return _deploy(args)
        return _releases(args)
    except (OpsError, subprocess.CalledProcessError) as error:
        print(f"ops: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
