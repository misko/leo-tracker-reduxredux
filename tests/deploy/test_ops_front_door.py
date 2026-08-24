from __future__ import annotations

import importlib.util
import json
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


def test_web_change_selects_only_web_component_and_api_impact() -> None:
    selected = OPS.components_for_paths(("web/src/App.tsx",), OPS.load_components())
    gates = OPS.selected_gates(("web/src/App.tsx",), selected, all_tests=False, release=False)

    assert [component.name for component in selected] == ["web"]
    assert {gate.name for gate in gates} == {"web-build", "web-test"}
    assert {impact for component in selected for impact in component.impact} == {"api"}


def test_test_infrastructure_change_uses_bounded_exclusive_shard() -> None:
    selected = OPS.components_for_paths(("tests/catalog/conftest.py",), OPS.load_components())
    gates = OPS.selected_gates(
        ("tests/catalog/conftest.py",), selected, all_tests=False, release=False
    )

    assert [component.name for component in selected] == ["test-infrastructure"]
    pytest_gate = next(gate for gate in gates if gate.name == "pytest-components")
    assert not pytest_gate.needs_postgres
    assert "tests/catalog" not in pytest_gate.command


def test_catalog_change_requires_postgres_and_full_service_impact() -> None:
    selected = OPS.components_for_paths(("src/leo/catalog/repository.py",), OPS.load_components())
    gates = OPS.selected_gates(
        ("src/leo/catalog/repository.py",), selected, all_tests=False, release=False
    )

    pytest_gate = next(gate for gate in gates if gate.name == "pytest-components")
    assert pytest_gate.needs_postgres
    assert {impact for component in selected for impact in component.impact} == {
        "acquisition",
        "api",
        "migration",
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
    assert {"pytest-components", "web-build", "web-test"} <= {gate.name for gate in gates}


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


def test_non_api_mutating_deploy_automatically_selects_full_cutover(
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
    deployed: list[dict[str, object]] = []
    monkeypatch.setattr(
        OPS,
        "_deploy_full_release",
        lambda **kwargs: deployed.append(kwargs) or 0,
    )
    args = OPS.parser().parse_args(["deploy"])

    assert OPS._deploy(args) == 0
    assert deployed == [{"target": target, "previous": "1" * 40, "plan": plan}]


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


def test_deployment_environment_refuses_missing_or_duplicate_reviewed_binding(
    tmp_path: Path,
) -> None:
    environment = tmp_path / "leo.env"
    original = b"LEO_PIPELINE_RELEASE_ID=old\nLEO_CAPTURE_PROFILE=old\n"
    environment.write_bytes(original)

    with pytest.raises(OPS.OpsError, match="exactly one binding"):
        OPS._write_deployment_environment(environment, original, "2" * 40)

    assert environment.read_bytes() == original


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
    qualification = tmp_path / "qualification.json"
    qualification.write_text("{}")
    order: list[str] = []
    monkeypatch.setattr(OPS, "RELEASE_ROOT", release_root)
    monkeypatch.setattr(OPS, "PRODUCTION_ENVIRONMENT", environment)
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
    monkeypatch.setattr(OPS, "_select_all_components", lambda **_kwargs: order.append("select"))
    monkeypatch.setattr(OPS, "_fence_previous_release", lambda **_kwargs: order.append("fence"))
    monkeypatch.setattr(OPS, "_install_units", lambda _release: order.append("units"))
    monkeypatch.setattr(OPS, "_verify_cutover", lambda **_kwargs: order.append("preflight"))
    monkeypatch.setattr(OPS, "_start_runtime", lambda: order.append("start"))
    monkeypatch.setattr(OPS, "_verify_runtime", lambda _target: order.append("health"))
    monkeypatch.setattr(OPS, "_write_deployment_receipt", lambda **_kwargs: tmp_path / "ok")

    assert OPS._deploy_full_release(target=target, previous=previous, plan={}) == 0
    assert order == [
        "stage",
        "quiesce",
        "environment",
        "select",
        "fence",
        "units",
        "preflight",
        "start",
        "health",
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
    monkeypatch.setattr(OPS, "RELEASE_ROOT", release_root)
    monkeypatch.setattr(OPS, "PRODUCTION_ENVIRONMENT", environment)
    previous_api = "3" * 40
    selectors = {
        "global": previous,
        "api": previous_api,
        "worker": previous,
        "acquisition": previous,
    }
    order: list[str] = []
    write_deployment_environment = OPS._write_deployment_environment
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
        assert OPS._environment_values(path.read_bytes())["LEO_CAPTURE_PROFILE"].endswith(
            "continuity-v2"
        )
        assert content == old_environment
        order.append("previous-environment")
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
        OPS._deploy_full_release(target=target, previous=previous, plan={})
    assert order == [
        "stage",
        "quiesce",
        "target-environment",
        "target-selectors",
        "fence",
        "target-units",
        "preflight",
        "target-start",
        "target-health",
        "quiesce",
        "previous-environment",
        "previous-selectors",
        "previous-units",
        "target-fence",
        "previous-start",
        "previous-health",
    ]
    assert environment.read_bytes() == old_environment


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
    quiesces: list[str] = []
    monkeypatch.setattr(OPS, "RELEASE_ROOT", release_root)
    monkeypatch.setattr(OPS, "PRODUCTION_ENVIRONMENT", environment)
    monkeypatch.setattr(OPS, "_stage_release", lambda _target: None)
    monkeypatch.setattr(OPS, "_release_qualification", lambda _target: tmp_path / "receipt")
    monkeypatch.setattr(OPS, "_migration_required", lambda **_kwargs: True)
    monkeypatch.setattr(
        OPS,
        "_selected_selector_revisions",
        lambda: {component: previous for component in OPS._SELECTOR_COMPONENTS},
    )
    monkeypatch.setattr(OPS, "_quiesce_runtime", lambda: quiesces.append("quiesce"))
    monkeypatch.setattr(OPS, "_backup_database", lambda **_kwargs: tmp_path / "backup")
    monkeypatch.setattr(OPS, "_run_as_leo", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(OPS, "_write_deployment_environment", lambda *_args: None)
    monkeypatch.setattr(OPS, "_select_all_components", lambda **_kwargs: None)
    monkeypatch.setattr(OPS, "_fence_previous_release", lambda **_kwargs: None)
    monkeypatch.setattr(OPS, "_install_units", lambda _release: None)
    monkeypatch.setattr(OPS, "_verify_cutover", lambda **_kwargs: None)
    monkeypatch.setattr(
        OPS,
        "_start_runtime",
        lambda: (_ for _ in ()).throw(RuntimeError("partial target start")),
    )
    monkeypatch.setattr(
        OPS,
        "_restore_full_release",
        lambda **_kwargs: pytest.fail("schema-changing deployment must not start old code"),
    )

    with pytest.raises(RuntimeError, match="partial target start"):
        OPS._deploy_full_release(target=target, previous=previous, plan={})

    assert quiesces == ["quiesce", "quiesce"]


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
        )

    assert order == [
        "quiesce",
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
        lambda command, *, source_environment: calls.append((command, source_environment)),
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
