import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from alias_family_cohort import (
    adapter_recipe,
    assert_snapshot_unchanged,
    capture_qualified_rows,
    export_cohort,
    grouping_accounting,
    median_geometry_receipt,
    representative_original_indices,
    selected_captures,
    snapshot_files,
    validate_bundle_binding,
)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _selection(tmp_path):
    datasets = {}
    for dataset in ("DS10", "DS11"):
        sessions = [f"{dataset.lower()}-{index:02d}" for index in range(16)]
        source = tmp_path / f"{dataset}.json"
        population_hashes = {
            session: f"sha256:{index:064x}" for index, session in enumerate(sessions, 1)
        }
        source.write_text(
            json.dumps(
                {
                    "captures": [
                        {
                            "session_id": session,
                            "manifest_sha256": population_hashes[session],
                        }
                        for session in sessions
                    ]
                }
            )
        )
        units = [
            {"unit_id": f"{dataset}-S{index + 1:02d}", "size": 1, "session_ids": [session]}
            for index, session in enumerate(sessions)
        ]
        units.extend(
            {
                "unit_id": f"{dataset}-D{index // 2 + 1:02d}",
                "size": 2,
                "session_ids": sessions[index : index + 2],
            }
            for index in range(0, 16, 2)
        )
        units.extend(
            {
                "unit_id": f"{dataset}-Q{index // 4 + 1:02d}",
                "size": 4,
                "session_ids": sessions[index : index + 4],
            }
            for index in range(0, 16, 4)
        )
        datasets[dataset] = {
            "selected": sessions,
            "units": units,
            "manifest_path": str(source),
            "manifest_sha256": _sha(source),
            "population_hashes": population_hashes,
        }
    return {"schema": "multiscan-localization-selection/v1", "datasets": datasets}


def test_selection_extracts_exact_16_plus_16_and_unit_membership(tmp_path):
    captures = selected_captures(_selection(tmp_path))
    assert len(captures) == 32
    assert captures[0]["session_id"] == "ds10-00"
    assert captures[16]["session_id"] == "ds11-00"
    assert captures[0]["unit_ids"] == ["DS10-S01", "DS10-D01", "DS10-Q01"]
    assert captures[0]["population_capture_manifest_sha256"].startswith("sha256:")
    assert captures[-1]["cohort_selection_index"] == 31


def test_selection_rejects_missing_or_duplicate_capture(tmp_path):
    selection = _selection(tmp_path)
    selection["datasets"]["DS10"]["selected"][-1] = selection["datasets"]["DS10"]["selected"][0]
    with pytest.raises(ValueError, match="unique"):
        selected_captures(selection)


def test_bundle_binds_to_population_capture_manifest_not_selection_file():
    spec = {
        "session_id": "capture",
        "dataset": "DS10",
        "population_capture_manifest_sha256": "sha256:authority",
    }
    manifest = {
        "session_id": "capture",
        "dataset": "DS10",
        "provenance": {"input_manifest_sha256": "sha256:authority"},
    }
    validate_bundle_binding(manifest, spec)
    manifest["provenance"]["input_manifest_sha256"] = "sha256:selection-file"
    with pytest.raises(ValueError, match="population capture"):
        validate_bundle_binding(manifest, spec)


def test_snapshot_guard_detects_input_change(tmp_path):
    source = tmp_path / "source.json"
    source.write_text("before")
    snapshot = snapshot_files([source])
    assert_snapshot_unchanged(snapshot)
    source.write_text("after")
    with pytest.raises(RuntimeError, match="changed before seal"):
        assert_snapshot_unchanged(snapshot)


def test_capture_qualification_and_representative_indices_are_original_order():
    rows = [
        {"probe_key": [2, 0, 3], "candidate_id": "ignored"},
        {"probe_key": [2, 0, 3], "candidate_id": "ignored"},
    ]
    projected = [SimpleNamespace(candidate_id="b"), SimpleNamespace(candidate_id="a")]
    qualified = capture_qualified_rows("capture", rows, projected)
    assert qualified[0]["probe_key"] == ["capture", 2, 0, 3]
    assert qualified[0]["local_probe_key"] == [2, 0, 3]
    grouping = {"representative_rows": [{"candidate_id": "a"}, {"candidate_id": "b"}]}
    np.testing.assert_array_equal(
        representative_original_indices(grouping, qualified), [1, 0]
    )


def test_median_geometry_is_frozen_before_representative_filtering():
    data = SimpleNamespace(
        times=np.array([0.0, 2.0, 10.0]),
        measured=np.array([5.0, 6.0, 7.0]),
        rf=np.array([11.0, 11.0, 12.0]),
        receiver=np.array([0, 0, 1]),
        channel=np.array([1, 1, 2]),
        group=np.array([4, 4, 9]),
        margin=np.array([0.1, 0.2, 0.3]),
        reference_time_s=8.0,
    )
    receipt = median_geometry_receipt(data, np.array([0, 2]))
    expected_times = np.array([1.0, 10.0])
    assert receipt["source_median_changed_row_count"] == 2
    assert receipt["reference_time_s"] == 8.0
    assert receipt["fitted_representative_array_sha256"]["times"] == hashlib.sha256(
        expected_times.dtype.str.encode()
        + np.asarray(expected_times.shape, dtype="<i8").tobytes()
        + expected_times.tobytes()
    ).hexdigest()


def test_grouping_accounting_requires_complete_partition():
    grouping = {
        "families": [
            {"kind": "zero_anchor", "member_candidate_ids": ["a", "b"]},
            {"kind": "passthrough", "member_candidate_ids": ["c"]},
        ],
        "ambiguous_edges": [{}],
        "unmatched_edges": [],
        "policy": {"zero_bridge_candidate_ids": []},
    }
    receipt = grouping_accounting(grouping, 3)
    assert receipt["grouped_family_count"] == 2
    assert receipt["collapsed_row_count"] == 1
    assert receipt["ambiguous_edge_count"] == 1
    with pytest.raises(ValueError, match="partition"):
        grouping_accounting(grouping, 4)


def test_bounded_partial_cli_export_writes_immutable_child_receipts(tmp_path):
    selection_path = tmp_path / "selection.json"
    selection_path.write_text(json.dumps(_selection(tmp_path)))

    def fake_export(spec, *, bulk_root):
        return {
            "schema": "alias-family-capture-export/v1",
            "session_id": spec["session_id"],
            "accounting": {"raw_row_count": 10, "grouped_family_count": 7},
        }

    output = tmp_path / "export"
    manifest_path, manifest = export_cohort(
        output,
        selection_path=selection_path,
        max_count=2,
        capture_exporter=fake_export,
    )
    assert manifest_path.exists()
    assert manifest["exported_capture_count"] == 2
    assert not manifest["complete_32_capture_export"]
    assert len(list(output.glob("*.json"))) == 3
    with pytest.raises(FileExistsError):
        export_cohort(output, selection_path=selection_path, capture_exporter=fake_export)
    with pytest.raises(ValueError, match=r"\[1, 32\]"):
        export_cohort(tmp_path / "bad", selection_path=selection_path, max_count=33)


def test_joint_adapter_recipe_qualifies_identity_and_orders_median_first():
    recipe = adapter_recipe()
    steps = recipe["steps"]
    assert "qualify raw source-group identity by session_id" in steps[1]
    assert steps.index(
        "construct each child full-row geometry and freeze source-group median "
        "times before filtering"
    ) < steps.index(
        "select rows by representative_original_indices in the child's original row order"
    )
    assert recipe["warnings"][1].startswith("never join probes or groups across captures")
