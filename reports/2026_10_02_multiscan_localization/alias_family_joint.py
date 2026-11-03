"""Apply frozen child alias-family exports to single or joint numerical data."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path

import numpy as np
from finite_set_fit import GroupMedianGeometryData, array_digest
from joint_inputs import load_joint_data
from prediction_jacobian import paired_prediction_jacobian

ROW_ARRAYS = ("times", "measured", "rf", "receiver", "channel", "group", "margin")
ROOT = Path(__file__).resolve().parent
DEFAULT_SELECTION = ROOT / "selection.json"
DEFAULT_SCANS = ROOT / "scans"
DEFAULT_UNITS = ROOT / "units"
EXPECTED_UNIT_SIZES = Counter({1: 16, 2: 8, 4: 4})


def _digest(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _capture_contract(data):
    row_count = len(data.times)
    if hasattr(data, "capture_index"):
        capture_index = np.asarray(data.capture_index, dtype=np.int64)
        child_sessions = tuple(data.child_sessions)
    else:
        capture_index = np.zeros(row_count, dtype=np.int64)
        session_id = getattr(data, "session_id", None)
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("single-capture data must expose a session_id")
        child_sessions = (session_id,)
    if capture_index.shape != (row_count,):
        raise ValueError("capture_index must align with joint rows")
    if not child_sessions or len(set(child_sessions)) != len(child_sessions):
        raise ValueError("child_sessions must be nonempty and unique")
    if np.any(capture_index < 0) or np.any(capture_index >= len(child_sessions)):
        raise ValueError("capture_index falls outside child_sessions")
    return child_sessions, capture_index


def _validate_receipt_lineage(receipt, raw_count):
    grouping = receipt.get("grouping")
    if not isinstance(grouping, dict):
        raise ValueError("child export lacks grouping")
    families = grouping.get("families")
    representatives = grouping.get("representative_rows")
    if not isinstance(families, list) or not isinstance(representatives, list):
        raise ValueError("child grouping lacks families or representative rows")
    if len(families) != len(representatives):
        raise ValueError("family and representative counts differ")
    lineage_indices = []
    family_by_representative = {}
    for family in families:
        representative_id = family.get("representative_candidate_id")
        member_ids = family.get("member_candidate_ids")
        lineage = family.get("lineage")
        if (
            not isinstance(representative_id, str)
            or not isinstance(member_ids, list)
            or not isinstance(lineage, list)
            or len(member_ids) != len(lineage)
            or representative_id not in member_ids
            or representative_id in family_by_representative
        ):
            raise ValueError("child family lineage is malformed")
        lineage_ids = []
        for member in lineage:
            candidate_id = member.get("candidate_id")
            index = member.get("input_row_index")
            if (
                not isinstance(candidate_id, str)
                or isinstance(index, bool)
                or not isinstance(index, int)
                or index < 0
                or index >= raw_count
            ):
                raise ValueError("child family lineage row is invalid")
            lineage_ids.append(candidate_id)
            lineage_indices.append(index)
        if sorted(lineage_ids) != sorted(member_ids):
            raise ValueError("child family IDs disagree with lineage")
        family_by_representative[representative_id] = {
            member["candidate_id"]: member["input_row_index"] for member in lineage
        }
    if Counter(lineage_indices) != Counter(range(raw_count)):
        raise ValueError("child lineage must partition every original row exactly once")
    representative_indices = []
    for representative in representatives:
        candidate_id = representative.get("candidate_id")
        if candidate_id not in family_by_representative:
            raise ValueError("representative candidate is absent from family lineage")
        representative_indices.append(family_by_representative[candidate_id][candidate_id])
    exported = np.asarray(receipt.get("representative_original_indices"), dtype=np.int64)
    expected = np.asarray(representative_indices, dtype=np.int64)
    if exported.shape != expected.shape or not np.array_equal(exported, expected):
        raise ValueError("exported representative indices disagree with family lineage")
    if len(np.unique(exported)) != len(exported):
        raise ValueError("child representative indices must be unique")
    return exported


def resolve_representative_rows(data, child_receipts):
    """Validate child exports and return their cumulative joint row mapping."""

    child_sessions, capture_index = _capture_contract(data)
    receipts = tuple(child_receipts)
    if len(receipts) != len(child_sessions):
        raise ValueError("one child export is required per capture")
    if tuple(receipt.get("session_id") for receipt in receipts) != child_sessions:
        raise ValueError("child export order must match frozen child_sessions")
    dataset = getattr(data, "dataset", None)
    unit_id = getattr(data, "unit_id", None)
    global_rows = []
    child_accounting = []
    expected_offset = 0
    for child_index, (session_id, receipt) in enumerate(
        zip(child_sessions, receipts, strict=True)
    ):
        if receipt.get("schema") != "alias-family-capture-export/v1":
            raise ValueError("unsupported child alias-family export schema")
        if dataset is not None and receipt.get("dataset") != dataset:
            raise ValueError("child export dataset differs from numerical data")
        selected_units = receipt.get("selected_unit_ids")
        if unit_id is not None and (
            not isinstance(selected_units, list) or unit_id not in selected_units
        ):
            raise ValueError("child export is not bound to this selected unit")
        rows = np.flatnonzero(capture_index == child_index)
        raw_count = receipt.get("accounting", {}).get("raw_row_count")
        if isinstance(raw_count, bool) or not isinstance(raw_count, int) or raw_count != len(rows):
            raise ValueError("child raw row count differs from capture_index")
        expected_rows = np.arange(expected_offset, expected_offset + raw_count)
        if not np.array_equal(rows, expected_rows):
            raise ValueError("joint capture rows are not contiguous in child selection order")
        local_representatives = _validate_receipt_lineage(receipt, raw_count)
        geometry = receipt.get("geometry", {})
        if (
            geometry.get("source_row_count") != raw_count
            or geometry.get("representative_row_count") != len(local_representatives)
        ):
            raise ValueError("child geometry counts disagree with representatives")
        selected_rows = expected_offset + local_representatives
        source_groups = np.unique(np.asarray(data.group)[rows])
        selected_groups = np.unique(np.asarray(data.group)[selected_rows])
        if not np.array_equal(source_groups, selected_groups):
            raise ValueError("child representatives do not preserve every source group")
        if (
            geometry.get("source_group_count") != len(source_groups)
            or geometry.get("representative_group_count") != len(selected_groups)
            or geometry.get("all_source_groups_preserved") is not True
        ):
            raise ValueError("child group accounting differs from joint data")
        for family in receipt["grouping"]["families"]:
            probe_key = family.get("probe_key")
            if not isinstance(probe_key, list) or not probe_key or probe_key[0] != session_id:
                raise ValueError("child family probe identity is not capture-qualified")
        global_rows.extend(selected_rows.tolist())
        child_accounting.append(
            {
                "session_id": session_id,
                "capture_index": child_index,
                "raw_row_offset": expected_offset,
                "raw_row_count": raw_count,
                "representative_row_count": len(local_representatives),
                "source_group_count": len(source_groups),
            }
        )
        expected_offset += raw_count
    if expected_offset != len(data.times):
        raise ValueError("child raw row counts do not cover joint data")
    global_rows = np.asarray(global_rows, dtype=np.int64)
    if len(np.unique(global_rows)) != len(global_rows):
        raise ValueError("joint representative rows must be unique")
    return {
        "child_sessions": child_sessions,
        "source_capture_index": capture_index,
        "representative_original_rows": global_rows,
        "children": child_accounting,
    }


class AliasFamilyJointData:
    """Reduced observation view with untouched joint orbit and timing authority."""

    def __init__(self, source, child_receipts):
        mapping = resolve_representative_rows(source, child_receipts)
        median_source = GroupMedianGeometryData(source)
        indices = mapping["representative_original_rows"]
        self.source = median_source
        self.original_data = source
        self.original_rows = indices.copy()
        for name in ROW_ARRAYS:
            setattr(self, name, np.asarray(getattr(median_source, name))[indices].copy())
        source_capture_index = mapping["source_capture_index"]
        self.capture_index = source_capture_index[indices].copy()
        self.tracks = None
        self.tracks_available_for_rough_fitting = False
        self.track_policy = (
            "original track row indices are unavailable on reduced data; run rough fitting and "
            "track-seed caches on the original ungrouped source"
        )
        self.geometry_receipt = {
            "policy": "full joint group-median geometry frozen before alias-family filtering",
            "preselection_geometry": median_source.geometry_receipt,
            "representative_original_rows": indices.copy(),
            "representative_original_rows_sha256": array_digest(indices),
            "representative_row_count": len(indices),
            "group_count": len(np.unique(self.group)),
            "capture_count": len(mapping["child_sessions"]),
            "capture_index_sha256": array_digest(self.capture_index),
            "fitted_array_sha256": {
                name: array_digest(getattr(self, name))
                for name in (*ROW_ARRAYS, "capture_index")
            },
            "children": mapping["children"],
            "all_families_represented": True,
            "representatives_only": True,
            "holdout_used": False,
            "tracks_available_for_rough_fitting": False,
        }

    def __getattr__(self, name):
        return getattr(self.source, name)

    def predict(self, parameters, rows=None, satellites=None):
        if (rows is None) != (satellites is None):
            raise ValueError("supply paired rows and satellites, or neither")
        if rows is None:
            row_count = len(self.times)
            satellite_count = len(self.numbers)
            rows = np.repeat(np.arange(row_count), satellite_count).reshape(
                row_count, satellite_count
            )
            satellites = np.tile(np.arange(satellite_count), row_count).reshape(
                row_count, satellite_count
            )
        predicted, visible, _ = paired_prediction_jacobian(
            self,
            parameters,
            np.asarray(rows, dtype=int),
            np.asarray(satellites, dtype=int),
        )
        return predicted, visible


def load_cohort_manifest(export_directory, *, expected_manifest_sha256=None):
    """Authenticate the complete manifest without parsing child receipt JSON."""

    export_directory = Path(export_directory)
    manifest_path = export_directory / "manifest.json"
    manifest_sha256 = _digest(manifest_path)
    if (
        expected_manifest_sha256 is not None
        and manifest_sha256 != expected_manifest_sha256
    ):
        raise ValueError("cohort export manifest digest differs from the expected digest")
    manifest = json.loads(manifest_path.read_text())
    records = manifest.get("captures")
    if (
        manifest.get("schema") != "alias-family-cohort-export/v1"
        or manifest.get("sealed") is not True
        or manifest.get("complete_32_capture_export") is not True
        or manifest.get("exported_capture_count") != 32
        or not isinstance(records, list)
        or len(records) != 32
    ):
        raise ValueError("cohort export is not a sealed complete 32-capture export")
    records_by_session = {}
    paths = set()
    dataset_counts = Counter()
    for record in records:
        session_id = record.get("session_id")
        relative_path = record.get("path")
        if (
            not isinstance(session_id, str)
            or session_id in records_by_session
            or not isinstance(relative_path, str)
        ):
            raise ValueError("cohort export capture records are malformed or duplicated")
        path = export_directory / relative_path
        if path.resolve().parent != export_directory.resolve() or path in paths:
            raise ValueError("cohort export capture path must be a direct child")
        dataset = record.get("dataset")
        raw_count = record.get("raw_row_count")
        family_count = record.get("grouped_family_count")
        if (
            dataset not in {"DS10", "DS11"}
            or isinstance(raw_count, bool)
            or not isinstance(raw_count, int)
            or isinstance(family_count, bool)
            or not isinstance(family_count, int)
            or not 0 < family_count <= raw_count
            or not isinstance(record.get("sha256"), str)
        ):
            raise ValueError("cohort export capture accounting is malformed")
        records_by_session[session_id] = record
        paths.add(path)
        dataset_counts[dataset] += 1
    if dataset_counts != Counter({"DS10": 16, "DS11": 16}):
        raise ValueError("cohort manifest must contain 16 captures per dataset")
    return {
        "manifest": manifest,
        "manifest_path": manifest_path,
        "manifest_sha256": manifest_sha256,
        "records_by_session": records_by_session,
        "receipt_paths": {
            session_id: export_directory / record["path"]
            for session_id, record in records_by_session.items()
        },
    }


def _load_child_exports(cohort, session_ids):
    receipts = {}
    receipt_sha256 = {}
    for session_id in session_ids:
        record = cohort["records_by_session"].get(session_id)
        if record is None:
            raise ValueError(f"{session_id}: missing from cohort export manifest")
        path = cohort["receipt_paths"][session_id]
        actual_digest = _digest(path)
        if actual_digest != record.get("sha256"):
            raise ValueError(f"{session_id}: child export digest mismatch")
        receipt = json.loads(path.read_text())
        if (
            receipt.get("sealed") is not True
            or receipt.get("session_id") != session_id
            or receipt.get("dataset") != record.get("dataset")
            or receipt.get("accounting", {}).get("raw_row_count")
            != record.get("raw_row_count")
            or receipt.get("accounting", {}).get("grouped_family_count")
            != record.get("grouped_family_count")
        ):
            raise ValueError(f"{session_id}: child export disagrees with cohort manifest")
        receipts[session_id] = receipt
        receipt_sha256[session_id] = actual_digest
    return {
        **cohort,
        "receipts": receipts,
        "receipt_sha256": receipt_sha256,
    }


def load_cohort_exports(export_directory, *, expected_manifest_sha256=None):
    """Load and authenticate every receipt for one complete frozen export."""

    cohort = load_cohort_manifest(
        export_directory, expected_manifest_sha256=expected_manifest_sha256
    )
    return _load_child_exports(cohort, cohort["records_by_session"])


def _selection_memberships(selection):
    if selection.get("schema") != "multiscan-localization-selection/v1":
        raise ValueError("unsupported frozen selection schema")
    datasets = selection.get("datasets")
    if not isinstance(datasets, dict) or set(datasets) != {"DS10", "DS11"}:
        raise ValueError("preflight requires the frozen DS10 and DS11 populations")
    expected_memberships = {}
    session_datasets = {}
    unit_count = 0
    for dataset, population in datasets.items():
        units = population.get("units")
        selected = population.get("selected")
        if not isinstance(units, list) or not isinstance(selected, list):
            raise ValueError(f"{dataset}: frozen unit selection is malformed")
        if Counter(len(unit.get("session_ids", ())) for unit in units) != EXPECTED_UNIT_SIZES:
            raise ValueError(f"{dataset}: expected 16 singles, 8 pairs, and 4 quads")
        if len(selected) != 16 or len(set(selected)) != 16:
            raise ValueError(f"{dataset}: expected 16 unique selected captures")
        for unit in units:
            unit_id = unit.get("unit_id")
            sessions = unit.get("session_ids")
            if (
                not isinstance(unit_id, str)
                or not isinstance(sessions, list)
                or len(sessions) not in EXPECTED_UNIT_SIZES
                or len(set(sessions)) != len(sessions)
                or any(session_id not in selected for session_id in sessions)
            ):
                raise ValueError(f"{dataset}: selected unit is malformed")
            for session_id in sessions:
                previous_dataset = session_datasets.setdefault(session_id, dataset)
                if previous_dataset != dataset:
                    raise ValueError("selected capture appears in multiple datasets")
                expected_memberships.setdefault(session_id, []).append(unit_id)
            unit_count += 1
        if set(selected) != {
            session_id
            for unit in units
            for session_id in unit["session_ids"]
        }:
            raise ValueError(f"{dataset}: selected captures and unit membership differ")
    if unit_count != 56 or set(expected_memberships) != {
        session_id
        for population in datasets.values()
        for session_id in population["selected"]
    }:
        raise ValueError("selection does not define exactly 56 units")
    return expected_memberships, session_datasets


def _validate_selection(selection, receipts):
    expected_memberships, session_datasets = _selection_memberships(selection)
    if set(receipts) != set(expected_memberships):
        raise ValueError("selection and cohort exports do not cover the same captures")
    for session_id, expected in expected_memberships.items():
        receipt = receipts[session_id]
        if receipt.get("dataset") != session_datasets[session_id]:
            raise ValueError(f"{session_id}: child export dataset differs from selection")
        if receipt.get("selected_unit_ids") != expected:
            raise ValueError(f"{session_id}: selected unit membership differs from selection")


def preflight_selected_units(selection, receipts, load_unit):
    """Validate all 56 selected units through a caller-supplied frozen-data loader."""

    _validate_selection(selection, receipts)
    units = []
    size_counts = Counter()
    total_source_rows = 0
    total_representative_rows = 0
    for dataset, population in selection["datasets"].items():
        for unit in population["units"]:
            unit_id = unit["unit_id"]
            sessions = tuple(unit["session_ids"])
            source = load_unit(dataset, unit)
            source_sessions, source_capture_index = _capture_contract(source)
            if source_sessions != sessions:
                raise ValueError(f"{unit_id}: numerical child order differs from selection")
            if hasattr(source, "dataset") and source.dataset != dataset:
                raise ValueError(f"{unit_id}: numerical dataset differs from selection")
            if hasattr(source, "unit_id") and source.unit_id != unit_id:
                raise ValueError(f"{unit_id}: numerical unit identity differs from selection")
            child_receipts = tuple(receipts[session_id] for session_id in sessions)
            source_hashes = {
                name: array_digest(getattr(source, name)) for name in ROW_ARRAYS
            }
            adapted = AliasFamilyJointData(source, child_receipts)
            if any(
                source_hashes[name] != array_digest(getattr(source, name))
                for name in ROW_ARRAYS
            ):
                raise RuntimeError(f"{unit_id}: alias-family adaptation mutated source arrays")
            if (
                getattr(adapted, "reference_time_s", 150.0)
                != getattr(source, "reference_time_s", 150.0)
                or adapted.nodes is not source.nodes
                or adapted.position is not source.position
                or adapted.velocity is not source.velocity
                or adapted.numbers is not source.numbers
            ):
                raise RuntimeError(f"{unit_id}: timing or ephemeris authority was replaced")
            for group_value in np.unique(adapted.group):
                rows = adapted.group == group_value
                if len(np.unique(adapted.capture_index[rows])) != 1:
                    raise ValueError(f"{unit_id}: reduced source group crosses captures")
            source_rows = len(source.times)
            representative_rows = len(adapted.times)
            expected_representatives = sum(
                receipt["accounting"]["grouped_family_count"]
                for receipt in child_receipts
            )
            if representative_rows != expected_representatives:
                raise ValueError(f"{unit_id}: representative family count differs from exports")
            capture_rows = np.bincount(
                adapted.capture_index, minlength=len(sessions)
            ).tolist()
            units.append(
                {
                    "dataset": dataset,
                    "unit_id": unit_id,
                    "size": len(sessions),
                    "child_sessions": list(sessions),
                    "source_row_count": source_rows,
                    "representative_row_count": representative_rows,
                    "source_group_count": len(np.unique(source.group)),
                    "representative_group_count": len(np.unique(adapted.group)),
                    "representative_rows_by_capture": capture_rows,
                    "candidate_count": len(adapted.numbers),
                    "reference_time_s": float(getattr(adapted, "reference_time_s", 150.0)),
                    "source_arrays_unchanged": True,
                    "tracks_available_for_rough_fitting": False,
                    "valid": True,
                }
            )
            size_counts[len(sessions)] += 1
            total_source_rows += source_rows
            total_representative_rows += representative_rows
            del adapted, source, source_capture_index
    return {
        "schema": "alias-family-joint-preflight/v1",
        "unit_count": len(units),
        "unit_counts_by_size": {
            str(size): size_counts[size] for size in sorted(size_counts)
        },
        "source_row_count": total_source_rows,
        "representative_row_count": total_representative_rows,
        "all_units_valid": len(units) == 56 and all(unit["valid"] for unit in units),
        "units": units,
        "provenance": {
            "reference_accessed": False,
            "tle_queried": False,
            "iq_read": False,
            "fit_performed": False,
            "rough_fitting_performed": False,
        },
    }


def _single_data_class():
    path = ROOT.parent / "2026_10_02_localization_benchmark" / "bundle.py"
    specification = importlib.util.spec_from_file_location(
        "alias_family_joint_single_bundle", path
    )
    if specification is None or specification.loader is None:
        raise ImportError(f"cannot load frozen single-bundle adapter from {path}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module.Data


def _load_frozen_unit(unit, *, scans_root, units_root, single_data):
    if len(unit["session_ids"]) == 1:
        return single_data(Path(scans_root) / unit["session_ids"][0])
    return load_joint_data(Path(units_root) / unit["unit_id"])


def load_unit_with_family_exports(
    unit_id,
    export_directory,
    *,
    selection_path=DEFAULT_SELECTION,
    scans_root=DEFAULT_SCANS,
    units_root=DEFAULT_UNITS,
    expected_manifest_sha256=None,
):
    """Load one frozen unit and its validated alias-family representative view."""

    selection_path = Path(selection_path)
    selection_sha256 = _digest(selection_path)
    selection = json.loads(selection_path.read_text())
    exports = load_cohort_manifest(
        export_directory, expected_manifest_sha256=expected_manifest_sha256
    )
    if exports["manifest"].get("selection_sha256") != selection_sha256:
        raise ValueError("cohort export selection digest differs from frozen selection")
    expected_memberships, session_datasets = _selection_memberships(selection)
    if set(exports["records_by_session"]) != set(expected_memberships):
        raise ValueError("selection and cohort manifest do not cover the same captures")
    for session_id, record in exports["records_by_session"].items():
        if record.get("dataset") != session_datasets[session_id]:
            raise ValueError(f"{session_id}: cohort manifest dataset differs from selection")
    matches = [
        (dataset, unit)
        for dataset, population in selection["datasets"].items()
        for unit in population["units"]
        if unit.get("unit_id") == unit_id
    ]
    if len(matches) != 1:
        raise ValueError("unit_id must identify exactly one frozen selected unit")
    dataset, unit = matches[0]
    sessions = tuple(unit["session_ids"])
    exports = _load_child_exports(exports, sessions)
    child_receipts = tuple(exports["receipts"][session_id] for session_id in sessions)
    for session_id, receipt in zip(sessions, child_receipts, strict=True):
        if receipt.get("selected_unit_ids") != expected_memberships[session_id]:
            raise ValueError(f"{session_id}: selected unit membership differs from selection")
    input_paths = [selection_path, exports["manifest_path"]]
    for session_id, receipt in zip(sessions, child_receipts, strict=True):
        input_paths.append(exports["receipt_paths"][session_id])
        for name in ("bundle.json", "bundle.npz"):
            path = Path(scans_root) / session_id / name
            actual = _digest(path)
            expected = receipt.get("input_digests", {}).get(name.replace(".", "_"))
            if actual != expected:
                raise ValueError(f"{session_id}: {name} differs from child export")
            input_paths.append(path)
    if len(sessions) > 1:
        input_paths.extend(
            [
                Path(units_root) / unit_id / "bundle.json",
                Path(units_root) / unit_id / "bundle.npz",
            ]
        )
    single_data = _single_data_class()
    original_data = _load_frozen_unit(
        unit,
        scans_root=scans_root,
        units_root=units_root,
        single_data=single_data,
    )
    source_sessions, _ = _capture_contract(original_data)
    if source_sessions != sessions:
        raise ValueError(f"{unit_id}: numerical child order differs from selection")
    if hasattr(original_data, "dataset") and original_data.dataset != dataset:
        raise ValueError(f"{unit_id}: numerical dataset differs from selection")
    if hasattr(original_data, "unit_id") and original_data.unit_id != unit_id:
        raise ValueError(f"{unit_id}: numerical unit identity differs from selection")
    adapted_data = AliasFamilyJointData(original_data, child_receipts)
    return original_data, adapted_data, tuple(dict.fromkeys(map(Path, input_paths)))


def preflight_saved_cohort(
    selection_path,
    export_directory,
    *,
    scans_root=DEFAULT_SCANS,
    units_root=DEFAULT_UNITS,
    expected_manifest_sha256=None,
    load_unit=None,
):
    """Preflight saved exports against all frozen single/pair/quad bundles."""

    selection_path = Path(selection_path)
    selection_sha256 = _digest(selection_path)
    selection = json.loads(selection_path.read_text())
    exports = load_cohort_exports(
        export_directory, expected_manifest_sha256=expected_manifest_sha256
    )
    if exports["manifest"].get("selection_sha256") != selection_sha256:
        raise ValueError("cohort export selection digest differs from frozen selection")
    scan_snapshots = {}
    for session_id, receipt in exports["receipts"].items():
        for name in ("bundle.json", "bundle.npz"):
            path = Path(scans_root) / session_id / name
            actual = _digest(path)
            expected = receipt.get("input_digests", {}).get(name.replace(".", "_"))
            if actual != expected:
                raise ValueError(f"{session_id}: {name} differs from child export")
            scan_snapshots[str(path.resolve())] = actual
    if load_unit is None:
        single_data = _single_data_class()

        def load_unit(dataset, unit):
            del dataset
            return _load_frozen_unit(
                unit,
                scans_root=scans_root,
                units_root=units_root,
                single_data=single_data,
            )

    result = preflight_selected_units(selection, exports["receipts"], load_unit)
    if _digest(selection_path) != selection_sha256:
        raise RuntimeError("selection changed during joint preflight")
    if _digest(exports["manifest_path"]) != exports["manifest_sha256"]:
        raise RuntimeError("cohort export manifest changed during joint preflight")
    for path, expected in scan_snapshots.items():
        if _digest(path) != expected:
            raise RuntimeError(f"source bundle changed during joint preflight: {path}")
    result.update(
        {
            "selection_sha256": selection_sha256,
            "cohort_export_manifest_sha256": exports["manifest_sha256"],
            "child_export_sha256": exports["receipt_sha256"],
            "inputs_reverified_unchanged_before_seal": True,
            "sealed": True,
        }
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exports", type=Path, required=True)
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--scans-root", type=Path, default=DEFAULT_SCANS)
    parser.add_argument("--units-root", type=Path, default=DEFAULT_UNITS)
    parser.add_argument("--expected-manifest-sha256")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    receipt = preflight_saved_cohort(
        args.selection,
        args.exports,
        scans_root=args.scans_root,
        units_root=args.units_root,
        expected_manifest_sha256=args.expected_manifest_sha256,
    )
    if args.output is not None:
        if args.output.exists():
            raise FileExistsError(args.output)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                "unit_count": receipt["unit_count"],
                "unit_counts_by_size": receipt["unit_counts_by_size"],
                "all_units_valid": receipt["all_units_valid"],
                "output": None if args.output is None else str(args.output),
            }
        )
    )


__all__ = [
    "AliasFamilyJointData",
    "load_cohort_exports",
    "load_cohort_manifest",
    "load_unit_with_family_exports",
    "preflight_saved_cohort",
    "preflight_selected_units",
    "resolve_representative_rows",
]


if __name__ == "__main__":
    main()
