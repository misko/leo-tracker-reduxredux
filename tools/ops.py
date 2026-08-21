#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import fnmatch
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "config/ops-components.json"
PROTECTED_DATABASES = frozenset({"leo_tracker", "postgres", "template0", "template1"})


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


def changed_paths(*, all_paths: bool = False) -> tuple[str, ...]:
    if all_paths:
        return tuple(line for line in _run_git("ls-files").splitlines() if line)
    head = _run_git("rev-parse", "HEAD")
    origin = _run_git("rev-parse", "origin/main")
    base = _run_git("merge-base", head, origin)
    paths = set(_git_lines("diff", "--name-only"))
    paths.update(_git_lines("diff", "--cached", "--name-only"))
    paths.update(_git_lines("ls-files", "--others", "--exclude-standard"))
    if not paths:
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
    python_paths = tuple(path for path in paths if path.endswith(".py"))
    source_changed = any(path.startswith("src/") for path in python_paths)
    gates: list[Gate] = []
    if python_paths:
        gates.extend(
            (
                Gate("ruff-check", _python_tool("ruff", "check", *python_paths)),
                Gate("ruff-format", _python_tool("ruff", "format", "--check", *python_paths)),
            )
        )
    if source_changed or all_tests:
        gates.append(Gate("mypy", _python_tool("mypy", "src")))
    changed_test_paths = sorted(
        path
        for path in paths
        if path.startswith("tests/")
        and path.endswith(".py")
        and not path.endswith("/conftest.py")
        and (ROOT / path).is_file()
    )
    if any(component.exclusive for component in components):
        test_paths = sorted(
            set(changed_test_paths).union(
                path for component in components if component.exclusive for path in component.tests
            )
        )
    elif changed_test_paths:
        # Component changes are required to carry component-owned tests. Running the
        # exact changed tests avoids recursively selecting a multi-minute directory.
        test_paths = changed_test_paths
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
                _python_tool("pytest", "-q", "-m", expression, *test_paths),
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
        completed = subprocess.run(
            gate.command,
            cwd=cwd,
            env=safe_child_environment(needs_postgres=gate.needs_postgres),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        output = completed.stdout
        exit_code = completed.returncode
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
    paths = changed_paths(all_paths=args.all or args.release)
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
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(gates))) as executor:
        results = list(executor.map(_execute_gate, gates))
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


def _deploy_plan(args: argparse.Namespace) -> int:
    if not args.plan:
        raise OpsError("mutating deploy is not enabled in this implementation slice; use --plan")
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
    document = {
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
    print(json.dumps(document, indent=2, sort_keys=True))
    return 0


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


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="ops")
    commands = result.add_subparsers(dest="command", required=True)
    test = commands.add_parser("test", help="run safe change-aware developer gates")
    test.add_argument("--all", action="store_true")
    test.add_argument("--release", action="store_true")
    test.add_argument("--explain", action="store_true")
    test.add_argument("--json")
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
        return _deploy_plan(args)
    except (OpsError, subprocess.CalledProcessError) as error:
        print(f"ops: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
