import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest
from alias_family_joint import (
    AliasFamilyJointData,
    load_unit_with_family_exports,
    preflight_selected_units,
    resolve_representative_rows,
)


def _child_receipt(dataset, unit_id, session_id, groups):
    groups = np.asarray(groups, dtype=int)
    representatives = []
    families = []
    for family_index, group in enumerate(dict.fromkeys(groups.tolist())):
        members = np.flatnonzero(groups == group).tolist()
        member_ids = [f"{session_id}:row-{index}" for index in members]
        representative = members[-1]
        representative_id = f"{session_id}:row-{representative}"
        representatives.append(representative)
        families.append(
            {
                "family_id": f"{session_id}:family-{family_index}",
                "probe_key": [session_id, family_index, 0, 0],
                "representative_candidate_id": representative_id,
                "member_candidate_ids": member_ids,
                "lineage": [
                    {"candidate_id": candidate_id, "input_row_index": row}
                    for candidate_id, row in zip(member_ids, members, strict=True)
                ],
            }
        )
    return {
        "schema": "alias-family-capture-export/v1",
        "dataset": dataset,
        "session_id": session_id,
        "selected_unit_ids": [unit_id],
        "accounting": {"raw_row_count": len(groups)},
        "representative_original_indices": representatives,
        "geometry": {
            "source_row_count": len(groups),
            "representative_row_count": len(representatives),
            "source_group_count": len(np.unique(groups)),
            "representative_group_count": len(np.unique(groups)),
            "all_source_groups_preserved": True,
        },
        "grouping": {
            "families": families,
            "representative_rows": [
                {"candidate_id": family["representative_candidate_id"]}
                for family in families
            ],
        },
    }


def _data(group_layouts, *, single=False):
    child_sessions = tuple(f"capture-{index}" for index in range(len(group_layouts)))
    groups = []
    capture_index = []
    times = []
    group_offset = 0
    row_offset = 0
    for child_index, layout in enumerate(group_layouts):
        layout = np.asarray(layout, dtype=int)
        _, inverse = np.unique(layout, return_inverse=True)
        groups.extend((inverse + group_offset).tolist())
        capture_index.extend([child_index] * len(layout))
        times.extend((100 * child_index + np.arange(len(layout), dtype=float)).tolist())
        group_offset += len(np.unique(layout))
        row_offset += len(layout)
    count = len(groups)
    source = SimpleNamespace(
        dataset="DS10",
        unit_id="DS10-S01" if single else f"DS10-{'D' if len(group_layouts) == 2 else 'Q'}01",
        session_id=child_sessions[0] if single else "joint",
        child_sessions=child_sessions,
        reference_time_s=321.5,
        origin_utc_ns=123,
        times=np.asarray(times),
        measured=np.arange(count, dtype=float) + 10,
        rf=np.asarray([11e9 + 1e6 * value for value in capture_index]),
        receiver=np.asarray([value % 2 for value in capture_index]),
        channel=np.asarray([value + 1 for value in capture_index]),
        group=np.asarray(groups),
        margin=np.linspace(0.1, 0.9, count),
        capture_index=np.asarray(capture_index),
        nodes=np.arange(-5.0, 1000.0, 0.25),
        numbers=np.array([10, 20, 30]),
        position=np.ones((3, 4020, 3)),
        velocity=np.full((3, 4020, 3), 2.0),
        initial=np.zeros(9),
        tracks=[{"rows": np.arange(count), "candidate_indices": np.arange(3)}],
    )
    receipt_unit_id = source.unit_id
    if single:
        del source.capture_index
        del source.child_sessions
        del source.unit_id
    receipts = [
        _child_receipt("DS10", receipt_unit_id, session, layout)
        for session, layout in zip(child_sessions, group_layouts, strict=True)
    ]
    return source, receipts


@pytest.mark.parametrize(
    ("layouts", "single"),
    [
        ([[4, 4, 9]], True),
        ([[1, 1, 2], [8, 9, 9, 10]], False),
        ([[1, 1], [3, 4, 4], [5, 5, 6, 7], [8, 9, 9, 10, 10]], False),
    ],
)
def test_single_pair_quad_mapping_medians_and_capture_index(layouts, single):
    source, receipts = _data(layouts, single=single)
    original = {name: np.asarray(getattr(source, name)).copy() for name in (
        "times", "measured", "rf", "receiver", "channel", "group", "margin"
    )}
    adapted = AliasFamilyJointData(source, receipts)
    expected_rows = []
    offset = 0
    for layout in layouts:
        for group in dict.fromkeys(layout):
            local_row = max(
                index for index, value in enumerate(layout) if value == group
            )
            expected_rows.append(offset + local_row)
        offset += len(layout)
    np.testing.assert_array_equal(adapted.original_rows, expected_rows)
    expected_capture = np.concatenate(
        [np.full(len(layout), index) for index, layout in enumerate(layouts)]
    )[expected_rows]
    np.testing.assert_array_equal(adapted.capture_index, expected_capture)
    for index, row in enumerate(expected_rows):
        group_rows = np.flatnonzero(source.group == source.group[row])
        assert adapted.times[index] == np.median(source.times[group_rows])
    assert adapted.reference_time_s == source.reference_time_s
    assert adapted.nodes is source.nodes
    assert adapted.position is source.position
    assert adapted.velocity is source.velocity
    assert adapted.numbers is source.numbers
    assert adapted.tracks is None
    assert adapted.tracks_available_for_rough_fitting is False
    predicted, visible = adapted.predict(source.initial)
    assert predicted.shape == (len(expected_rows), len(source.numbers))
    assert visible.shape == predicted.shape
    for name, values in original.items():
        np.testing.assert_array_equal(getattr(source, name), values)


