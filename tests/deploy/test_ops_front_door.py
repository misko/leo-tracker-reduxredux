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

    pytest_gate = next(gate for gate in gates if gate.name == "pytest-components")
    assert "tests/analysis/test_final_trajectory_reports.py" in pytest_gate.command
    assert "tests/analysis" not in pytest_gate.command


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


def test_non_api_mutating_deploy_is_refused_before_root_or_service_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        OPS,
        "_deployment_plan",
        lambda _args: {
            "impact": ["worker"],
            "target_revision": "2" * 40,
            "current_revision": "1" * 40,
        },
    )
    args = OPS.parser().parse_args(["deploy"])

    with pytest.raises(OPS.OpsError, match="API/web-only"):
        OPS._deploy(args)


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
