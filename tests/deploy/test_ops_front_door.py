from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("leo_ops", ROOT / "tools/ops.py")
assert SPEC is not None and SPEC.loader is not None
OPS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = OPS
SPEC.loader.exec_module(OPS)


def test_every_tracked_path_is_classified() -> None:
    paths = tuple(OPS._git_lines("ls-files"))

    selected = OPS.components_for_paths(paths, OPS.load_components())

    assert selected


def test_unknown_path_fails_closed() -> None:
    with pytest.raises(OPS.OpsError, match="unclassified"):
        OPS.components_for_paths(("unknown/new-surface.bin",), OPS.load_components())


def test_scanner_iiod_release_assets_select_acquisition_and_deployment_gates() -> None:
    paths = ("runtime/scanner-iiod/iiod", "runtime/scanner-iiod/provenance.json")

    selected = OPS.components_for_paths(paths, OPS.load_components())

    assert {component.name for component in selected} == {"acquisition", "deployment"}
    assert OPS.runtime_impacts_for_paths(paths, selected) == ("acquisition",)
    gates = OPS.selected_gates(paths, selected, all_tests=False, release=False)
    pytest_targets = {
        target
        for gate in gates
        if gate.name.startswith("pytest-components-")
        for target in gate.command
    }
    assert any(target.startswith("tests/acquisition/") for target in pytest_targets)
    assert any(target.startswith("tests/deploy/") for target in pytest_targets)


def test_child_environment_removes_application_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LEO_DATABASE_URL", "postgresql+psycopg:///leo_tracker")
    monkeypatch.setenv("LEO_TEST_DATABASE_URL", "postgresql+psycopg:///leo_tracker")

    environment = OPS.safe_child_environment(needs_postgres=False)

    assert "LEO_DATABASE_URL" not in environment
    assert "LEO_TEST_DATABASE_URL" not in environment


def test_postgres_gate_refuses_production_before_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LEO_TEST_DATABASE_URL", "postgresql+psycopg:///leo_tracker")

    with pytest.raises(OPS.OpsError, match="protected"):
        OPS.safe_child_environment(needs_postgres=True)