def test_pair_mapping_uses_cumulative_offsets_and_has_no_cross_capture_links():
    source, receipts = _data([[1, 1, 2], [7, 8, 8, 9]])
    mapping = resolve_representative_rows(source, receipts)
    np.testing.assert_array_equal(mapping["representative_original_rows"], [1, 2, 3, 5, 6])
    assert [child["raw_row_offset"] for child in mapping["children"]] == [0, 3]
    adapted = AliasFamilyJointData(source, receipts)
    for group in np.unique(adapted.group):
        assert len(np.unique(adapted.capture_index[adapted.group == group])) == 1


def test_bad_lineage_and_representative_mapping_are_rejected():
    source, receipts = _data([[1, 1, 2]], single=True)
    receipts[0]["grouping"]["families"][0]["lineage"][1]["input_row_index"] = 0
    with pytest.raises(ValueError, match="partition"):
        resolve_representative_rows(source, receipts)
    source, receipts = _data([[1, 1, 2]], single=True)
    receipts[0]["representative_original_indices"][0] = 0
    with pytest.raises(ValueError, match="disagree"):
        resolve_representative_rows(source, receipts)


def test_bad_raw_count_capture_order_and_group_coverage_are_rejected():
    source, receipts = _data([[1, 1, 2], [7, 8]])
    receipts[0]["accounting"]["raw_row_count"] = 2
    with pytest.raises(ValueError, match="raw row count"):
        resolve_representative_rows(source, receipts)
    source, receipts = _data([[1, 1, 2], [7, 8]])
    source.capture_index[[2, 3]] = source.capture_index[[3, 2]]
    with pytest.raises(ValueError, match="contiguous"):
        resolve_representative_rows(source, receipts)
    source, receipts = _data([[1, 1, 2]], single=True)
    receipts[0]["representative_original_indices"] = [1]
    receipts[0]["grouping"]["representative_rows"] = receipts[0]["grouping"][
        "representative_rows"
    ][:1]
    receipts[0]["grouping"]["families"] = receipts[0]["grouping"]["families"][:1]
    receipts[0]["geometry"]["representative_row_count"] = 1
    with pytest.raises(ValueError, match="partition"):
        resolve_representative_rows(source, receipts)


def test_complete_lineage_cannot_drop_a_source_group_representative():
    source, receipts = _data([[1, 1, 2]], single=True)
    first, second = receipts[0]["grouping"]["families"]
    first["member_candidate_ids"].extend(second["member_candidate_ids"])
    first["lineage"].extend(second["lineage"])
    receipts[0]["grouping"]["families"] = [first]
    receipts[0]["grouping"]["representative_rows"] = receipts[0]["grouping"][
        "representative_rows"
    ][:1]
    receipts[0]["representative_original_indices"] = [1]
    receipts[0]["geometry"]["representative_row_count"] = 1
    with pytest.raises(ValueError, match="preserve every source group"):
        resolve_representative_rows(source, receipts)


def _frozen_56_fixture():
    selection = {
        "schema": "multiscan-localization-selection/v1",
        "datasets": {},
    }
    receipts = {}
    for dataset in ("DS10", "DS11"):
        sessions = [f"{dataset}-capture-{index:02d}" for index in range(16)]
        units = []
        for index, session_id in enumerate(sessions, start=1):
            units.append(
                {
                    "unit_id": f"{dataset}-S{index:02d}",
                    "session_ids": [session_id],
                }
            )
        for index in range(8):
            units.append(
                {
                    "unit_id": f"{dataset}-D{index + 1:02d}",
                    "session_ids": sessions[2 * index : 2 * index + 2],
                }
            )
        for index in range(4):
            units.append(
                {
                    "unit_id": f"{dataset}-Q{index + 1:02d}",
                    "session_ids": sessions[4 * index : 4 * index + 4],
                }
            )
        selection["datasets"][dataset] = {"selected": sessions, "units": units}
        memberships = {
            session_id: [
                unit["unit_id"] for unit in units if session_id in unit["session_ids"]
            ]
            for session_id in sessions
        }
        for session_id in sessions:
            receipt = _child_receipt(dataset, memberships[session_id][0], session_id, [0, 0, 1])
            receipt["selected_unit_ids"] = memberships[session_id]
            receipt["accounting"]["grouped_family_count"] = 2
            receipts[session_id] = receipt
    return selection, receipts


