from __future__ import annotations

import json

import finite_set_reset_cohort as runner
import pytest


def unit(unit_id, sessions):
    return {
        "unit_id": unit_id,
        "size": len(sessions),
        "session_ids": list(sessions),
    }


def parent(unit_id, run_id):
    return {
        "schema": "finite-set-grouped-cohort/v1",
        "run_id": run_id,
        "unit": {"unit_id": unit_id},
        "fit": {"marker": unit_id},
    }


def test_supports_exactly_all_twenty_four_dq_units():
    assert len(runner.SUPPORTED_UNITS) == 24
    assert len(set(runner.SUPPORTED_UNITS)) == 24
    assert runner.SUPPORTED_UNITS[0] == "DS10-D01"
    assert runner.SUPPORTED_UNITS[-1] == "DS11-Q04"
    assert all("-S" not in value for value in runner.SUPPORTED_UNITS)


def test_parent_selection_has_one_explicit_legacy_retry():
    assert runner.expected_parent_run("DS10-Q01") == runner.LEGACY_RETRY_PARENT_RUN
    for unit_id in runner.SUPPORTED_UNITS:
        if unit_id != "DS10-Q01":
            assert runner.expected_parent_run(unit_id) == runner.STANDARD_PARENT_RUN
    with pytest.raises(ValueError, match="frozen DS10/DS11 D/Q"):
        runner.expected_parent_run("DS10-S01")


def test_legacy_parent_is_exactly_validated_before_validator_normalization():
    source = parent("DS10-Q01", runner.LEGACY_RETRY_PARENT_RUN)
    normalized, receipt = runner.validate_parent_identity(source, "DS10-Q01")
    assert source["run_id"] == runner.LEGACY_RETRY_PARENT_RUN
    assert normalized["run_id"] == runner.STANDARD_PARENT_RUN
    assert receipt == {
        "run_id": runner.LEGACY_RETRY_PARENT_RUN,
        "legacy_retry_parent": True,
        "validator_run_id_normalization": "legacy_retry_to_standard_schema_identity",
    }
    wrong = parent("DS10-Q01", runner.STANDARD_PARENT_RUN)
    with pytest.raises(ValueError, match="declared cohort source"):
        runner.validate_parent_identity(wrong, "DS10-Q01")


def test_standard_parent_is_not_substituted():
    source = parent("DS11-D03", runner.STANDARD_PARENT_RUN)
    normalized, receipt = runner.validate_parent_identity(source, "DS11-D03")
    assert normalized == source
    assert normalized is not source
    assert receipt["legacy_retry_parent"] is False
    changed = parent("DS11-D03", runner.LEGACY_RETRY_PARENT_RUN)
    with pytest.raises(ValueError, match="declared cohort source"):
        runner.validate_parent_identity(changed, "DS11-D03")


@pytest.mark.parametrize(
    ("unit_id", "sessions"),
    [
        ("DS10-D08", ("a", "b")),
        ("DS11-Q04", ("a", "b", "c", "d")),
    ],
)
def test_unit_shape_requires_declared_pair_or_quad(unit_id, sessions):
    assert runner.validate_unit_shape(unit_id, unit(unit_id, sessions)) == len(sessions)
    broken = unit(unit_id, sessions[:-1])
    with pytest.raises(ValueError, match="capture geometry"):
        runner.validate_unit_shape(unit_id, broken)


def test_source_paths_bind_parent_children_validators_and_numerical_core(tmp_path):
    root = tmp_path / "reports" / "2026_10_02_multiscan_localization"
    root.mkdir(parents=True)
    selection = root / "selection.json"
    parent_path = root / "parent.json"
    inherited = root / "inherited-validator.py"
    source = {"source_hashes": {str(inherited.resolve()): "digest"}}
    children = [unit("DS10-S01", ("capture-a",)), unit("DS10-S02", ("capture-b",))]
    paths = runner.source_paths(root, selection, parent_path, source, children)
    names = {path.name for path in paths}
    assert {
        "finite_set_reset_multistart.py",
        "finite_set_capture_reset.py",
        "alias_family_joint.py",
        "capture_reset_gn.py",
        "inherited-validator.py",
        "selection.json",
        "parent.json",
        "bundle.py",
    } <= names
    assert root / "runs" / "coherent-v1" / "DS10-S01" / "fit.json" in paths
    assert root / "runs" / "rough-v1" / "DS10-S02" / "fit.json" in paths


def test_frozen_core_is_reused_without_runner_options():
    data = object()
    source = {"fit": {"bank": [1, 2]}}
    children = {"capture": {"fit": "rough"}}
    calls = []

    def fitter(*args, **kwargs):
        calls.append((args, kwargs))
        return {"refinements_per_bank": 2, "budget_s_per_refinement": 15.0}

    result = runner.fit_with_frozen_core(data, source, children, fitter=fitter)
    assert calls == [((data, source["fit"], children), {})]
    assert result["refinements_per_bank"] == 2
    assert result["budget_s_per_refinement"] == 15.0


def test_snapshot_detects_post_snapshot_corruption(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"value": 1}))
    snapshot = runner._snapshot_files((source,))
    runner._assert_snapshot_unchanged(snapshot)
    source.write_text(json.dumps({"value": 2}))
    with pytest.raises(RuntimeError, match="changed before seal"):
        runner._assert_snapshot_unchanged(snapshot)


def test_cli_requires_named_unit_option():
    assert runner.parse_args(["--unit", "DS10-D01"]).unit == "DS10-D01"
    with pytest.raises(SystemExit):
        runner.parse_args(["DS10-D01"])