def test_delegated_postgres_gate_holds_shared_qualification_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        OPS,
        "safe_child_environment",
        lambda **_kwargs: {"LEO_TEST_DATABASE_URL": "postgresql+psycopg:///leo_qualification"},
    )
    monkeypatch.setattr(OPS, "_local_service_test_delegation_available", lambda _env: True)
    monkeypatch.setattr(OPS, "_service_account_uid", lambda: 123)

    def run(command: tuple[str, ...], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        observed.append(tuple(command))
        return subprocess.CompletedProcess(command, 0, stdout="passed\n")

    monkeypatch.setattr(OPS.subprocess, "run", run)

    result = OPS._execute_gate(OPS.Gate("postgres", ("/bin/true",), needs_postgres=True))

    assert result["exit_code"] == 0
    assert observed[0][4:8] == (
        "/usr/bin/flock",
        "--shared",
        str(OPS.QUALIFICATION_DATABASE_LOCK),
        "/usr/bin/env",
    )


def test_run_as_leo_forces_bytecode_suppression_in_direct_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[tuple[str, ...]] = []

    def run(argv: tuple[str, ...], **_kwargs: object) -> object:
        observed.append(tuple(argv))
        return object()

    monkeypatch.setattr(OPS.subprocess, "run", run)

    OPS._run_as_leo(
        ("/bin/echo", "safe"),
        extra_environment={"HOME": "/var/lib/leo", "PYTHONDONTWRITEBYTECODE": "0"},
    )

    assert observed == [
        (
            "/usr/sbin/runuser",
            "-u",
            "leo",
            "--",
            "/usr/bin/env",
            "HOME=/var/lib/leo",
            "PYTHONDONTWRITEBYTECODE=1",
            "/bin/echo",
            "safe",
        )
    ]


def test_run_as_leo_forces_bytecode_suppression_after_sourced_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[tuple[str, ...]] = []

    def run(argv: tuple[str, ...], **_kwargs: object) -> object:
        observed.append(tuple(argv))
        return object()

    monkeypatch.setattr(OPS.subprocess, "run", run)

    OPS._run_as_leo(("/bin/echo", "two words"), source_environment=True)

    assert observed[0][:-1] == (
        "/usr/sbin/runuser",
        "-u",
        "leo",
        "--",
        "/bin/bash",
        "-c",
    )
    shell = observed[0][-1]
    assert shell.index("source /etc/leo/leo.env") < shell.index("export PYTHONDONTWRITEBYTECODE=1")
    assert shell.endswith("exec /bin/echo 'two words'")


def test_web_change_selects_only_web_component_and_api_impact() -> None:
    selected = OPS.components_for_paths(("web/src/App.tsx",), OPS.load_components())
    gates = OPS.selected_gates(("web/src/App.tsx",), selected, all_tests=False, release=False)

    assert [component.name for component in selected] == ["web"]
    assert {gate.name for gate in gates} == {"web-build", "web-test"}
    assert OPS.runtime_impacts_for_paths(("web/src/App.tsx",), selected) == ("api",)


def test_test_only_change_selects_its_owner_without_runtime_impact() -> None:
    paths = ("tests/processing/test_processing_service.py",)
    selected = OPS.components_for_paths(paths, OPS.load_components())

    assert [component.name for component in selected] == ["processing"]
    assert OPS.runtime_impacts_for_paths(paths, selected) == ()


def test_specific_component_suppresses_conservative_python_fallback() -> None:
    selected = OPS.components_for_paths(("src/leo/api/routes.py",), OPS.load_components())

    assert [component.name for component in selected] == ["api"]
    assert OPS.runtime_impacts_for_paths(("src/leo/api/routes.py",), selected) == ("api",)


def test_only_database_contract_changes_request_migration() -> None:
    components = OPS.load_components()
    source_paths = ("src/leo/processing/worker.py",)
    migration_paths = ("migrations/versions/new.py",)

    source = OPS.components_for_paths(source_paths, components)
    migration = OPS.components_for_paths(migration_paths, components)

    assert "migration" not in OPS.runtime_impacts_for_paths(source_paths, source)
    assert "migration" in OPS.runtime_impacts_for_paths(migration_paths, migration)


def test_worker_entrypoint_change_has_worker_only_runtime_impact() -> None:
    paths = ("src/leo/cli/processing.py",)
    selected = OPS.components_for_paths(paths, OPS.load_components())

    assert [component.name for component in selected] == ["worker-entrypoint"]
    assert OPS.runtime_impacts_for_paths(paths, selected) == ("worker",)


def test_test_infrastructure_change_uses_bounded_exclusive_shard() -> None:
    selected = OPS.components_for_paths(("tests/catalog/conftest.py",), OPS.load_components())
    gates = OPS.selected_gates(
        ("tests/catalog/conftest.py",), selected, all_tests=False, release=False
    )

    assert [component.name for component in selected] == ["test-infrastructure"]
    pytest_gates = tuple(gate for gate in gates if gate.name.startswith("pytest-components-"))
    assert pytest_gates
    assert not any(gate.needs_postgres for gate in pytest_gates)
    assert not any("tests/catalog" in gate.command for gate in pytest_gates)


def test_catalog_change_requires_postgres_and_full_service_impact() -> None:
    selected = OPS.components_for_paths(("src/leo/catalog/repository.py",), OPS.load_components())
    gates = OPS.selected_gates(
        ("src/leo/catalog/repository.py",), selected, all_tests=False, release=False
    )

    pytest_gates = tuple(gate for gate in gates if gate.name.startswith("pytest-components-"))
    assert pytest_gates
    assert all(gate.needs_postgres for gate in pytest_gates)
    assert set(OPS.runtime_impacts_for_paths(("src/leo/catalog/repository.py",), selected)) == {
        "acquisition",
        "api",
        "worker",
    }


def test_source_change_with_owned_test_runs_exact_test_not_whole_component() -> None:
    paths = (
        "src/leo/analysis/standard/final_reports.py",
        "tests/analysis/test_final_trajectory_reports.py",
    )
    selected = OPS.components_for_paths(paths, OPS.load_components())

    gates = OPS.selected_gates(paths, selected, all_tests=False, release=False)

    pytest_gate = next(gate for gate in gates if gate.name.startswith("pytest-changed-"))
    assert "tests/analysis/test_final_trajectory_reports.py" in pytest_gate.command
    assert "tests/analysis" not in pytest_gate.command


@pytest.mark.parametrize(
    ("paths", "gate_prefix"),
    (
        (
            ("tests/processing/test_mixed_rate_standard_native_operational_vertical.py",),
            "pytest-changed-",
        ),
        (("src/leo/processing/service.py",), "pytest-components-"),
    ),
)
def test_current_mixed_rate_vertical_is_sharded_without_historical_cases(
    paths: tuple[str, ...],
    gate_prefix: str,
) -> None:
    path = "tests/processing/test_mixed_rate_standard_native_operational_vertical.py"
    selected = OPS.components_for_paths(paths, OPS.load_components())

    gates = OPS.selected_gates(paths, selected, all_tests=False, release=False)

    pytest_gates = tuple(gate for gate in gates if gate.name.startswith(gate_prefix))
    node_ids = {gate.command[-1] for gate in pytest_gates}
    current_nodes = {
        f"{path}::test_real_postgres_direct_async_capture_analysis_png_and_browser_vertical"
        f"[{rate_hz}]"
        for rate_hz in (10_000_000, 15_000_000, 25_000_000)
    }
    assert current_nodes <= node_ids
    assert all(gate.needs_postgres for gate in pytest_gates if gate.command[-1] in current_nodes)
    assert "tests/processing" not in node_ids
    assert not any("production_single_rx_all_rate" in node_id for node_id in node_ids)


def test_fast_test_checks_changed_source_and_only_changed_portable_tests() -> None:
    paths = (
        "src/leo/analysis/standard/final_reports.py",
        "tests/analysis/test_final_trajectory_reports.py",
        "tests/processing/test_standard_native_operational_vertical.py",
    )
    selected = OPS.components_for_paths(paths, OPS.load_components())

    gates = OPS.selected_gates(
        paths,
        selected,
        all_tests=False,
        release=False,
        fast=True,
    )

    mypy = next(gate for gate in gates if gate.name == "mypy")
    assert mypy.command[-1] == "src/leo/analysis/standard/final_reports.py"
    assert "src" not in mypy.command
    pytest_commands = tuple(
        gate.command for gate in gates if gate.name.startswith("pytest-changed-")
    )
    assert len(pytest_commands) == 1
    assert "tests/analysis/test_final_trajectory_reports.py" in pytest_commands[0]
    assert not any(gate.needs_postgres for gate in gates)


def test_fast_test_is_incompatible_with_complete_test_tiers() -> None:
    for arguments in (("test", "--fast", "--all"), ("test", "--fast", "--release")):
        with pytest.raises(OPS.OpsError, match="cannot be combined"):
            OPS._test(OPS.parser().parse_args(arguments))


def test_python_quality_gates_force_configured_exclusions() -> None:
    paths = ("src/leo/analysis/standard/final_reports.py",)
    selected = OPS.components_for_paths(paths, OPS.load_components())

    gates = OPS.selected_gates(paths, selected, all_tests=False, release=False)

    ruff_check = next(gate for gate in gates if gate.name == "ruff-check")
    ruff_format = next(gate for gate in gates if gate.name == "ruff-format")
    assert "--force-exclude" in ruff_check.command
    assert "--force-exclude" in ruff_format.command


def test_deleted_python_path_selects_owner_without_formatter_file_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(OPS, "ROOT", tmp_path)
    paths = ("src/leo/api/deleted_cache.py", "web/src/App.tsx")
    selected = OPS.components_for_paths(paths, OPS.load_components())

    gates = OPS.selected_gates(paths, selected, all_tests=False, release=False)

    formatter_arguments = {
        argument
        for gate in gates
        if gate.name in {"ruff-check", "ruff-format"}
        for argument in gate.command
    }
    assert "src/leo/api/deleted_cache.py" not in formatter_arguments
    assert not {"ruff-check", "ruff-format"} & {gate.name for gate in gates}
    assert {"web-build", "web-test"} <= {gate.name for gate in gates}
    assert any(gate.name.startswith("pytest-components-") for gate in gates)


def test_test_support_modules_select_owned_tests_but_are_not_collected_as_tests() -> None:
    paths = ("tests/e2e/server.py", "tests/postgres_support.py")
    selected = OPS.components_for_paths(paths, OPS.load_components())

    gates = OPS.selected_gates(paths, selected, all_tests=False, release=False)
    pytest_commands = tuple(
        item
        for gate in gates
        if gate.name.startswith("pytest-")
        for item in gate.command
        if item.endswith(".py")
    )

    assert "tests/e2e/server.py" not in pytest_commands
    assert "tests/postgres_support.py" not in pytest_commands
    assert "tests/test_postgres_test_safety.py" in pytest_commands
    assert "tests/deploy/test_ops_front_door.py" in pytest_commands


def test_all_tests_are_split_into_parallel_component_shards() -> None:
    components = OPS.load_components()
    paths = tuple(OPS._git_lines("ls-files"))

    gates = OPS.selected_gates(paths, components, all_tests=True, release=False)
    pytest_gates = [gate for gate in gates if gate.name.startswith("pytest-")]

    assert len(pytest_gates) >= 20
    assert not any(gate.name == "pytest-components" for gate in pytest_gates)
    catalog = next(gate for gate in pytest_gates if gate.name == "pytest-catalog-1")
    analysis = next(gate for gate in pytest_gates if gate.name == "pytest-analysis-1")
    assert catalog.needs_postgres
    assert not analysis.needs_postgres


def test_explain_is_machine_readable_and_does_not_execute(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(OPS, "changed_paths", lambda **_kwargs: ("web/src/App.tsx",))
    args = OPS.parser().parse_args(["test", "--explain"])

    assert OPS._test(args) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["components"] == ["web"]
    assert {gate["name"] for gate in document["gates"]} == {"web-build", "web-test"}


def test_deploy_plan_for_web_change_cannot_touch_workers_or_acquisition(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    current = "1" * 40
    target = "2" * 40

    def fake_git(*arguments: str) -> str:
        if arguments == ("status", "--porcelain"):
            return ""
        if arguments == ("rev-parse", "origin/main"):
            return target
        raise AssertionError(arguments)

    monkeypatch.setattr(OPS, "_run_git", fake_git)
    monkeypatch.setattr(OPS, "_selected_release_revision", lambda: current)
    monkeypatch.setattr(OPS, "_git_lines", lambda *_arguments: ("web/src/App.tsx",))
    args = OPS.parser().parse_args(["deploy", "--plan"])

    assert OPS._deploy(args) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["services_to_restart"] == ["api"]
    assert not plan["migration_required"]
    assert not plan["worker_fence_required"]
    assert plan["mode"] == "minimal"
    assert plan["capture_policy_id"] is None


def test_deploy_plan_for_test_only_change_has_no_runtime_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = "1" * 40
    target = "2" * 40

    def fake_git(*arguments: str) -> str:
        if arguments == ("status", "--porcelain"):
            return ""
        if arguments == ("rev-parse", "origin/main"):
            return target
        raise AssertionError(arguments)

    monkeypatch.setattr(OPS, "_run_git", fake_git)
    monkeypatch.setattr(OPS, "_selected_release_revision", lambda: current)
    monkeypatch.setattr(
        OPS,
        "_git_lines",
        lambda *_arguments: ("tests/processing/test_processing_service.py",),
    )

    plan = OPS._deployment_plan(OPS.parser().parse_args(["deploy", "--plan"]))

    assert plan["components"] == ["processing"]
    assert plan["impact"] == []
    assert plan["services_to_restart"] == []
    assert plan["mode"] == "no-op"


@pytest.mark.parametrize(
    "paths",
    (
        ("tools/ops.py", "config/ops-components.json"),
        (
            "tools/report_7fea_pss_glrt_deep_dive.py",
            "tools/prototype_7fea_glrt_fractional_epoch.py",
        ),
    ),
)
def test_operator_and_offline_tools_have_no_runtime_work(
    paths: tuple[str, ...],
) -> None:
    selected = OPS.components_for_paths(paths, OPS.load_components())

    assert OPS.runtime_impacts_for_paths(paths, selected) == ()


def test_native_evidence_worker_remains_runtime_authority() -> None:
    native_worker = ("tools/native_evidence_worker.py",)
    selected_native = OPS.components_for_paths(native_worker, OPS.load_components())
    assert set(OPS.runtime_impacts_for_paths(native_worker, selected_native)) == {
        "api",
        "worker",
    }


def test_full_deployment_plan_binds_exact_production_capture_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = "1" * 40
    target = "2" * 40

    def fake_git(*arguments: str) -> str:
        if arguments == ("status", "--porcelain"):
            return ""
        if arguments == ("rev-parse", "origin/main"):
            return target
        raise AssertionError(arguments)

    monkeypatch.setattr(OPS, "_run_git", fake_git)
    monkeypatch.setattr(OPS, "_selected_release_revision", lambda: current)
    monkeypatch.setattr(
        OPS,
        "_git_lines",
        lambda *_arguments: ("deploy/systemd/leo-acquisition.service",),
    )

    plan = OPS._deployment_plan(OPS.parser().parse_args(["deploy", "--plan"]))

    assert plan["capture_policy_id"] == ("production-direct-async-2p5-10-15-25-hold-exact-lo-6-v2")


def test_fast_deployment_plan_uses_selected_api_delta_and_only_restarts_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = "1" * 40
    current_api = "2" * 40
    target = "3" * 40

    def fake_git(*arguments: str) -> str:
        if arguments == ("status", "--porcelain"):
            return ""
        if arguments == ("rev-parse", "origin/main"):
            return target
        raise AssertionError(arguments)

    observed_diff: list[tuple[str, ...]] = []

    def fake_git_lines(*arguments: str) -> tuple[str, ...]:
        observed_diff.append(arguments)
        return (
            "src/leo/presentation/standard_native_pipeline.py",
            "tests/presentation/test_standard_native_pipeline.py",
            "web/src/App.tsx",
        )

    monkeypatch.setattr(OPS, "_run_git", fake_git)
    monkeypatch.setattr(OPS, "_selected_release_revision", lambda: current)
    monkeypatch.setattr(
        OPS,
        "_selected_component_release_revision",
        lambda component: current_api if component == "api" else None,
    )
    monkeypatch.setattr(OPS, "_git_lines", fake_git_lines)

    plan = OPS._deployment_plan(OPS.parser().parse_args(["deploy", "--fast", "--plan"]))

    assert observed_diff == [("diff", "--name-only", f"{current_api}..{target}")]
    assert plan["current_revision"] == current
    assert plan["current_api_revision"] == current_api
    assert plan["comparison_revision"] == current_api
    assert plan["fast_eligible"] is True
    assert plan["fast_rejected_paths"] == []
    assert plan["mode"] == "fast-api-only"
    assert plan["services_to_restart"] == ["api"]
    assert plan["worker_fence_required"] is False
    assert plan["migration_required"] is False
    assert plan["capture_policy_id"] is None


@pytest.mark.parametrize(
    "changed_path",
    (
        "src/leo/contracts/standard_native.py",
        "src/leo/processing/worker.py",
        "migrations/versions/unsafe.py",
        "deploy/systemd/leo-api.service",
        "pyproject.toml",
        "uv.lock",
        "web/package-lock.json",
    ),
)
def test_fast_deployment_plan_rejects_shared_runtime_and_dependency_changes(
    changed_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = "1" * 40
    target = "2" * 40

    def fake_git(*arguments: str) -> str:
        if arguments == ("status", "--porcelain"):
            return ""
        if arguments == ("rev-parse", "origin/main"):
            return target
        raise AssertionError(arguments)

    monkeypatch.setattr(OPS, "_run_git", fake_git)
    monkeypatch.setattr(OPS, "_selected_release_revision", lambda: current)
    monkeypatch.setattr(OPS, "_selected_component_release_revision", lambda _name: current)
    monkeypatch.setattr(
        OPS,
        "_git_lines",
        lambda *_arguments: ("src/leo/api/routes.py", changed_path),
    )

    plan = OPS._deployment_plan(OPS.parser().parse_args(["deploy", "--fast", "--plan"]))

    assert plan["fast_eligible"] is False
    assert plan["fast_rejected_paths"] == [changed_path]


def test_fast_deploy_requires_receipts_and_pre_staged_api_cutover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = "1" * 40
    current_api = "2" * 40
    target = "3" * 40
    plan = {
        "impact": ["api", "worker"],
        "target_revision": target,
        "current_revision": current,
        "current_api_revision": current_api,
        "changed_paths": ["src/leo/presentation/view.py"],
        "fast_eligible": True,
        "fast_rejected_paths": [],
    }
    monkeypatch.setattr(OPS, "_deployment_plan", lambda _args: plan)
    monkeypatch.setattr(OPS.os, "geteuid", lambda: 0)
    checked: list[tuple[str, object]] = []
    monkeypatch.setattr(
        OPS,
        "_require_passing_release_qualification",
        lambda revision: checked.append(("qualification", revision)) or Path("qualified"),
    )
    monkeypatch.setattr(
        OPS,
        "_require_matching_test_receipt",
        lambda **kwargs: checked.append(("tests", kwargs)) or Path("tested"),
    )
    deployed: list[dict[str, object]] = []
    monkeypatch.setattr(
        OPS,
        "_deploy_api_release",
        lambda **kwargs: deployed.append(kwargs) or 0,
    )

    assert OPS._deploy(OPS.parser().parse_args(["deploy", "--fast"])) == 0
    assert checked == [
        ("qualification", current),
        (
            "tests",
            {"target": target, "changed": ("src/leo/presentation/view.py",)},
        ),
    ]
    assert deployed == [
        {
            "target": target,
            "previous": current_api,
            "plan": plan,
            "require_pre_staged": True,
        }
    ]


def test_fast_deploy_requires_published_immutable_target(tmp_path: Path) -> None:
    target = "2" * 40

    with pytest.raises(OPS.OpsError, match="already-staged"):
        OPS._require_pre_staged_release(target, release_root=tmp_path)

    release = tmp_path / "releases" / target
    release.mkdir(parents=True)
    with pytest.raises(OPS.OpsError, match="publication metadata"):
        OPS._require_pre_staged_release(target, release_root=tmp_path)

    metadata = tmp_path / "release-metadata" / f"{target}.txt"
    metadata.parent.mkdir()
    metadata.write_text(f"revision={target}\n")
    assert OPS._require_pre_staged_release(target, release_root=tmp_path) == release


def test_fast_deploy_requires_sealed_healthy_full_deployment_base(tmp_path: Path) -> None:
    target = "2" * 40
    deployment_root = tmp_path / "deployment"
    release_root = tmp_path / "release"
    deployment_root.mkdir()
    receipt = release_root / "qualified" / "receipt.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps({"git_revision": target, "passed": True}))
    receipt.chmod(0o440)
    deployment = deployment_root / f"deploy-{target}.json"
    deployment.write_text(
        json.dumps(
            {
                "kind": "leo-deployment-receipt",
                "mode": "full",
                "target_revision": target,
                "healthy": True,
                "release_qualification_receipt": str(receipt),
            }
        )
    )
    deployment.chmod(0o440)

    assert (
        OPS._require_passing_release_qualification(
            target,
            deployment_root=deployment_root,
            release_evidence_root=release_root,
        )
        == receipt
    )

    receipt.chmod(0o640)
    with pytest.raises(OPS.OpsError, match="sealed healthy full-deployment"):
        OPS._require_passing_release_qualification(
            target,
            deployment_root=deployment_root,
            release_evidence_root=release_root,
        )


def test_stage_only_stages_exact_main_without_cutover_or_rate_receipt(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    current = "1" * 40
    target = "2" * 40

    def fake_git(*arguments: str) -> str:
        if arguments == ("status", "--porcelain"):
            return ""
        if arguments == ("rev-parse", "origin/main"):
            return target
        raise AssertionError(arguments)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("stage-only crossed into the cutover path")

    monkeypatch.setattr(OPS, "_run_git", fake_git)
    monkeypatch.setattr(OPS, "_selected_release_revision", lambda: current)
    monkeypatch.setattr(
        OPS,
        "_git_lines",
        lambda *_arguments: ("deploy/systemd/leo-acquisition.service",),
    )
    monkeypatch.setattr(OPS, "_require_matching_test_receipt", forbidden)
    monkeypatch.setattr(OPS, "_deploy_full_release", forbidden)
    monkeypatch.setattr(OPS, "_deploy_api_release", forbidden)
    monkeypatch.setattr(OPS.os, "geteuid", lambda: 0)
    staged: list[str] = []
    monkeypatch.setattr(OPS, "_stage_release", staged.append)
    args = OPS.parser().parse_args(["deploy", "--stage-only", "--revision", target])

    assert OPS._deploy(args) == 0
    assert staged == [target]
    assert f"STAGED-ONLY revision={target}" in capsys.readouterr().out


@pytest.mark.parametrize("local_head, accepted", (("3" * 40, True), ("4" * 40, False)))
def test_stage_only_accepts_only_main_or_clean_local_head(
    monkeypatch: pytest.MonkeyPatch,
    local_head: str,
    accepted: bool,
) -> None:
    current = "1" * 40
    origin = "2" * 40
    target = "3" * 40

    def fake_git(*arguments: str) -> str:
        if arguments == ("status", "--porcelain"):
            return ""
        if arguments == ("rev-parse", "origin/main"):
            return origin
        if arguments == ("rev-parse", "HEAD"):
            return local_head
        raise AssertionError(arguments)

    monkeypatch.setattr(OPS, "_run_git", fake_git)
    monkeypatch.setattr(OPS, "_selected_release_revision", lambda: current)
    monkeypatch.setattr(OPS, "_git_lines", lambda *_arguments: ("tools/ops.py",))
    arguments = OPS.parser().parse_args(["deploy", "--stage-only", "--revision", target])
    if accepted:
        plan = OPS._deployment_plan(arguments)
        assert plan["target_revision"] == target
        assert plan["mode"] == "no-op"
    else:
        with pytest.raises(OPS.OpsError, match="clean local HEAD"):
            OPS._deployment_plan(arguments)


@pytest.mark.parametrize(
    ("arguments", "message"),
    (
        (("deploy", "--stage-only"), "requires an explicit --revision"),
        (
            ("deploy", "--stage-only", "--revision", "2" * 40, "--plan"),
            "cannot be combined with --plan",
        ),
        (
            ("deploy", "--stage-only", "--revision", "2" * 40, "--full"),
            "cannot be combined with --full",
        ),
        (
            ("deploy", "--stage-only", "--revision", "2" * 40, "--fast"),
            "cannot be combined with --fast",
        ),
        (("deploy", "--full", "--fast"), "cannot be combined with --fast"),
    ),
)
def test_stage_only_rejects_ambiguous_modes(
    arguments: tuple[str, ...],
    message: str,
) -> None:
    with pytest.raises(OPS.OpsError, match=message):
        OPS._deployment_plan(OPS.parser().parse_args(arguments))


def test_stage_only_requires_root_before_staging(monkeypatch: pytest.MonkeyPatch) -> None:
    target = "2" * 40
    monkeypatch.setattr(
        OPS,
        "_deployment_plan",
        lambda _args: {
            "impact": ["systemd"],
            "target_revision": target,
            "current_revision": "1" * 40,
        },
    )
    monkeypatch.setattr(OPS.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(
        OPS,
        "_stage_release",
        lambda _target: pytest.fail("non-root caller must not stage"),
    )
    args = OPS.parser().parse_args(["deploy", "--stage-only", "--revision", target])

    with pytest.raises(OPS.OpsError, match="requires root"):
        OPS._deploy(args)


def test_worker_only_deploy_uses_narrow_component_cutover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = "2" * 40
    plan = {
        "impact": ["worker"],
        "target_revision": target,
        "current_revision": "1" * 40,
        "changed_paths": ["src/leo/processing/worker.py"],
    }
    monkeypatch.setattr(
        OPS,
        "_deployment_plan",
        lambda _args: plan,
    )
    monkeypatch.setattr(OPS.os, "geteuid", lambda: 0)
    monkeypatch.setattr(OPS, "_require_matching_test_receipt", lambda **_kwargs: Path("ok"))
    monkeypatch.setattr(
        OPS,
        "_selected_component_release_revision",
        lambda component: "1" * 40 if component == "worker" else None,
    )
    deployed: list[dict[str, object]] = []
    monkeypatch.setattr(
        OPS,
        "_deploy_component_release",
        lambda **kwargs: deployed.append(kwargs) or 0,
    )
    args = OPS.parser().parse_args(["deploy"])

    assert OPS._deploy(args) == 0
    assert deployed == [
        {"component": "worker", "target": target, "previous": "1" * 40, "plan": plan}
    ]


def test_worker_component_cutover_qualifies_fences_binds_and_restarts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = "2" * 40
    previous = "1" * 40
    release_root = tmp_path / "opt"
    release_root.mkdir()
    worker_environment = tmp_path / "worker.env"
    worker_environment.write_text(f"LEO_PIPELINE_RELEASE_ID={previous}\n")
    order: list[str] = []
    monkeypatch.setattr(OPS, "RELEASE_ROOT", release_root)
    monkeypatch.setattr(OPS, "PRODUCTION_WORKER_ENVIRONMENT", worker_environment)
    monkeypatch.setattr(OPS, "_stage_release", lambda _target: order.append("stage"))
    monkeypatch.setattr(
        OPS, "_release_qualification", lambda _target: order.append("qualify") or tmp_path / "q"
    )
    monkeypatch.setattr(OPS, "_verify_cutover", lambda **_kwargs: order.append("preflight"))
    monkeypatch.setattr(OPS, "_fence_previous_release", lambda **_kwargs: order.append("fence"))
    monkeypatch.setattr(
        OPS,
        "_write_worker_release_environment",
        lambda *_args: order.append("environment"),
    )

    def run(command: tuple[str, ...], **_kwargs: object) -> object:
        order.append("select" if command[-2:] == ("worker", target) else "restart")
        return object()

    monkeypatch.setattr(OPS.subprocess, "run", run)
    monkeypatch.setattr(
        OPS,
        "_write_deployment_receipt",
        lambda **_kwargs: order.append("receipt") or tmp_path / "deployment.json",
    )

    assert (
        OPS._deploy_component_release(
            component="worker",
            target=target,
            previous=previous,
            plan={"mode": "worker-only"},
        )
        == 0
    )
    assert order == [
        "stage",
        "qualify",
        "fence",
        "select",
        "environment",
        "preflight",
        "restart",
        "receipt",
    ]


def test_api_mutating_deploy_requires_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        OPS,
        "_deployment_plan",
        lambda _args: {
            "impact": ["api"],
            "target_revision": "2" * 40,
            "current_revision": "1" * 40,
        },
    )
    monkeypatch.setattr(OPS.os, "geteuid", lambda: 1000)

    with pytest.raises(OPS.OpsError, match="requires root"):
        OPS._deploy(OPS.parser().parse_args(["deploy"]))


def test_matching_receipt_must_cover_every_deployment_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = "2" * 40
    receipt_root = tmp_path / ".leo/test-receipts"
    receipt_root.mkdir(parents=True)
    receipt = {
        "kind": "leo-test-receipt",
        "revision": target,
        "passed": True,
        "plan": {"paths": ["web/src/App.tsx"]},
    }
    (receipt_root / "receipt.json").write_text(json.dumps(receipt))
    monkeypatch.setattr(OPS, "ROOT", tmp_path)

    assert (
        OPS._require_matching_test_receipt(target=target, changed=("web/src/App.tsx",)).name
        == "receipt.json"
    )
    with pytest.raises(OPS.OpsError, match="covers the deployment delta"):
        OPS._require_matching_test_receipt(
            target=target,
            changed=("web/src/App.tsx", "web/src/api.ts"),
        )


def test_fast_iteration_receipt_cannot_authorize_deployment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = "2" * 40
    receipt_root = tmp_path / ".leo/test-receipts"
    receipt_root.mkdir(parents=True)
    receipt = {
        "kind": "leo-test-receipt",
        "revision": target,
        "passed": True,
        "plan": {"tier": "fast-iteration", "paths": ["web/src/App.tsx"]},
    }
    (receipt_root / "receipt.json").write_text(json.dumps(receipt))
    monkeypatch.setattr(OPS, "ROOT", tmp_path)

    with pytest.raises(OPS.OpsError, match="exact-revision test receipt"):
        OPS._require_matching_test_receipt(target=target, changed=("web/src/App.tsx",))


def test_restore_environment_is_atomic_and_rejects_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = tmp_path / "leo.env"
    environment.write_text("LEO_PIPELINE_RELEASE_ID=old\n")
    monkeypatch.setattr(OPS.os, "chown", lambda *_args: None)
    monkeypatch.setattr(OPS.grp, "getgrnam", lambda _name: type("Group", (), {"gr_gid": 1})())

    OPS._restore_environment(environment, b"LEO_PIPELINE_RELEASE_ID=restored\n")

    assert environment.read_bytes() == b"LEO_PIPELINE_RELEASE_ID=restored\n"
    symlink = tmp_path / "linked.env"
    symlink.symlink_to(environment)
    with pytest.raises(OPS.OpsError, match="non-symlink"):
        OPS._restore_environment(symlink, b"unsafe\n")


def test_backup_refuses_nonproduction_database_before_pg_dump() -> None:
    with pytest.raises(OPS.OpsError, match="exact leo_tracker"):
        OPS._backup_database(
            target="2" * 40,
            database_url="postgresql+psycopg:///leo_qualification",
        )


def test_deployment_environment_atomically_binds_reviewed_continuity_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = "2" * 40
    environment = tmp_path / "leo.env"
    original = (
        "# preserved operator comment\n"
        "LEO_DATABASE_URL=postgresql+psycopg:///leo_tracker\n"
        + "\n".join(
            f"{key}=legacy-{index}"
            for index, key in enumerate(OPS._REVIEWED_CONTINUITY_ENVIRONMENT)
        )
        + "\nLEO_PIPELINE_RELEASE_ID="
        + "1" * 40
        + "\nLEO_UNRELATED_SETTING=preserved\n"
    ).encode()
    environment.write_bytes(original)
    monkeypatch.setattr(OPS.os, "chown", lambda *_args: None)
    monkeypatch.setattr(OPS.grp, "getgrnam", lambda _name: type("Group", (), {"gr_gid": 1})())

    OPS._write_deployment_environment(environment, original, target)

    values = OPS._environment_values(environment.read_bytes())
    assert values | OPS._REVIEWED_CONTINUITY_ENVIRONMENT == values
    assert all(
        values[key] == expected for key, expected in OPS._REVIEWED_CONTINUITY_ENVIRONMENT.items()
    )
    assert values["LEO_PIPELINE_RELEASE_ID"] == target
    assert values["LEO_UNRELATED_SETTING"] == "preserved"
    assert environment.read_text().startswith("# preserved operator comment\n")

    OPS._restore_environment(environment, original)
    assert environment.read_bytes() == original


def test_deployment_scanner_authority_matches_the_environment_template() -> None:
    template = OPS._environment_values((ROOT / "deploy/etc/leo/leo.env.example").read_bytes())
    scanner_authority = {
        key: value
        for key, value in OPS._REVIEWED_CONTINUITY_ENVIRONMENT.items()
        if key.startswith("LEO_SCANNER_")
    }

    assert {key: template[key] for key in scanner_authority} == scanner_authority


def test_deployment_environment_refuses_missing_or_duplicate_reviewed_binding(
    tmp_path: Path,
) -> None:
    environment = tmp_path / "leo.env"
    original = b"LEO_PIPELINE_RELEASE_ID=old\nLEO_CAPTURE_PROFILE=old\n"
    environment.write_bytes(original)

    with pytest.raises(OPS.OpsError, match="exactly one binding"):
        OPS._write_deployment_environment(environment, original, "2" * 40)

    assert environment.read_bytes() == original


def test_deployment_environment_adds_new_reviewed_rate_profile_bindings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = "2" * 40
    environment = tmp_path / "leo.env"
    existing = {
        key: value
        for key, value in OPS._REVIEWED_CONTINUITY_ENVIRONMENT.items()
        if key not in OPS._ADDITIVE_REVIEWED_ENVIRONMENT_KEYS
    }
    original = (
        "\n".join(f"{key}=old" for key in existing) + "\nLEO_PIPELINE_RELEASE_ID=" + "1" * 40 + "\n"
    ).encode()
    environment.write_bytes(original)
    monkeypatch.setattr(OPS.os, "chown", lambda *_args: None)
    monkeypatch.setattr(OPS.grp, "getgrnam", lambda _name: type("Group", (), {"gr_gid": 1})())

    OPS._write_deployment_environment(environment, original, target)

    values = OPS._environment_values(environment.read_bytes())
    assert values["LEO_CAPTURE_PROFILE_5M"] == "starlink-ch4-lower-5m-60s-native-bandwidth-v4"
    assert values["LEO_MIXED_RATE_POLICY"] == (
        "production-direct-async-2p5-10-15-25-hold-exact-lo-6-v2"
    )
    assert values["LEO_DIRECT_ASYNC_ENABLED"] == "true"
    assert values["LEO_SCANNER_RUN_SECONDS"] == "300"
    assert values["LEO_PIPELINE_RELEASE_ID"] == target


def test_acquisition_environment_atomically_binds_selected_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = "2" * 40
    environment = tmp_path / "acquisition.env"
    original = (
        "# preserved acquisition override\n"
        f"LEO_ACQUISITION_RELEASE_ID={'1' * 40}\n"
        "LEO_SCANNER_ENABLED=false\n"
        "LEO_MIXED_RATE_POLICY=fixed-2p5-25\n"
    ).encode()
    environment.write_bytes(original)
    monkeypatch.setattr(OPS.os, "chown", lambda *_args: None)
    monkeypatch.setattr(OPS.grp, "getgrnam", lambda _name: type("Group", (), {"gr_gid": 1})())

    OPS._write_acquisition_release_environment(environment, original, target)

    values = OPS._environment_values(environment.read_bytes())
    assert values["LEO_ACQUISITION_RELEASE_ID"] == target
    assert values["LEO_SCANNER_PERSISTENT_IIOD_BINARY_PATH"] == (
        f"/opt/leo-tracker/releases/{target}/runtime/scanner-iiod/iiod"
    )
    assert values["LEO_MIXED_RATE_POLICY"] == "fixed-2p5-25"
    assert values["LEO_SCANNER_ENABLED"] == "false"
    assert environment.read_text().startswith("# preserved acquisition override\n")
    monkeypatch.setattr(OPS, "PRODUCTION_ACQUISITION_ENVIRONMENT", environment)
    OPS._verify_acquisition_environment_revision(target)
    with pytest.raises(OPS.OpsError, match="does not match"):
        OPS._verify_acquisition_environment_revision("3" * 40)


def test_legacy_acquisition_environment_without_scanner_binary_binding_is_restorable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy = "1" * 40
    environment = tmp_path / "acquisition.env"
    environment.write_text(f"LEO_ACQUISITION_RELEASE_ID={legacy}\nLEO_SCANNER_ENABLED=false\n")
    monkeypatch.setattr(OPS, "PRODUCTION_ACQUISITION_ENVIRONMENT", environment)

    OPS._verify_acquisition_environment_revision(legacy)

    binary = Path(f"/opt/leo-tracker/releases/{legacy}/runtime/scanner-iiod/iiod")
    original_is_file = Path.is_file
    monkeypatch.setattr(
        OPS.Path,
        "is_file",
        lambda path: path == binary or original_is_file(path),
    )
    with pytest.raises(OPS.OpsError, match="persistent-hop iiOD binary"):
        OPS._verify_acquisition_environment_revision(legacy)


def test_worker_environment_is_created_and_atomically_binds_selected_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous = "1" * 40
    target = "2" * 40
    environment = tmp_path / "worker.env"
    monkeypatch.setattr(OPS.os, "chown", lambda *_args: None)
    monkeypatch.setattr(OPS.grp, "getgrnam", lambda _name: type("Group", (), {"gr_gid": 1})())

    original = OPS._ensure_worker_release_environment(environment, previous)
    OPS._write_worker_release_environment(environment, original, target)

    assert original == f"LEO_PIPELINE_RELEASE_ID={previous}\n".encode()
    assert OPS._environment_values(environment.read_bytes()) == {"LEO_PIPELINE_RELEASE_ID": target}
    monkeypatch.setattr(OPS, "PRODUCTION_WORKER_ENVIRONMENT", environment)
    OPS._verify_worker_environment_revision(target)
    with pytest.raises(OPS.OpsError, match="does not match"):
        OPS._verify_worker_environment_revision(previous)


def test_worker_environment_rejects_duplicate_release_bindings(
    tmp_path: Path,
) -> None:
    revision = "1" * 40
    environment = tmp_path / "worker.env"
    environment.write_text(
        f"LEO_PIPELINE_RELEASE_ID={revision}\nLEO_PIPELINE_RELEASE_ID={revision}\n"
    )

    with pytest.raises(OPS.OpsError, match="exactly one"):
        OPS._ensure_worker_release_environment(environment, revision)
    with pytest.raises(OPS.OpsError, match="exactly one"):
        OPS._write_worker_release_environment(environment, environment.read_bytes(), revision)


def test_full_deploy_orders_quiesce_select_fence_verify_and_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = "2" * 40
    previous = "1" * 40
    release_root = tmp_path / "opt"
    release = release_root / "releases" / target
    release.mkdir(parents=True)
    environment = tmp_path / "leo.env"
    environment.write_text(
        f"LEO_DATABASE_URL=postgresql+psycopg:///leo_tracker\nLEO_PIPELINE_RELEASE_ID={previous}\n"
    )
    acquisition_environment = tmp_path / "acquisition.env"
    acquisition_environment.write_text(f"LEO_ACQUISITION_RELEASE_ID={previous}\n")
    worker_environment = tmp_path / "worker.env"
    worker_environment.write_text(f"LEO_PIPELINE_RELEASE_ID={previous}\n")
    qualification = tmp_path / "qualification.json"
    qualification.write_text("{}")
    order: list[str] = []
    monkeypatch.setattr(OPS, "RELEASE_ROOT", release_root)
    monkeypatch.setattr(OPS, "PRODUCTION_ENVIRONMENT", environment)
    monkeypatch.setattr(OPS, "PRODUCTION_WORKER_ENVIRONMENT", worker_environment)
    monkeypatch.setattr(OPS, "PRODUCTION_ACQUISITION_ENVIRONMENT", acquisition_environment)
    monkeypatch.setattr(OPS, "_stage_release", lambda _target: order.append("stage"))
    monkeypatch.setattr(OPS, "_release_qualification", lambda _target: qualification)
    monkeypatch.setattr(OPS, "_migration_required", lambda **_kwargs: False)
    monkeypatch.setattr(
        OPS,
        "_selected_selector_revisions",
        lambda: {component: previous for component in OPS._SELECTOR_COMPONENTS},
    )
    monkeypatch.setattr(OPS, "_quiesce_runtime", lambda: order.append("quiesce"))
    monkeypatch.setattr(
        OPS, "_write_deployment_environment", lambda *_args: order.append("environment")
    )
    monkeypatch.setattr(
        OPS, "_write_worker_release_environment", lambda *_args: order.append("worker-environment")
    )
    monkeypatch.setattr(
        OPS,
        "_write_acquisition_release_environment",
        lambda *_args: order.append("acquisition-environment"),
    )
    monkeypatch.setattr(OPS, "_select_all_components", lambda **_kwargs: order.append("select"))
    monkeypatch.setattr(OPS, "_fence_previous_release", lambda **_kwargs: order.append("fence"))
    monkeypatch.setattr(OPS, "_install_units", lambda _release: order.append("units"))
    monkeypatch.setattr(OPS, "_verify_cutover", lambda **_kwargs: order.append("preflight"))
    monkeypatch.setattr(OPS, "_start_runtime", lambda: order.append("start"))
    monkeypatch.setattr(OPS, "_verify_runtime", lambda _target: order.append("health"))
    monkeypatch.setattr(OPS, "_write_deployment_receipt", lambda **_kwargs: tmp_path / "ok")
    assert (
        OPS._deploy_full_release(
            target=target,
            previous=previous,
            plan={"capture_policy_id": OPS.PRODUCTION_CAPTURE_POLICY},
        )
        == 0
    )
    assert order == [
        "stage",
        "quiesce",
        "environment",
        "worker-environment",
        "acquisition-environment",
        "select",
        "fence",
        "units",
        "preflight",
        "start",
        "health",
    ]


def test_install_units_installs_service_drop_ins_as_directory_contents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = tmp_path / "release"
    systemd_root = release / "deploy/systemd"
    drop_in_root = systemd_root / "leo-acquisition.service.d"
    drop_in_root.mkdir(parents=True)
    unit = systemd_root / "leo-acquisition.service"
    unit.write_text("[Service]\nExecStart=/bin/true\n")
    drop_in = drop_in_root / "20-component-environment.conf"
    drop_in.write_text("[Service]\nEnvironmentFile=/etc/leo/acquisition.env\n")
    commands: list[tuple[str, ...]] = []

    def run(command: tuple[str, ...], **_kwargs: object) -> object:
        commands.append(tuple(command))
        return object()

    monkeypatch.setattr(OPS.subprocess, "run", run)

    OPS._install_units(release)

    destination = "/etc/systemd/system/leo-acquisition.service.d"
    assert commands == [
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
        (
            "/usr/bin/install",
            "-d",
            "-o",
            "root",
            "-g",
            "root",
            "-m",
            "0755",
            destination,
        ),
        (
            "/usr/bin/install",
            "-o",
            "root",
            "-g",
            "root",
            "-m",
            "0644",
            str(drop_in),
            destination,
        ),
        ("/usr/bin/systemd-analyze", "verify", str(unit)),
        ("/usr/bin/systemctl", "daemon-reload"),
    ]


def test_full_deploy_rolls_back_no_migration_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = "2" * 40
    previous = "1" * 40
    release_root = tmp_path / "opt"
    (release_root / "releases" / target).mkdir(parents=True)
    (release_root / "releases" / previous).mkdir(parents=True)
    environment = tmp_path / "leo.env"
    old_environment = (
        "LEO_DATABASE_URL=postgresql+psycopg:///leo_tracker\n"
        + "\n".join(
            f"{key}=legacy-{index}"
            for index, key in enumerate(OPS._REVIEWED_CONTINUITY_ENVIRONMENT)
        )
        + f"\nLEO_PIPELINE_RELEASE_ID={previous}\n"
    ).encode()
    environment.write_bytes(old_environment)
    acquisition_environment = tmp_path / "acquisition.env"
    old_acquisition_environment = f"LEO_ACQUISITION_RELEASE_ID={previous}\n".encode()
    acquisition_environment.write_bytes(old_acquisition_environment)
    worker_environment = tmp_path / "worker.env"
    old_worker_environment = f"LEO_PIPELINE_RELEASE_ID={previous}\n".encode()
    worker_environment.write_bytes(old_worker_environment)
    monkeypatch.setattr(OPS, "RELEASE_ROOT", release_root)
    monkeypatch.setattr(OPS, "PRODUCTION_ENVIRONMENT", environment)
    monkeypatch.setattr(OPS, "PRODUCTION_WORKER_ENVIRONMENT", worker_environment)
    monkeypatch.setattr(OPS, "PRODUCTION_ACQUISITION_ENVIRONMENT", acquisition_environment)
    previous_api = "3" * 40
    selectors = {
        "global": previous,
        "api": previous_api,
        "worker": previous,
        "acquisition": previous,
    }
    order: list[str] = []
    write_deployment_environment = OPS._write_deployment_environment
    write_acquisition_release_environment = OPS._write_acquisition_release_environment
    write_worker_release_environment = OPS._write_worker_release_environment
    restore_environment = OPS._restore_environment
    monkeypatch.setattr(OPS, "_stage_release", lambda _target: order.append("stage"))
    monkeypatch.setattr(OPS, "_release_qualification", lambda _target: tmp_path / "receipt")
    monkeypatch.setattr(OPS, "_migration_required", lambda **_kwargs: False)
    monkeypatch.setattr(OPS, "_selected_selector_revisions", lambda: selectors)
    monkeypatch.setattr(OPS, "_quiesce_runtime", lambda: order.append("quiesce"))
    monkeypatch.setattr(OPS.os, "chown", lambda *_args: None)
    monkeypatch.setattr(OPS.grp, "getgrnam", lambda _name: type("Group", (), {"gr_gid": 1})())

    def write_target(path: Path, content: bytes, revision: str) -> None:
        order.append("target-environment")
        write_deployment_environment(path, content, revision)

    monkeypatch.setattr(OPS, "_write_deployment_environment", write_target)

    def write_worker_target(path: Path, content: bytes, revision: str) -> None:
        order.append("target-worker-environment")
        write_worker_release_environment(path, content, revision)

    monkeypatch.setattr(OPS, "_write_worker_release_environment", write_worker_target)

    def write_acquisition_target(path: Path, content: bytes, revision: str) -> None:
        order.append("target-acquisition-environment")
        write_acquisition_release_environment(path, content, revision)

    monkeypatch.setattr(
        OPS,
        "_write_acquisition_release_environment",
        write_acquisition_target,
    )
    monkeypatch.setattr(
        OPS, "_select_all_components", lambda **_kwargs: order.append("target-selectors")
    )
    monkeypatch.setattr(OPS, "_fence_previous_release", lambda **_kwargs: order.append("fence"))
    monkeypatch.setattr(
        OPS,
        "_install_units",
        lambda release: order.append(
            "previous-units" if release.name == previous else "target-units"
        ),
    )
    monkeypatch.setattr(OPS, "_verify_cutover", lambda **_kwargs: order.append("preflight"))
    start_count = 0

    def start_runtime() -> None:
        nonlocal start_count
        start_count += 1
        order.append("target-start" if start_count == 1 else "previous-start")

    monkeypatch.setattr(OPS, "_start_runtime", start_runtime)

    def reject_target(_target: str) -> None:
        order.append("target-health")
        raise RuntimeError("bad")

    monkeypatch.setattr(
        OPS,
        "_verify_runtime",
        reject_target,
    )

    def restore_previous(path: Path, content: bytes) -> None:
        if path == environment:
            assert OPS._environment_values(path.read_bytes())["LEO_CAPTURE_PROFILE"].endswith(
                "native-bandwidth-v4"
            )
            assert content == old_environment
            order.append("previous-environment")
        elif path == acquisition_environment:
            assert path == acquisition_environment
            assert (
                OPS._environment_values(path.read_bytes())["LEO_ACQUISITION_RELEASE_ID"] == target
            )
            assert content == old_acquisition_environment
            order.append("previous-acquisition-environment")
        else:
            assert path == worker_environment
            assert OPS._environment_values(path.read_bytes())["LEO_PIPELINE_RELEASE_ID"] == target
            assert content == old_worker_environment
            order.append("previous-worker-environment")
        restore_environment(path, content)

    monkeypatch.setattr(OPS, "_restore_environment", restore_previous)
    monkeypatch.setattr(
        OPS,
        "_select_component_revisions",
        lambda *, release, revisions: order.append(
            "previous-selectors" if revisions == selectors else "unexpected-selectors"
        ),
    )
    monkeypatch.setattr(
        OPS,
        "_verify_restored_runtime",
        lambda revisions: order.append(
            "previous-health" if revisions == selectors else "unexpected-health"
        ),
    )
    monkeypatch.setattr(
        OPS,
        "_fence_target_release_for_rollback",
        lambda **kwargs: order.append(
            "target-fence"
            if kwargs
            == {
                "release": release_root / "releases" / previous,
                "target": target,
                "previous": previous,
            }
            else "unexpected-fence"
        ),
    )
    with pytest.raises(RuntimeError, match="bad"):
        OPS._deploy_full_release(
            target=target,
            previous=previous,
            plan={"capture_policy_id": OPS.PRODUCTION_CAPTURE_POLICY},
        )
    assert order == [
        "stage",
        "quiesce",
        "target-environment",
        "target-worker-environment",
        "target-acquisition-environment",
        "target-selectors",
        "fence",
        "target-units",
        "preflight",
        "target-start",
        "target-health",
        "quiesce",
        "previous-environment",
        "previous-worker-environment",
        "previous-acquisition-environment",
        "previous-selectors",
        "previous-units",
        "target-fence",
        "previous-start",
        "previous-health",
    ]
    assert environment.read_bytes() == old_environment
    assert acquisition_environment.read_bytes() == old_acquisition_environment


def test_migrated_target_start_failure_is_quiesced_and_not_rolled_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = "2" * 40
    previous = "1" * 40
    release_root = tmp_path / "opt"
    (release_root / "releases" / target).mkdir(parents=True)
    environment = tmp_path / "leo.env"
    environment.write_text(
        f"LEO_DATABASE_URL=postgresql+psycopg:///leo_tracker\nLEO_PIPELINE_RELEASE_ID={previous}\n"
    )
    acquisition_environment = tmp_path / "acquisition.env"
    acquisition_environment.write_text(f"LEO_ACQUISITION_RELEASE_ID={previous}\n")
    worker_environment = tmp_path / "worker.env"
    worker_environment.write_text(f"LEO_PIPELINE_RELEASE_ID={previous}\n")
    order: list[str] = []
    monkeypatch.setattr(OPS, "RELEASE_ROOT", release_root)
    monkeypatch.setattr(OPS, "PRODUCTION_ENVIRONMENT", environment)
    monkeypatch.setattr(OPS, "PRODUCTION_WORKER_ENVIRONMENT", worker_environment)
    monkeypatch.setattr(OPS, "PRODUCTION_ACQUISITION_ENVIRONMENT", acquisition_environment)
    monkeypatch.setattr(OPS, "_stage_release", lambda _target: None)
    monkeypatch.setattr(OPS, "_release_qualification", lambda _target: tmp_path / "receipt")
    monkeypatch.setattr(OPS, "_migration_required", lambda **_kwargs: True)
    monkeypatch.setattr(
        OPS,
        "_selected_selector_revisions",
        lambda: {component: previous for component in OPS._SELECTOR_COMPONENTS},
    )
    monkeypatch.setattr(OPS, "_quiesce_runtime", lambda: order.append("quiesce"))
    monkeypatch.setattr(OPS, "_backup_database", lambda **_kwargs: tmp_path / "backup")
    monkeypatch.setattr(OPS, "_run_as_leo", lambda *_args, **_kwargs: order.append("migration"))
    monkeypatch.setattr(OPS, "_write_deployment_environment", lambda *_args: None)
    monkeypatch.setattr(OPS, "_write_worker_release_environment", lambda *_args: None)
    monkeypatch.setattr(OPS, "_write_acquisition_release_environment", lambda *_args: None)
    monkeypatch.setattr(OPS, "_select_all_components", lambda **_kwargs: None)
    monkeypatch.setattr(OPS, "_fence_previous_release", lambda **_kwargs: None)
    monkeypatch.setattr(OPS, "_install_units", lambda _release: None)
    monkeypatch.setattr(OPS, "_verify_cutover", lambda **_kwargs: order.append("preflight"))

    def fail_start() -> None:
        order.append("start")
        raise RuntimeError("partial target start")

    monkeypatch.setattr(
        OPS,
        "_start_runtime",
        fail_start,
    )
    monkeypatch.setattr(
        OPS,
        "_restore_full_release",
        lambda **_kwargs: pytest.fail("schema-changing deployment must not start old code"),
    )
    with pytest.raises(RuntimeError, match="partial target start"):
        OPS._deploy_full_release(
            target=target,
            previous=previous,
            plan={"capture_policy_id": OPS.PRODUCTION_CAPTURE_POLICY},
        )

    assert order == ["quiesce", "migration", "preflight", "start", "quiesce"]


def test_quiesce_stops_complete_unit_inventory_then_verifies_no_active_units(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[tuple[str, ...]] = []

    def run(command, **_kwargs):
        commands.append(tuple(command))
        return type("Result", (), {"returncode": 0, "stdout": ""})()

    monkeypatch.setattr(
        OPS.subprocess,
        "run",
        run,
    )

    OPS._quiesce_runtime()

    assert commands == [
        ("/usr/bin/systemctl", "stop", *OPS._LEO_TIMER_UNITS),
        ("/usr/bin/systemctl", "stop", *OPS._LEO_SERVICE_UNITS),
        (
            "/usr/bin/systemctl",
            "kill",
            "--kill-who=all",
            "--signal=SIGKILL",
            OPS._WORKER_UNIT_PATTERN,
        ),
        ("/usr/bin/systemctl", "stop", OPS._WORKER_UNIT_PATTERN),
        (
            "/usr/bin/systemctl",
            "list-units",
            "leo-*",
            "--state=active,activating,reloading",
            "--no-legend",
            "--no-pager",
            "--plain",
        ),
    ]
    assert {
        "leo-acquisition-soak.service",
        "leo-qualification.service",
        "leo-release-qualification.service",
        "leo-reconcile.service",
        "leo-retention.service",
        "leo-tle-collection.service",
    } <= set(OPS._LEO_SERVICE_UNITS)
    assert {
        "leo-qualification.timer",
        "leo-release-qualification.timer",
        "leo-reconcile.timer",
        "leo-retention.timer",
        "leo-tle-collection.timer",
    } == set(OPS._LEO_TIMER_UNITS)
    unit_root = ROOT / "deploy/systemd"
    assert set(OPS._LEO_SERVICE_UNITS) == {
        path.name for path in unit_root.glob("leo-*.service") if path.name != "leo-worker@.service"
    }
    assert set(OPS._LEO_TIMER_UNITS) == {path.name for path in unit_root.glob("leo-*.timer")}


def test_quiesce_fails_closed_when_any_leo_unit_remains_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def run(command, **_kwargs):
        stdout = ""
        if "list-units" in command:
            stdout = "leo-acquisition-soak.service loaded active running soak\n"
        return type("Result", (), {"returncode": 0, "stdout": stdout})()

    monkeypatch.setattr(OPS.subprocess, "run", run)

    with pytest.raises(OPS.OpsError, match="leo-acquisition-soak.service"):
        OPS._quiesce_runtime()


def test_restore_refuses_to_mutate_previous_runtime_until_target_is_stopped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        OPS,
        "_quiesce_runtime",
        lambda: (_ for _ in ()).throw(OPS.OpsError("target still active")),
    )
    monkeypatch.setattr(
        OPS,
        "_restore_environment",
        lambda *_args: calls.append("environment"),
    )

    with pytest.raises(OPS.OpsError, match="target still active"):
        OPS._restore_full_release(
            selector_revisions={
                "global": "1" * 40,
                "api": "3" * 40,
                "worker": "1" * 40,
                "acquisition": "1" * 40,
            },
            selector_release=tmp_path / "target",
            environment_path=tmp_path / "leo.env",
            old_environment=b"old",
            worker_environment_path=tmp_path / "worker.env",
            old_worker_environment=b"old-worker",
            acquisition_environment_path=tmp_path / "acquisition.env",
            old_acquisition_environment=b"old-acquisition",
        )

    assert calls == []


def test_failed_previous_runtime_health_is_quiesced_again(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selectors = {component: "1" * 40 for component in OPS._SELECTOR_COMPONENTS}
    order: list[str] = []
    monkeypatch.setattr(OPS, "RELEASE_ROOT", tmp_path / "opt")
    monkeypatch.setattr(OPS, "_quiesce_runtime", lambda: order.append("quiesce"))
    monkeypatch.setattr(OPS, "_restore_environment", lambda *_args: order.append("environment"))
    monkeypatch.setattr(
        OPS, "_select_component_revisions", lambda **_kwargs: order.append("selectors")
    )
    monkeypatch.setattr(OPS, "_install_units", lambda *_args: order.append("units"))
    monkeypatch.setattr(
        OPS, "_fence_target_release_for_rollback", lambda **_kwargs: order.append("fence")
    )
    monkeypatch.setattr(OPS, "_start_runtime", lambda: order.append("start"))

    def reject_health(_selectors: dict[str, str]) -> None:
        order.append("health")
        raise RuntimeError("previous runtime unhealthy")

    monkeypatch.setattr(OPS, "_verify_restored_runtime", reject_health)

    with pytest.raises(RuntimeError, match="previous runtime unhealthy"):
        OPS._restore_full_release(
            selector_revisions=selectors,
            selector_release=tmp_path / ("2" * 40),
            environment_path=tmp_path / "leo.env",
            old_environment=b"old",
            worker_environment_path=tmp_path / "worker.env",
            old_worker_environment=b"old-worker",
            acquisition_environment_path=tmp_path / "acquisition.env",
            old_acquisition_environment=b"old-acquisition",
        )

    assert order == [
        "quiesce",
        "environment",
        "environment",
        "environment",
        "selectors",
        "units",
        "fence",
        "start",
        "health",
        "quiesce",
    ]


def test_rollback_fence_cancels_only_active_target_release_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[str, ...], bool]] = []
    monkeypatch.setattr(
        OPS,
        "_run_as_leo",
        lambda command, *, source_environment, capture_output: calls.append(
            (command, source_environment)
        ),
    )
    target = "2" * 40
    previous = "1" * 40
    release = tmp_path / previous

    OPS._fence_target_release_for_rollback(
        release=release,
        target=target,
        previous=previous,
    )

    assert len(calls) == 1
    command, source_environment = calls[0]
    assert source_environment is True
    assert command[0] == str(release / ".venv/bin/leo")
    assert command[1:4] == ("process", "stop-and-fence", "--release")
    assert command[4] == target
    assert command[command.index("--operator") + 1] == "ops-rollback"
    assert command[command.index("--reason") + 1] == f"rollback replacement by {previous}"
    assert "--all-active-for-release" in command
    assert "--yes" in command
    assert "--json" in command


def test_rollback_fence_treats_exact_absent_target_release_as_noop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = "2" * 40
    previous = "1" * 40

    def absent_target(*_args, **_kwargs):
        document = {
            "schema_version": 1,
            "command": "process.stop-and-fence",
            "ok": False,
            "exit_code": 11,
            "message": f"pipeline release is absent: {target}",
            "payload": None,
        }
        raise subprocess.CalledProcessError(
            11,
            ("leo", "process", "stop-and-fence"),
            output=json.dumps(document),
        )

    monkeypatch.setattr(OPS, "_run_as_leo", absent_target)

    OPS._fence_target_release_for_rollback(
        release=tmp_path / previous,
        target=target,
        previous=previous,
    )

    assert capsys.readouterr().out == f"FENCE-NO-OP release={target} reason=absent\n"


def test_rollback_fence_reads_trailing_json_after_validator_prelude(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = "2" * 40
    previous = "1" * 40
    document = {
        "schema_version": 1,
        "command": "process.stop-and-fence",
        "ok": False,
        "exit_code": 11,
        "message": f"pipeline release is absent: {target}",
        "payload": None,
    }

    def absent_target(*_args, **_kwargs):
        prelude = "PRODUCTION ENVIRONMENT VALIDATED\n- release selector is exact\n"
        raise subprocess.CalledProcessError(
            11,
            ("leo", "process", "stop-and-fence"),
            output=prelude + json.dumps(document, indent=2) + "\n",
        )

    monkeypatch.setattr(OPS, "_run_as_leo", absent_target)

    OPS._fence_target_release_for_rollback(
        release=tmp_path / previous,
        target=target,
        previous=previous,
    )

    assert capsys.readouterr().out == f"FENCE-NO-OP release={target} reason=absent\n"


def test_rollback_fence_rejects_unrelated_not_found(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = "2" * 40
    previous = "1" * 40

    def unrelated_not_found(*_args, **_kwargs):
        document = {
            "command": "process.stop-and-fence",
            "exit_code": 11,
            "message": "database is absent",
            "payload": None,
        }
        raise subprocess.CalledProcessError(
            11,
            ("leo", "process", "stop-and-fence"),
            output=json.dumps(document),
        )

    monkeypatch.setattr(OPS, "_run_as_leo", unrelated_not_found)

    with pytest.raises(subprocess.CalledProcessError):
        OPS._fence_target_release_for_rollback(
            release=tmp_path / previous,
            target=target,
            previous=previous,
        )


def test_restored_runtime_verifies_divergent_selectors_and_service_health(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selectors = {
        "global": "1" * 40,
        "api": "3" * 40,
        "worker": "1" * 40,
        "acquisition": "1" * 40,
    }
    observed_components = {
        component: revision for component, revision in selectors.items() if component != "global"
    }
    health: list[str] = []
    monkeypatch.setattr(OPS, "_selected_release_revision", lambda: selectors["global"])
    monkeypatch.setattr(
        OPS,
        "_selected_component_release_revision",
        lambda component: observed_components[component],
    )
    monkeypatch.setattr(OPS, "_wait_for_api", lambda: health.append("api"))
    monkeypatch.setattr(OPS, "_verify_worker_environment_revision", lambda _revision: None)
    monkeypatch.setattr(OPS, "_verify_acquisition_environment_revision", lambda _revision: None)
    monkeypatch.setattr(
        OPS.subprocess,
        "run",
        lambda *_args, **_kwargs: type(
            "Result", (), {"stdout": "active\nactive\nactive\nactive\n"}
        )(),
    )

    OPS._verify_restored_runtime(selectors)

    assert health == ["api"]
    observed_components["api"] = "4" * 40
    with pytest.raises(OPS.OpsError, match="api selector"):
        OPS._verify_restored_runtime(selectors)


def test_api_health_wait_retries_boundedly(monkeypatch: pytest.MonkeyPatch) -> None:
    return_codes = iter((7, 7, 0))
    sleeps: list[float] = []
    monkeypatch.setattr(
        OPS.subprocess,
        "run",
        lambda *_args, **_kwargs: type("Result", (), {"returncode": next(return_codes)})(),
    )
    monkeypatch.setattr(OPS.time, "sleep", sleeps.append)

    OPS._wait_for_api(timeout_seconds=1.0)

    assert sleeps == [0.25, 0.25]
