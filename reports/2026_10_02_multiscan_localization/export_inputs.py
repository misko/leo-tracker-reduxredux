"""Export one frozen DS10 or DS11 capture through the benchmark bundle contract."""

from __future__ import annotations

import argparse
import importlib.util
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
SELECTION_PATH = ROOT / "selection.json"
LEGACY_EXPORT_PATH = (
    ROOT.parent / "2026_10_02_localization_benchmark" / "export_ds11.py"
)
DEFAULT_API_BASE = "http://127.0.0.1:8090/api/v1/scanner/tracking"
DEFAULT_BULK_ROOT = Path("/srv/bulk/leo")
DEFAULT_TLE_ROOT = Path("/var/lib/leo/tle")
DATASETS = ("DS10", "DS11")
EXPECTED_UNIT_COUNTS = {1: 16, 2: 8, 4: 4}


def _load_legacy_export():
    spec = importlib.util.spec_from_file_location(
        "localization_benchmark_export_helpers", LEGACY_EXPORT_PATH
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load benchmark export helpers from {LEGACY_EXPORT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_HELPERS = _load_legacy_export()


def _validate_units(dataset: str, block: dict, captures: dict[str, dict]) -> None:
    selected = block.get("selected")
    units = block.get("units")
    if not isinstance(selected, list) or len(selected) != 16 or len(set(selected)) != 16:
        raise ValueError(f"{dataset} must freeze 16 unique selected captures")
    if not isinstance(units, list):
        raise ValueError(f"{dataset} units must be a list")
    if len({unit.get("unit_id") for unit in units}) != len(units):
        raise ValueError(f"{dataset} unit IDs must be unique")
    by_size: dict[int, list[tuple[str, ...]]] = {size: [] for size in EXPECTED_UNIT_COUNTS}
    for unit in units:
        session_ids = tuple(unit.get("session_ids", ()))
        size = unit.get("size")
        if size not in EXPECTED_UNIT_COUNTS or len(session_ids) != size:
            raise ValueError(f"{dataset} unit size does not match its session IDs")
        if len(set(session_ids)) != size or not set(session_ids).issubset(selected):
            raise ValueError(f"{dataset} unit sessions must be distinct selected captures")
        starts = [int(captures[session_id]["capture_start_utc_ns"]) for session_id in session_ids]
        if starts != sorted(starts):
            raise ValueError(f"{dataset} unit sessions must be chronological")
        by_size[size].append(session_ids)
    observed_counts = {size: len(rows) for size, rows in by_size.items()}
    if observed_counts != EXPECTED_UNIT_COUNTS:
        raise ValueError(f"{dataset} unit counts differ from the frozen 16/8/4 design")
    for size, rows in by_size.items():
        frequency = Counter(session_id for row in rows for session_id in row)
        if frequency != Counter({session_id: 1 for session_id in selected}):
            raise ValueError(f"{dataset} size-{size} units must partition selected captures")
    pairs = set(by_size[2])
    nested_pairs = {
        pair
        for quad in by_size[4]
        for pair in ((quad[0], quad[1]), (quad[2], quad[3]))
    }
    if pairs != nested_pairs:
        raise ValueError(f"{dataset} pairs must be nested consecutively within frozen quads")


def load_authority(
    dataset: str,
    session_id: str,
    *,
    selection_path: Path = SELECTION_PATH,
) -> dict:
    if dataset not in DATASETS:
        raise ValueError(f"Unsupported dataset: {dataset}")
    selection_bytes = selection_path.read_bytes()
    selection = json.loads(selection_bytes)
    try:
        block = selection["datasets"][dataset]
    except KeyError as error:
        raise ValueError(f"Frozen selection lacks {dataset}") from error
    manifest_path = Path(block["manifest_path"])
    if not manifest_path.is_absolute():
        raise ValueError(f"{dataset} manifest_path must be absolute")
    manifest_bytes = manifest_path.read_bytes()
    observed_manifest_sha256 = _HELPERS.sha256_bytes(manifest_bytes)
    expected_manifest_sha256 = block["manifest_sha256"]
    if observed_manifest_sha256 != expected_manifest_sha256:
        raise ValueError(f"Frozen {dataset} population manifest digest differs")
    population = json.loads(manifest_bytes)
    if population.get("dataset_id") != dataset:
        raise ValueError(f"Frozen population identity is not {dataset}")
    captures = {row["session_id"]: row for row in population["captures"]}
    if len(captures) != len(population["captures"]):
        raise ValueError(f"Frozen {dataset} population contains duplicate sessions")
    _validate_units(dataset, block, captures)
    if session_id not in block["selected"]:
        raise ValueError(f"{session_id} is outside the frozen {dataset} cohort")
    if session_id not in captures:
        raise ValueError(f"{session_id} is absent from the frozen {dataset} population")
    return {
        "dataset": dataset,
        "selection_path": selection_path,
        "selection_sha256": _HELPERS.sha256_bytes(selection_bytes),
        "dataset_selection_sha256": _HELPERS.canonical_sha256(block),
        "manifest_path": manifest_path,
        "manifest_sha256": observed_manifest_sha256,
        "capture_entry": captures[session_id],
        "unit_ids": [
            unit["unit_id"] for unit in block["units"] if session_id in unit["session_ids"]
        ],
    }


def export_input(
    session_id: str,
    *,
    dataset: str,
    output_root: Path,
    api_base: str = DEFAULT_API_BASE,
    bulk_root: Path = DEFAULT_BULK_ROOT,
    tle_root: Path = DEFAULT_TLE_ROOT,
    selection_path: Path = SELECTION_PATH,
) -> dict:
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
    from leo.analysis.persistent_hop_trajectory import (
        PersistentHopTrajectoryConfig,
        reconstruct_persistent_hop_trajectories,
    )
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_sets

    authority = load_authority(dataset, session_id, selection_path=selection_path)
    capture_entry = authority["capture_entry"]
    product, api_artifact = _HELPERS.fetch_tracking(api_base, session_id)
    store = ScannerTrackingInputStore(bulk_root)
    try:
        source = store.load(session_id)
    finally:
        store.close()
    if source.input_manifest_sha256 != product["input_manifest_sha256"]:
        raise ValueError("Capture manifest differs from persisted tracking")
    if source.input_manifest_sha256 != capture_entry["manifest_sha256"]:
        raise ValueError(
            f"Scanner source input manifest differs from frozen {dataset} capture manifest"
        )
    if source.analysis_manifest_sha256 != product["analysis_manifest_sha256"]:
        raise ValueError("Analysis manifest differs from persisted tracking")
    if source.capture_start_utc_ns != int(capture_entry["capture_start_utc_ns"]):
        raise ValueError(f"Scanner source start differs from frozen {dataset} capture window")
    if source.sample_rate_hz != int(capture_entry["sample_rate_hz"]):
        raise ValueError(f"Scanner source sample rate differs from frozen {dataset} capture entry")
    if source.radio_id != capture_entry["radio_id"]:
        raise ValueError(f"Scanner source radio differs from frozen {dataset} capture entry")
    origin = source.timing.first_sample_estimate_utc_ns
    candidates = project_scanner_candidates(source)
    if len(candidates) != int(product["projected_candidate_count"]):
        raise ValueError("Projected candidate count differs from persisted tracking")
    config = PersistentHopTrajectoryConfig()
    trajectory = reconstruct_persistent_hop_trajectories(candidates, config=config)
    tracks, mapping = _HELPERS.track_rows(
        candidates, trajectory, product["track_reviews"]
    )
    arrays, raw_receipt = _HELPERS.raw_arrays(candidates, origin)
    nodes = _HELPERS.geometry_nodes(float(np.max(arrays["times"])))
    archive = TleArchiveReader(tle_root)
    snapshot = _HELPERS._snapshot(archive, product, origin)
    payload, exclusions = exclude_labelled_starlink_debris(archive.read(snapshot))
    catalogue = parse_element_sets(payload)
    numbers, position, velocity, candidate_receipt = _HELPERS.candidate_states(
        catalogue, product["track_reviews"], origin, nodes
    )
    initial, initial_receipt = _HELPERS.conditional_initial(product)
    arrays.update(
        nodes=nodes,
        position=position,
        velocity=velocity,
        numbers=numbers,
        initial=initial,
    )
    sources = _HELPERS.runtime_source_artifacts(
        (
            ScannerTrackingInputStore,
            project_scanner_candidates,
            reconstruct_persistent_hop_trajectories,
            propagate_candidate_states,
            exclude_labelled_starlink_debris,
            parse_element_sets,
        )
    )
    sources.append(
        {"path": str(Path(__file__).resolve()), "sha256": _HELPERS.sha256_file(Path(__file__))}
    )
    analysis_evidence_matches = (
        capture_entry["analysis_evidence_sha256"] == source.analysis_manifest_sha256
    )
    manifest = {
        "schema": "coherent-localization-bundle/v1",
        "dataset": dataset,
        "session_id": session_id,
        "origin_utc_ns": origin,
        "capture_window": {
            "policy": "one complete capture session; never split or pooled",
            "start_utc_ns": capture_entry["capture_start_utc_ns"],
            "end_utc_ns": capture_entry["capture_end_utc_ns"],
            "scanner_tracking_start_utc_ns": source.capture_start_utc_ns,
            "scanner_tracking_end_utc_ns": source.capture_end_utc_ns,
            "scanner_tracking_end_matches_frozen_capture_end": (
                source.capture_end_utc_ns == int(capture_entry["capture_end_utc_ns"])
            ),
            "end_semantics": (
                "frozen capture end and tracking counter-derived source-span end are distinct "
                "recorded authorities; neither is relabelled as the other"
            ),
        },
        "cohort_unit_ids": authority["unit_ids"],
        "tracks": tracks,
        "track_mapping": mapping,
        "raw_observations": raw_receipt,
        "candidate_bank": candidate_receipt,
        "initialization": initial_receipt,
        "provenance": {
            "scope": (
                "conditional known-site-candidate benchmark input; candidate reviews do not "
                "establish blind localization validation"
            ),
            "reference_truth_used_to_select_fit_or_hyperparameters": False,
            "input_manifest_sha256": source.input_manifest_sha256,
            "persisted_analysis_manifest_sha256": source.analysis_manifest_sha256,
            "frozen_analysis_evidence_sha256": capture_entry["analysis_evidence_sha256"],
            "analysis_evidence_matches_persisted_analysis": analysis_evidence_matches,
            "analysis_digest_policy": (
                "frozen admission evidence and current persisted reanalysis are recorded "
                "separately; equality is claimed only by the explicit comparison flag"
            ),
            "raw_recording_authority_digest": source.raw_recording_authority_digest,
            "trajectory_config_digest": str(config.digest),
            "tle_snapshot": {
                "provider": snapshot.provider,
                "collected_utc_ns": snapshot.collected_utc_ns,
                "digest": snapshot.digest,
                "labelled_debris_exclusion_count": len(exclusions),
            },
        },
        "artifacts": {
            "bundle_npz_sha256": None,
            "selection": {
                "path": str(authority["selection_path"]),
                "sha256": authority["selection_sha256"],
                "dataset_selection_sha256": authority["dataset_selection_sha256"],
            },
            "population_manifest": {
                "dataset": dataset,
                "path": str(authority["manifest_path"]),
                "sha256": authority["manifest_sha256"],
            },
            "capture_entry": {
                "dataset": dataset,
                "sha256": _HELPERS.canonical_sha256(capture_entry),
                "manifest_sha256": capture_entry["manifest_sha256"],
                "analysis_evidence_sha256": capture_entry["analysis_evidence_sha256"],
            },
            "tracking_api": api_artifact,
            "runtime_sources": sources,
        },
    }
    evaluation = {
        "schema": "coherent-localization-evaluation/v1",
        "dataset": dataset,
        "session_id": session_id,
        "reference_site": product["observer_site"],
        "policy": (
            "reference site is evaluation-only and is excluded from bundle.json, bundle.npz, "
            "candidate fill, fit selection, and hyperparameter selection"
        ),
        "conditional_known_site_candidate_provenance": True,
        "tracking_api_sha256": api_artifact["sha256"],
    }
    _HELPERS._write_bundle(output_root / session_id, arrays, manifest, evaluation)
    return {
        "dataset": dataset,
        "session_id": session_id,
        "raw_observations": len(arrays["times"]),
        "source_groups": raw_receipt["source_group_count"],
        "tracks": len(tracks),
        "track_observations": mapping["track_observations"],
        "candidates": len(numbers),
        "cohort_units": authority["unit_ids"],
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("session_id")
    parser.add_argument("--dataset", required=True, choices=DATASETS)
    parser.add_argument("--output-root", type=Path, default=ROOT / "scans")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--bulk-root", type=Path, default=DEFAULT_BULK_ROOT)
    parser.add_argument("--tle-root", type=Path, default=DEFAULT_TLE_ROOT)
    return parser.parse_args(argv)


def main(argv=None):
    arguments = parse_args(argv)
    started = time.monotonic()
    with _HELPERS.scan_timeout():
        result = export_input(
            arguments.session_id,
            dataset=arguments.dataset,
            output_root=arguments.output_root,
            api_base=arguments.api_base,
            bulk_root=arguments.bulk_root,
            tle_root=arguments.tle_root,
        )
    result["elapsed_s"] = time.monotonic() - started
    result["budget_s"] = _HELPERS.SCAN_TIMEOUT_S
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
