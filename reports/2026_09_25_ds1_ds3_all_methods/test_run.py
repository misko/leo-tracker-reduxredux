from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def module():
    path = Path(__file__).with_name("run.py")
    spec = importlib.util.spec_from_file_location("all_methods_report_test", path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def test_ds3_artifact_marks_unsealed_binding_incomplete(tmp_path: Path):
    m = module()
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{}\n")
    value, path, sha256, error = m.ds3_artifact({"artifact": {"path": str(artifact)}})
    assert value is None
    assert path == str(artifact)
    assert sha256 is None
    assert error and "unsealed" in error


def test_verify_accepts_standard_sha256sum_sidecar(tmp_path: Path):
    m = module()
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{}\n")
    artifact.with_suffix(".json.sha256").write_text(
        m.digest(artifact).removeprefix("sha256:") + "  artifact.json\n"
    )
    assert m.verify(artifact) == {}


def test_portable_path_uses_repository_relative_paths():
    m = module()
    assert m.portable_path(m.DEFAULT_MATRIX) == (
        "reports/2026_09_25_ds3_all_iterations_backfill/"
        "paired-completion-matrix-v4.json"
    )


def test_publish_refuses_incomplete_report(tmp_path: Path):
    m = module()
    report = tmp_path / "comparison.json"
    m.write(report, {"publication_ready": False})
    with pytest.raises(ValueError, match="refusing publication"):
        m.publish(report)


def test_postseal_reader_keeps_unavailable_values_null(tmp_path: Path):
    m = module()
    root = tmp_path / "method"
    root.mkdir()
    assert m.postseal_from_report(str(root)) == {
        "estimate": None,
        "postseal_error_km": None,
        "artifact": None,
        "artifact_sha256": None,
    }


def test_postseal_marks_unqualified_estimate_diagnostic(tmp_path: Path):
    m = module()
    comparison = tmp_path / "comparison.json"
    m.write(
        comparison,
        {
            "schema": "ds1-ds3-all-methods-report/v2",
            "matrix": {"sha256": "sha256:matrix"},
            "method_registry": {"sha256": "sha256:registry"},
            "rows": [
                {
                    "method_id": "example-arm",
                    "iteration": 2,
                    "ds3_terminal_status": "unqualified_boundary",
                    "ds3_estimates": [
                        {"label": "raw", "latitude_deg": 37.0, "longitude_deg": -122.0}
                    ],
                }
            ],
        },
    )
    output = tmp_path / "postseal.json"
    value = m.evaluate_postseal(
        comparison,
        output,
        {"latitude_deg": 37.0, "longitude_deg": -122.0},
    )
    row = value["rows"][0]
    assert row["best_qualified_error_km"] is None
    assert row["best_diagnostic_error_km"] == 0
    assert row["method_id"] == "example-arm"
    assert row["estimates"][0]["ranking_eligible"] is False
    assert row["estimates"][0]["classification"] == "diagnostic_unqualified"
    sealed = m.verify(output)
    assert sealed["matrix_sha256"] == "sha256:matrix"
    assert sealed["method_registry_sha256"] == "sha256:registry"


def test_postseal_keeps_parent_disqualified_estimate_as_diagnostic(tmp_path: Path):
    m = module()
    comparison = tmp_path / "comparison.json"
    m.write(
        comparison,
        {
            "schema": "ds1-ds3-all-methods-report/v2",
            "matrix": {"sha256": "sha256:matrix"},
            "method_registry": {"sha256": "sha256:registry"},
            "rows": [
                {
                    "method_id": "descendant-arm",
                    "iteration": 9,
                    "ds3_terminal_status": "unqualified_parent",
                    "ds3_estimates": [
                        {"label": "selected", "latitude_deg": 37.0, "longitude_deg": -122.0}
                    ],
                }
            ],
        },
    )

    value = m.evaluate_postseal(
        comparison,
        tmp_path / "postseal.json",
        {"latitude_deg": 37.0, "longitude_deg": -122.0},
    )

    row = value["rows"][0]
    assert row["best_diagnostic_error_km"] == 0
    assert row["best_qualified_error_km"] is None
    assert row["estimates"][0]["ranking_eligible"] is False


def test_postseal_rejects_mismatched_matrix(tmp_path: Path):
    m = module()
    evaluation = tmp_path / "postseal.json"
    m.write(
        evaluation,
        {
            "schema": "ds1-ds3-all-methods-postseal/v2",
            "matrix_sha256": "sha256:other",
            "method_registry_sha256": "sha256:registry",
            "rows": [],
        },
    )
    with pytest.raises(ValueError, match="different paired matrix"):
        m.postseal_results(evaluation, "sha256:expected", "sha256:registry")


def test_ds1_qualification_uses_superseding_invalidating_audit():
    m = module()
    value = m.ds1_qualification("reports/2026_09_24_ds1_iteration15_information_weighted", 15)
    assert value["status"] == "invalidated_by_later_audit"
    assert value["ranking_eligible"] is False
    assert value["artifact"].endswith("iteration19_rate_bound_audit/comparison.json")


def test_ds1_boundary_and_gate_failures_cannot_rank():
    m = module()
    boundary = m.ds1_qualification("reports/2026_09_25_ds1_iteration20_session_predictive", 20)
    stencil = m.ds1_qualification("reports/2026_09_25_ds1_iteration27_phase_cache", 27)
    assert boundary["status"] == "unqualified"
    assert boundary["ranking_eligible"] is False
    assert "geographic_interior" in boundary["reason"]
    assert stencil["status"] == "unqualified"
    assert stencil["ranking_eligible"] is False
    assert "center_winner" in stencil["reason"]


def test_qualified_table_requires_both_ds1_and_ds3_qualification():
    m = module()
    value = {
        "rows": [
            {
                "method_id": "boundary-arm",
                "iteration": 20,
                "arm": "boundary",
                "method": "boundary",
                "ds3_terminal_status": "qualified",
                "ds1_ranking_eligible": False,
                "ds1_postseal_error_km": 0.267,
                "ds3_estimates": [
                    {
                        "label": "candidate",
                        "latitude_deg": 37.0,
                        "longitude_deg": -122.0,
                    }
                ],
                "ds3_artifact": "sealed.json",
                "ds3_artifact_sha256": "sha256:sealed",
            }
        ]
    }
    assert m.estimate_rows(value, qualified_only=True) == []
    all_rows = m.estimate_rows(value, qualified_only=False)
    assert len(all_rows) == 1
    assert all_rows[0]["ranking_eligible"] is False


def test_registry_is_stable_arm_identity_and_fail_closed():
    m = module()
    value = m.build(m.DEFAULT_MATRIX, m.DEFAULT_REGISTRY)
    assert value["schema"] == "ds1-ds3-all-methods-report/v2"
    assert value["counts"]["iteration_slots"] == 31
    assert value["counts"]["method_arms"] == 49
    assert value["publication_ready"] is False
    assert "i03-global-time-plus-orbit-rate-screen" in value["required_pending_method_ids"]
    assert "i22-randomized-time-predictive" in value["required_pending_method_ids"]
    rows = {row["method_id"]: row for row in value["rows"]}
    assert rows["i02-shared-global-time"]["arm"] == "shared_global_tau"
    assert rows["i02-regularized-per-scan-time"]["arm"] == "regularized_per_scan_tau"
    assert rows["i06b-legacy-session-scale"]["ds3_terminal_status"] == "not_portable_legacy"
    assert rows["i26-quartic-rate-marginal"]["superseded_by"] == "i27-phase-cache"


def test_markdown_explains_historical_ds1_coverage_is_not_a_ranking():
    m = module()
    value = {
        "publication_ready": False,
        "required_pending_method_ids": [],
        "rows": [],
    }
    assert "DS1_COVERAGE_AUDIT.md" in m.markdown(value)


def test_postseal_rejects_mismatched_method_registry(tmp_path: Path):
    m = module()
    evaluation = tmp_path / "postseal.json"
    m.write(
        evaluation,
        {
            "schema": "ds1-ds3-all-methods-postseal/v2",
            "matrix_sha256": "sha256:matrix",
            "method_registry_sha256": "sha256:other",
            "rows": [],
        },
    )
    with pytest.raises(ValueError, match="different method registry"):
        m.postseal_results(evaluation, "sha256:matrix", "sha256:registry")
