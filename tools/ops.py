#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import fcntl
import fnmatch
import grp
import hashlib
import json
import os
import shlex
import shutil
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
DEPLOYMENT_EVIDENCE_ROOT = Path("/srv/bulk/leo/qualification/deployment")


class OpsError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Component:
    name: str
    patterns: tuple[str, ...]
    tests: tuple[str, ...]
    impact: tuple[str, ...]
    postgres: bool = False
    web: bool = False
    exclusive: bool = False


@dataclass(frozen=True, slots=True)
class Gate:
    name: str
    command: tuple[str, ...]
    needs_postgres: bool = False


def _run_git(*arguments: str) -> str:
    completed = subprocess.run(
        ("git", *arguments), cwd=ROOT, check=True, text=True, stdout=subprocess.PIPE
    )
    return completed.stdout.strip()


def load_components(path: Path = MANIFEST_PATH) -> tuple[Component, ...]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != 1:
        raise OpsError("unsupported component manifest schema")
    return tuple(
        Component(
            name=item["name"],
            patterns=tuple(item["patterns"]),
            tests=tuple(item.get("tests", ())),
            impact=tuple(item.get("impact", ())),
            postgres=bool(item.get("postgres", False)),
            web=bool(item.get("web", False)),
            exclusive=bool(item.get("exclusive", False)),
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
        if not matches:
            unclassified.append(path)
        for component in matches:
            selected[component.name] = component
    if unclassified:
        raise OpsError("unclassified changed paths: " + ", ".join(sorted(unclassified)))
    return tuple(selected[name] for name in sorted(selected))


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
) -> tuple[Gate, ...]:
    # Deleted Python paths still select their owning component and deployment
    # impact, but file-oriented formatters cannot be invoked on an absent path.
    python_paths = tuple(path for path in paths if path.endswith(".py") and (ROOT / path).is_file())
    source_changed = any(path.startswith("src/") for path in python_paths)
    gates: list[Gate] = []
    if python_paths:
        gates.extend(
            (
                Gate("ruff-check", _python_tool("ruff", "check", *python_paths)),
                Gate(
                    "ruff-format",
                    _python_tool("ruff", "format", "--check", "--force-exclude", *python_paths),
                ),
            )
        )
    if source_changed or all_tests:
        gates.append(Gate("mypy", _python_tool("mypy", "src")))
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
        test_paths = sorted(
            set(changed_test_paths).union(
                path for component in components if component.exclusive for path in component.tests
            )
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
    elif any(component.exclusive for component in components):
        test_paths = sorted(
            path for component in components if component.exclusive for path in component.tests
        )
    else:
        test_paths = sorted({path for component in components for path in component.tests})
    if test_paths:
        needs_postgres = any(component.postgres for component in components)
        expression = "not real_corpus and not legacy_oracle"
        if not needs_postgres:
            expression += " and not postgres"
        gates.append(
            Gate(
                "pytest-components",
                _python_tool(
                    "pytest", "-q", "-p", "no:cacheprovider", "-m", expression, *test_paths
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
    location = ROOT / path
    if not location.is_dir():
        return (path,)
    files = tuple(
        item.relative_to(ROOT).as_posix()
        for item in sorted(location.glob("test_*.py"))
        if item.is_file()
    )
    return files or (path,)


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
    components = load_components()
    paths = changed_paths(
        all_paths=args.all or args.release,
        base_revision=args.base,
    )
    selected = components_for_paths(paths, components)
    gates = selected_gates(
        paths, selected, all_tests=args.all or args.release, release=args.release
    )
    plan = {
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


def _deployment_plan(args: argparse.Namespace) -> dict[str, Any]:
    if _run_git("status", "--porcelain"):
        raise OpsError("deployment planning requires a clean worktree")
    target = args.revision or _run_git("rev-parse", "origin/main")
    if len(target) != 40 or any(character not in "0123456789abcdef" for character in target):
        raise OpsError("deployment revision must be one full lowercase Git SHA")
    origin = _run_git("rev-parse", "origin/main")
    if target != origin:
        raise OpsError("ordinary deployment target must equal the locally fetched origin/main")
    current = _selected_release_revision()
    paths = tuple(_git_lines("diff", "--name-only", f"{current}..{target}")) if current else ()
    components = components_for_paths(paths, load_components())
    impact = sorted({item for component in components for item in component.impact})
    mode = "full" if {"migration", "systemd"}.intersection(impact) else "minimal"
    return {
        "schema_version": 1,
        "kind": "leo-deployment-plan",
        "current_revision": current,
        "target_revision": target,
        "changed_paths": list(paths),
        "components": [component.name for component in components],
        "impact": impact,
        "mode": mode,
        "services_to_restart": [
            name for name in ("api", "worker", "acquisition") if name in impact
        ],
        "migration_required": "migration" in impact,
        "worker_fence_required": "worker" in impact,
    }


def _deploy(args: argparse.Namespace) -> int:
    document = _deployment_plan(args)
    if args.plan:
        print(json.dumps(document, indent=2, sort_keys=True))
        return 0
    impact = set(document["impact"])
    target = str(document["target_revision"])
    current = document["current_revision"]
    if not impact:
        print(f"NO-OP target={target} has no runtime impact")
        return 0
    full_cutover = args.full or impact != {"api"}
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
    if current is None or _selected_component_release_revision("api") is None:
        raise OpsError(
            "component selectors require one reviewed --full rollout before minimal deploy"
        )
    _require_matching_test_receipt(target=target, changed=tuple(document["changed_paths"]))
    return _deploy_api_release(target=target, previous=str(current), plan=document)


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
            and set(receipt.get("plan", {}).get("paths", ())) >= set(changed)
        ):
            return path
    raise OpsError(
        "no passing exact-revision test receipt covers the deployment delta; "
        f"run ./ops test --base {str(_selected_component_release_revision('api'))}"
    )


def _deploy_api_release(*, target: str, previous: str, plan: dict[str, Any]) -> int:
    lock_path = RELEASE_ROOT / ".ops-deploy.lock"
    lock_path.touch(mode=0o600, exist_ok=True)
    with lock_path.open("r+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise OpsError("another deployment holds the host lock") from error
        started = time.monotonic()
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
        receipt = {
            "schema_version": 1,
            "kind": "leo-deployment-receipt",
            "mode": "api-only",
            "previous_revision": previous,
            "target_revision": target,
            "duration_seconds": round(time.monotonic() - started, 6),
            "plan": plan,
            "healthy": True,
        }
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        _seal_evidence_file(receipt_path)
        print(f"DEPLOYED component=api revision={target} receipt={receipt_path}")
    return 0


def _deploy_full_release(*, target: str, previous: str, plan: dict[str, Any]) -> int:
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
        environment_path = PRODUCTION_ENVIRONMENT
        old_environment = environment_path.read_bytes()
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
            _write_pipeline_release(environment_path, old_environment, target)
            _select_all_components(release=release, revision=target)
            _fence_previous_release(release=release, previous=previous, target=target)
            _install_units(release)
            _verify_cutover(target=target, release_receipt=release_receipt, release=release)
            _start_runtime()
            _verify_runtime(target)
        except Exception:
            if quiesced and not migration_changed:
                _restore_full_release(
                    previous=previous,
                    selector_release=release,
                    environment_path=environment_path,
                    old_environment=old_environment,
                )
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
    return 0


def _select_all_components(*, release: Path, revision: str) -> None:
    selector = release / "deploy/scripts/select-component-release"
    for component in ("global", "api", "worker", "acquisition"):
        subprocess.run((str(selector), component, revision), check=True)


def _release_qualification(target: str) -> Path:
    evidence_root = Path("/srv/bulk/leo/qualification/release")
    for receipt_path in sorted(evidence_root.glob("*/receipt.json"), reverse=True):
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if receipt.get("git_revision") == target and receipt.get("passed") is True:
            return receipt_path
    release = RELEASE_ROOT / "releases" / target
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


def _write_pipeline_release(path: Path, old_environment: bytes, target: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise OpsError("production environment must be a regular non-symlink file")
    lines = old_environment.decode().splitlines()
    matches = [
        index for index, line in enumerate(lines) if line.startswith("LEO_PIPELINE_RELEASE_ID=")
    ]
    if len(matches) != 1:
        raise OpsError("production environment must contain one pipeline release binding")
    lines[matches[0]] = f"LEO_PIPELINE_RELEASE_ID={target}"
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
    subprocess.run(("/usr/bin/systemctl", "stop", "leo-acquisition.service"), check=False)
    subprocess.run(
        (
            "/usr/bin/systemctl",
            "kill",
            "--kill-who=all",
            "--signal=SIGKILL",
            "leo-worker@*.service",
        ),
        check=False,
    )
    subprocess.run(("/usr/bin/systemctl", "stop", "leo-worker@*.service"), check=False)
    subprocess.run(("/usr/bin/systemctl", "stop", "leo-api.service"), check=False)
    subprocess.run(
        (
            "/usr/bin/systemctl",
            "stop",
            "leo-reconcile.service",
            "leo-reconcile.timer",
            "leo-retention.timer",
            "leo-tle-collection.timer",
        ),
        check=False,
    )


def _fence_previous_release(*, release: Path, previous: str, target: str) -> None:
    operation_id = f"deploy-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{previous}"
    command = (
        str(release / ".venv/bin/leo"),
        "process",
        "stop-and-fence",
        "--release",
        previous,
        "--operation-id",
        operation_id,
        "--operator",
        "ops-deploy",
        "--reason",
        f"full cutover to {target}",
        "--all-active-for-release",
        "--yes",
        "--json",
    )
    _run_as_leo(command, source_environment=True)


def _install_units(release: Path) -> None:
    units = sorted((release / "deploy/systemd").glob("leo-*.*"))
    for unit in units:
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
    subprocess.run(("/usr/bin/systemd-analyze", "verify", *map(str, units)), check=True)
    subprocess.run(("/usr/bin/systemctl", "daemon-reload"), check=True)


def _verify_cutover(*, target: str, release_receipt: Path, release: Path) -> None:
    standard = Path(
        "/srv/bulk/leo/qualification/standard-cutover/"
        "trial-132-standard-v2-full-review-receipt.json"
    )
    subprocess.run(
        (
            str(release / "deploy/scripts/verify-production-cutover"),
            "--revision",
            target,
            "--legacy-user",
            "mouse9911",
            "--release-receipt",
            str(release_receipt),
            "--standard-regression-receipt",
            str(standard),
        ),
        check=True,
    )


def _start_runtime() -> None:
    workers = tuple(f"leo-worker@{index}.service" for index in range(1, 21))
    subprocess.run(
        ("/usr/bin/systemctl", "start", "leo-api.service", *workers, "leo-acquisition.service"),
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
    for component in ("api", "worker", "acquisition"):
        if _selected_component_release_revision(component) != target:
            raise OpsError(f"{component} selector failed exact-release verification")
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
    previous: str,
    selector_release: Path,
    environment_path: Path,
    old_environment: bytes,
) -> None:
    _restore_environment(environment_path, old_environment)
    previous_release = RELEASE_ROOT / "releases" / previous
    _select_all_components(release=selector_release, revision=previous)
    _install_units(previous_release)
    _start_runtime()


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
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    argv: tuple[str, ...]
    if source_environment:
        quoted = " ".join(shlex.quote(item) for item in command)
        argv = (
            "/usr/sbin/runuser",
            "-u",
            "leo",
            "--",
            "/bin/bash",
            "-c",
            f"set -a; source /etc/leo/leo.env; set +a; exec {quoted}",
        )
    else:
        environment_arguments = tuple(
            f"{key}={value}" for key, value in sorted((extra_environment or {}).items())
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


def _selected_release_revision() -> str | None:
    selector = Path("/opt/leo-tracker/current")
    if not selector.is_symlink():
        return None
    target = os.readlink(selector)
    prefix = "releases/"
    revision = target.removeprefix(prefix)
    if target == prefix + revision and len(revision) == 40:
        return revision
    raise OpsError("current release selector is not an exact relative SHA")


def _selected_component_release_revision(component: str) -> str | None:
    selector = Path(f"/opt/leo-tracker/current-{component}")
    if not selector.is_symlink():
        return None
    target = os.readlink(selector)
    revision = target.removeprefix("releases/")
    if target == f"releases/{revision}" and len(revision) == 40:
        return revision
    raise OpsError(f"current {component} selector is not an exact relative SHA")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="ops")
    commands = result.add_subparsers(dest="command", required=True)
    test = commands.add_parser("test", help="run safe change-aware developer gates")
    test.add_argument("--all", action="store_true")
    test.add_argument("--release", action="store_true")
    test.add_argument("--explain", action="store_true")
    test.add_argument("--json")
    test.add_argument("--base")
    deploy = commands.add_parser("deploy", help="plan or perform an exact-main deployment")
    deploy.add_argument("--plan", action="store_true")
    deploy.add_argument("--full", action="store_true")
    deploy.add_argument("--revision")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "test":
            return _test(args)
        return _deploy(args)
    except (OpsError, subprocess.CalledProcessError) as error:
        print(f"ops: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
