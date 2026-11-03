#!/usr/bin/env python3
"""Export metadata-only alias families for the frozen 32-capture cohort."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from rough_smoke import load_module, serializable
from selection import ROOT

DEFAULT_SELECTION = ROOT / "selection.json"
DEFAULT_BULK_ROOT = Path("/srv/bulk/leo")
CAPTURES_PER_DATASET = 16
MAX_CAPTURE_COUNT = 32
ARRAY_NAMES = ("times", "measured", "rf", "receiver", "channel", "group", "margin")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def array_digest(values):
    values = np.ascontiguousarray(values)
    payload = values.dtype.str.encode() + np.asarray(values.shape, dtype="<i8").tobytes()
    return hashlib.sha256(payload + values.tobytes()).hexdigest()


def snapshot_files(paths):
    snapshot = {}
    for path in paths:
        resolved = str(Path(path).resolve())
        if resolved in snapshot:
            raise ValueError(f"duplicate snapshot path: {resolved}")
        snapshot[resolved] = digest(path)
    return snapshot


def assert_snapshot_unchanged(snapshot):
    changed = [path for path, expected in snapshot.items() if digest(path) != expected]
    if changed:
        raise RuntimeError(f"export provenance changed before seal: {', '.join(changed)}")


def validate_bundle_binding(manifest, spec):
    if (
        manifest.get("session_id") != spec["session_id"]
        or manifest.get("dataset") != spec["dataset"]
    ):
        raise ValueError("capture bundle identity differs from selection")
    if (
        manifest["provenance"]["input_manifest_sha256"]
        != spec["population_capture_manifest_sha256"]
    ):
        raise ValueError("bundle input manifest differs from selected population capture")


def selected_captures(selection):
    """Return the frozen 16+16 captures and all selected-unit memberships."""

    if selection.get("schema") != "multiscan-localization-selection/v1":
        raise ValueError("unsupported selection schema")
    datasets = selection.get("datasets")
    if not isinstance(datasets, dict) or set(datasets) != {"DS10", "DS11"}:
        raise ValueError("selection must contain exactly DS10 and DS11")
    captures = []
    global_sessions = set()
    for dataset in ("DS10", "DS11"):
        record = datasets[dataset]
        selected = record.get("selected")
        units = record.get("units")
        if not isinstance(selected, list) or len(selected) != CAPTURES_PER_DATASET:
            raise ValueError(f"{dataset} must select exactly 16 captures")
        if len(set(selected)) != len(selected) or any(
            not isinstance(session, str) or not session for session in selected
        ):
            raise ValueError(f"{dataset} selected captures must be unique nonempty strings")
        if not isinstance(units, list):
            raise ValueError(f"{dataset} units must be a list")
        size_counts = Counter(unit.get("size") for unit in units)
        if size_counts != Counter({1: 16, 2: 8, 4: 4}):
            raise ValueError(f"{dataset} units must partition as 16 singles, 8 pairs, 4 quads")
        memberships = {session: [] for session in selected}
        single_sessions = []
        for unit in units:
            unit_sessions = unit.get("session_ids")
            if (
                not isinstance(unit.get("unit_id"), str)
                or not isinstance(unit_sessions, list)
                or len(unit_sessions) != unit.get("size")
                or any(session not in memberships for session in unit_sessions)
            ):
                raise ValueError(f"{dataset} unit membership is inconsistent")
            for session in unit_sessions:
                memberships[session].append(unit["unit_id"])
            if unit["size"] == 1:
                single_sessions.append(unit_sessions[0])
        if single_sessions != selected:
            raise ValueError(f"{dataset} singleton order must equal selected capture order")
        for size in (1, 2, 4):
            partition = Counter(
                session
                for unit in units
                if unit["size"] == size
                for session in unit["session_ids"]
            )
            if partition != Counter({session: 1 for session in selected}):
                raise ValueError(f"{dataset} size-{size} units do not exactly partition captures")
        if any(len(unit_ids) != 3 for unit_ids in memberships.values()):
            raise ValueError(f"{dataset} captures must each belong to one single, pair, and quad")
        manifest_path = Path(record["manifest_path"])
        if digest(manifest_path) != record["manifest_sha256"]:
            raise ValueError(f"{dataset} source manifest digest changed")
        population = json.loads(manifest_path.read_text())
        population_rows = population.get("captures")
        if not isinstance(population_rows, list):
            raise ValueError(f"{dataset} population manifest lacks captures")
        population_by_session = {}
        for row in population_rows:
            session_id = row.get("session_id")
            manifest_sha256 = row.get("manifest_sha256")
            if (
                not isinstance(session_id, str)
                or not isinstance(manifest_sha256, str)
                or session_id in population_by_session
            ):
                raise ValueError(f"{dataset} population capture identity is invalid")
            population_by_session[session_id] = manifest_sha256
        for selection_index, session_id in enumerate(selected):
            if session_id in global_sessions:
                raise ValueError("a capture appears in both datasets")
            if session_id not in population_by_session:
                raise ValueError(f"{dataset} selected capture is absent from its population")
            global_sessions.add(session_id)
            captures.append(
                {
                    "dataset": dataset,
                    "dataset_selection_index": selection_index,
                    "cohort_selection_index": len(captures),
                    "session_id": session_id,
                    "unit_ids": memberships[session_id],
                    "source_manifest": str(manifest_path),
                    "source_manifest_sha256": record["manifest_sha256"],
                    "population_capture_manifest_sha256": population_by_session[
                        session_id
                    ],
                }
            )
    if len(captures) != MAX_CAPTURE_COUNT:
        raise ValueError("selection must contain exactly 32 captures")
    return captures


def capture_qualified_rows(session_id, rows, projected):
    """Copy exact-joined metadata and qualify probe identity by capture."""

    if len(rows) != len(projected) or any(row is None for row in rows):
        raise ValueError("metadata and projected rows must be completely aligned")
    qualified = []
    for row, point in zip(rows, projected, strict=True):
        item = copy.deepcopy(row)
        local_probe = list(item["probe_key"])
        item["local_probe_key"] = local_probe
        item["probe_key"] = [session_id, *local_probe]
        item["candidate_id"] = point.candidate_id
        qualified.append(item)
    candidate_ids = [row["candidate_id"] for row in qualified]
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("projected candidate IDs must be unique within a capture")
    return qualified


def representative_original_indices(grouping, qualified_rows):
    by_candidate = {
        row["candidate_id"]: index for index, row in enumerate(qualified_rows)
    }
    representatives = grouping.get("representative_rows")
    if not isinstance(representatives, list) or not representatives:
        raise ValueError("grouping must contain representative rows")
    try:
        indices = [by_candidate[row["candidate_id"]] for row in representatives]
    except (KeyError, TypeError) as error:
        raise ValueError("group representative lacks an authoritative candidate ID") from error
    if len(set(indices)) != len(indices):
        raise ValueError("representative original indices must be unique")
    return np.asarray(indices, dtype=np.int64)


def median_geometry_receipt(data, representative_indices):
    """Hash the actual median-before-filter arrays without mutating source data."""

    arrays = {name: np.asarray(getattr(data, name)).copy() for name in ARRAY_NAMES}
    count = len(arrays["times"])
    if count == 0 or any(values.shape != (count,) for values in arrays.values()):
        raise ValueError("capture arrays must be aligned nonempty vectors")
    source_times = arrays["times"].copy()
    for group_value in np.unique(arrays["group"]):
        members = np.flatnonzero(arrays["group"] == group_value)
        if (
            len(np.unique(arrays["rf"][members])) != 1
            or len(np.unique(arrays["receiver"][members])) != 1
            or len(np.unique(arrays["channel"][members])) != 1
        ):
            raise ValueError("source group has conflicting prediction keys")
        arrays["times"][members] = np.median(source_times[members])
    indices = np.asarray(representative_indices, dtype=np.int64)
    if indices.ndim != 1 or not len(indices) or np.any(indices < 0) or np.any(indices >= count):
        raise ValueError("representative indices are invalid")
    selected = {name: values[indices].copy() for name, values in arrays.items()}
    source_groups = np.unique(arrays["group"])
    selected_groups = np.unique(selected["group"])
    if not np.array_equal(source_groups, selected_groups):
        raise ValueError("representatives do not preserve every source group")
    return {
        "policy": (
            "freeze candidate-independent source-group median geometry before selecting "
            "family representatives"
        ),
        "source_row_count": count,
        "representative_row_count": len(indices),
        "source_group_count": len(source_groups),
        "representative_group_count": len(selected_groups),
        "all_source_groups_preserved": True,
        "representative_original_indices": indices,
        "representative_original_indices_sha256": array_digest(indices),
        "source_array_sha256": {
            name: array_digest(np.asarray(getattr(data, name))) for name in ARRAY_NAMES
        },
        "median_source_array_sha256": {
            name: array_digest(values) for name, values in arrays.items()
        },
        "fitted_representative_array_sha256": {
            name: array_digest(values) for name, values in selected.items()
        },
        "source_median_changed_row_count": int(np.sum(arrays["times"] != source_times)),
        "reference_time_s": float(getattr(data, "reference_time_s", 150.0)),
    }


def grouping_accounting(grouping, raw_count):
    families = grouping["families"]
    member_ids = [
        candidate_id
        for family in families
        for candidate_id in family["member_candidate_ids"]
    ]
    if len(member_ids) != raw_count or len(set(member_ids)) != raw_count:
        raise ValueError("family lineage must partition every raw candidate exactly once")
    sizes = Counter(len(family["member_candidate_ids"]) for family in families)
    kinds = Counter(family["kind"] for family in families)
    return {
        "raw_row_count": raw_count,
        "grouped_family_count": len(families),
        "collapsed_row_count": raw_count - len(families),
        "family_kind_counts": dict(sorted(kinds.items())),
        "family_size_counts": {str(size): count for size, count in sorted(sizes.items())},
        "ambiguous_edge_count": len(grouping["ambiguous_edges"]),
        "unmatched_edge_count": len(grouping["unmatched_edges"]),
        "zero_bridge_count": len(grouping["policy"]["zero_bridge_candidate_ids"]),
        "complete_partition": True,
    }


def _runtime_code_paths():
    module_names = (
        "leo.application.scanner_trajectory",
        "leo.scanner.host_adaptive_products",
        "leo.storage.adaptive_hop",
        "leo.storage.adaptive_hop_analysis",
        "leo.storage.scanner_tracking_source",
    )
    paths = []
    for name in module_names:
        module = sys.modules.get(name)
        path = getattr(module, "__file__", None)
        if path is None:
            raise RuntimeError(f"runtime metadata module was not loaded: {name}")
        paths.append(Path(path))
    return paths


def export_capture(spec, *, bulk_root=DEFAULT_BULK_ROOT):
    """Export one selected capture without reading IQ samples or fitting."""

    import alias_family
    import candidate_prevalence_diagnostic as prevalence
    import edge_alias_diagnostic as edge

    session_id = spec["session_id"]
    bundle_dir = ROOT / "scans" / session_id
    bundle_json = bundle_dir / "bundle.json"
    bundle_npz = bundle_dir / "bundle.npz"
    bundle_path = ROOT.parent / "2026_10_02_localization_benchmark" / "bundle.py"
    local_code_snapshot = snapshot_files(
        [
            Path(__file__),
            Path(alias_family.__file__),
            Path(edge.__file__),
            Path(prevalence.__file__),
            ROOT / "finite_set_likelihood.py",
            ROOT / "rough_smoke.py",
            bundle_path,
        ]
    )
    input_snapshot = snapshot_files(
        [bundle_json, bundle_npz, Path(spec["source_manifest"])]
    )
    manifest = json.loads(bundle_json.read_text())
    validate_bundle_binding(manifest, spec)
    bundle = load_module(f"alias_family_cohort_bundle_{session_id}", bundle_path)
    data = bundle.Data(bundle_dir)
    _, projected, rows, join, sample_rate_hz = edge._metadata(
        Path(bulk_root),
        session_id,
        manifest["provenance"]["input_manifest_sha256"],
        manifest["provenance"]["persisted_analysis_manifest_sha256"],
    )
    binding = prevalence._verify_bundle_rows(data, manifest, projected)
    qualified = capture_qualified_rows(session_id, rows, projected)
    grouping = alias_family.group_alias_families(
        qualified,
        frame_period_samples=sample_rate_hz / 750.0,
    )
    representatives = representative_original_indices(grouping, qualified)
    geometry = median_geometry_receipt(data, representatives)
    accounting = grouping_accounting(grouping, len(qualified))
    runtime_code_hashes = snapshot_files(_runtime_code_paths())
    assert_snapshot_unchanged(local_code_snapshot)
    assert_snapshot_unchanged(input_snapshot)
    return {
        "schema": "alias-family-capture-export/v1",
        "created_utc": datetime.now(UTC).isoformat(),
        "dataset": spec["dataset"],
        "session_id": session_id,
        "dataset_selection_index": spec["dataset_selection_index"],
        "cohort_selection_index": spec["cohort_selection_index"],
        "selected_unit_ids": spec["unit_ids"],
        "origin_utc_ns": manifest["origin_utc_ns"],
        "sample_rate_hz": sample_rate_hz,
        "join": {**join, **binding},
        "accounting": accounting,
        "representative_original_indices": representatives,
        "geometry": geometry,
        "grouping": grouping,
        "input_digests": {
            "bundle_json": digest(bundle_json),
            "bundle_npz": digest(bundle_npz),
            "input_manifest_sha256": manifest["provenance"]["input_manifest_sha256"],
            "analysis_manifest_sha256": manifest["provenance"][
                "persisted_analysis_manifest_sha256"
            ],
            "population_capture_manifest_sha256": spec[
                "population_capture_manifest_sha256"
            ],
            "selection_source_manifest": spec["source_manifest"],
            "selection_source_manifest_sha256": spec["source_manifest_sha256"],
            "snapshotted_inputs": input_snapshot,
        },
        "code_digests": {
            "snapshotted_local_code": local_code_snapshot,
            "runtime_metadata_code": runtime_code_hashes,
        },
        "provenance": {
            "reference_accessed": False,
            "tle_queried": False,
            "iq_read": False,
            "fit_performed": False,
            "probe_identity_capture_qualified": True,
            "all_families_represented": True,
            "representatives_only": True,
            "holdout_used": False,
            "bundle_and_local_code_reverified_unchanged_before_seal": True,
        },
        "sealed": True,
    }


def adapter_recipe():
    return {
        "purpose": (
            "assemble any selected single, pair, or quad without regrouping or "
            "cross-capture alias links"
        ),
        "steps": [
            "verify each child export, bundle, selection, and code digest",
            (
                "retain capture-qualified probe identity and qualify raw source-group "
                "identity by session_id"
            ),
            (
                "construct each child full-row geometry and freeze source-group median "
                "times before filtering"
            ),
            "select rows by representative_original_indices in the child's original row order",
            (
                "shift child receive times and ephemeris time authority into the joint unit "
                "origin using frozen capture origins"
            ),
            (
                "concatenate children in the session order frozen by selection.json and "
                "remap qualified groups to contiguous integers"
            ),
            (
                "verify candidate catalogue order and orbit authority are common before "
                "any joint likelihood evaluation"
            ),
            (
                "treat all exported families as training evidence through one representative "
                "each; use no holdout"
            ),
        ],
        "warnings": [
            "never apply median geometry after representative filtering",
            "never join probes or groups across captures using unqualified local integer IDs",
            "do not infer new families after concatenation",
            "do not compare absolute likelihood values with ungrouped observations",
        ],
    }


def export_cohort(
    output_dir,
    *,
    selection_path=DEFAULT_SELECTION,
    bulk_root=DEFAULT_BULK_ROOT,
    max_count=None,
    capture_exporter=export_capture,
):
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise FileExistsError(output_dir)
    if max_count is None:
        limit = MAX_CAPTURE_COUNT
    elif (
        isinstance(max_count, bool)
        or not isinstance(max_count, int)
        or not 1 <= max_count <= MAX_CAPTURE_COUNT
    ):
        raise ValueError("max_count must be an integer in [1, 32]")
    else:
        limit = max_count
    selection_path = Path(selection_path)
    selection = json.loads(selection_path.read_text())
    captures = selected_captures(selection)[:limit]
    selection_sha256 = digest(selection_path)
    output_dir.mkdir(parents=True, exist_ok=False)
    records = []
    for spec in captures:
        receipt = capture_exporter(spec, bulk_root=bulk_root)
        name = (
            f"{spec['dataset']}-{spec['dataset_selection_index'] + 1:02d}-"
            f"{spec['session_id']}.json"
        )
        path = output_dir / name
        path.write_text(json.dumps(serializable(receipt), indent=2, allow_nan=False) + "\n")
        records.append(
            {
                "dataset": spec["dataset"],
                "session_id": spec["session_id"],
                "cohort_selection_index": spec["cohort_selection_index"],
                "path": path.name,
                "sha256": digest(path),
                "raw_row_count": receipt["accounting"]["raw_row_count"],
                "grouped_family_count": receipt["accounting"]["grouped_family_count"],
            }
        )
    if digest(selection_path) != selection_sha256:
        raise RuntimeError("selection changed during cohort export")
    if selected_captures(json.loads(selection_path.read_text())) != selected_captures(selection):
        raise RuntimeError("selection bindings changed during cohort export")
    manifest = {
        "schema": "alias-family-cohort-export/v1",
        "created_utc": datetime.now(UTC).isoformat(),
        "selection": str(selection_path.resolve()),
        "selection_sha256": selection_sha256,
        "requested_max_count": max_count,
        "selected_capture_count": MAX_CAPTURE_COUNT,
        "exported_capture_count": len(records),
        "complete_32_capture_export": len(records) == MAX_CAPTURE_COUNT,
        "selection_reverified_unchanged_before_seal": True,
        "captures": records,
        "joint_adapter_recipe": adapter_recipe(),
        "provenance": {
            "reference_accessed": False,
            "tle_queried": False,
            "iq_read": False,
            "fit_performed": False,
        },
        "sealed": True,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(serializable(manifest), indent=2, allow_nan=False) + "\n")
    return manifest_path, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--bulk-root", type=Path, default=DEFAULT_BULK_ROOT)
    parser.add_argument("--max-count", type=int)
    args = parser.parse_args()
    manifest_path, manifest = export_cohort(
        args.output,
        selection_path=args.selection,
        bulk_root=args.bulk_root,
        max_count=args.max_count,
    )
    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "sha256": digest(manifest_path),
                "exported_capture_count": manifest["exported_capture_count"],
                "complete_32_capture_export": manifest["complete_32_capture_export"],
            }
        )
    )


if __name__ == "__main__":
    main()