def _load_synthetic_unit(dataset, unit):
    sessions = tuple(unit["session_ids"])
    source, _ = _data([[0, 0, 1]] * len(sessions), single=len(sessions) == 1)
    source.dataset = dataset
    source.session_id = sessions[0] if len(sessions) == 1 else unit["unit_id"]
    if len(sessions) > 1:
        source.unit_id = unit["unit_id"]
        source.child_sessions = sessions
    return source


def test_preflight_validates_all_56_units_and_reports_counts():
    selection, receipts = _frozen_56_fixture()
    result = preflight_selected_units(selection, receipts, _load_synthetic_unit)
    assert result["unit_count"] == 56
    assert result["unit_counts_by_size"] == {"1": 32, "2": 16, "4": 8}
    assert result["all_units_valid"]
    assert all(unit["valid"] for unit in result["units"])
    assert all(not unit["tracks_available_for_rough_fitting"] for unit in result["units"])


def test_preflight_uses_legacy_single_reference_epoch_without_changing_joint_epoch():
    selection, receipts = _frozen_56_fixture()

    def load_unit(dataset, unit):
        source = _load_synthetic_unit(dataset, unit)
        if len(unit["session_ids"]) == 1:
            del source.reference_time_s
        return source

    result = preflight_selected_units(selection, receipts, load_unit)
    assert result["all_units_valid"]
    singles = [unit for unit in result["units"] if len(unit["child_sessions"]) == 1]
    assert len(singles) == 32
    assert all(unit["reference_time_s"] == 150.0 for unit in singles)


def test_preflight_rejects_bad_child_membership_before_loading_units():
    selection, receipts = _frozen_56_fixture()
    receipts["DS10-capture-00"]["selected_unit_ids"] = ["DS10-S01"]
    called = False

    def load_unit(dataset, unit):
        nonlocal called
        called = True
        return _load_synthetic_unit(dataset, unit)

    with pytest.raises(ValueError, match="membership differs"):
        preflight_selected_units(selection, receipts, load_unit)
    assert not called


def test_saved_single_loader_returns_original_adapted_and_snapshot_paths(
    tmp_path, monkeypatch
):
    selection, receipts = _frozen_56_fixture()
    selection_path = tmp_path / "selection.json"
    selection_path.write_text(json.dumps(selection))
    scans_root = tmp_path / "scans"
    export_directory = tmp_path / "exports"
    export_directory.mkdir()
    records = []
    for index, (session_id, receipt) in enumerate(receipts.items()):
        scan = scans_root / session_id
        scan.mkdir(parents=True)
        bundle_json = scan / "bundle.json"
        bundle_npz = scan / "bundle.npz"
        bundle_json.write_text(f"manifest-{session_id}")
        bundle_npz.write_bytes(f"arrays-{session_id}".encode())
        receipt["sealed"] = True
        receipt["input_digests"] = {
            "bundle_json": hashlib.sha256(bundle_json.read_bytes()).hexdigest(),
            "bundle_npz": hashlib.sha256(bundle_npz.read_bytes()).hexdigest(),
        }
        path = export_directory / f"capture-{index:02d}.json"
        path.write_text(json.dumps(receipt))
        records.append(
            {
                "dataset": receipt["dataset"],
                "session_id": session_id,
                "path": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "raw_row_count": receipt["accounting"]["raw_row_count"],
                "grouped_family_count": receipt["accounting"][
                    "grouped_family_count"
                ],
            }
        )
    manifest = {
        "schema": "alias-family-cohort-export/v1",
        "sealed": True,
        "complete_32_capture_export": True,
        "exported_capture_count": 32,
        "selection_sha256": hashlib.sha256(selection_path.read_bytes()).hexdigest(),
        "captures": records,
    }
    unrequested_path = export_directory / records[1]["path"]
    unrequested_path.write_text("deliberately not JSON")
    records[1]["sha256"] = hashlib.sha256(unrequested_path.read_bytes()).hexdigest()
    (export_directory / "manifest.json").write_text(json.dumps(manifest))
    source, _ = _data([[0, 0, 1]], single=True)
    source.dataset = "DS10"
    source.session_id = "DS10-capture-00"
    monkeypatch.setattr(
        "alias_family_joint._single_data_class", lambda: lambda directory: source
    )
    original, adapted, input_paths = load_unit_with_family_exports(
        "DS10-S01",
        export_directory,
        selection_path=selection_path,
        scans_root=scans_root,
        units_root=tmp_path / "units",
    )
    assert original is source
    np.testing.assert_array_equal(adapted.original_rows, [1, 2])
    assert selection_path in input_paths
    assert export_directory / "manifest.json" in input_paths
    assert scans_root / source.session_id / "bundle.npz" in input_paths
    assert unrequested_path not in input_paths

    records[1]["dataset"] = "DS11"
    (export_directory / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="16 captures per dataset"):
        load_unit_with_family_exports(
            "DS10-S01",
            export_directory,
            selection_path=selection_path,
            scans_root=scans_root,
            units_root=tmp_path / "units",
        )
