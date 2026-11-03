"""Read-only integrity and semantic audit for the frozen T4 primary campaign."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SNAPSHOT = HERE / "primary-source"


def frozen_union_ids(unit: str) -> set[int]:
    adapter = HERE.parent / "2026_09_30_broad_prior_acquisition"
    sys.path.insert(0, str(adapter))
    try:
        from common import load_scan

        return set(load_scan(unit).bank.norad_ids)
    finally:
        sys.path.remove(str(adapter))


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return "sha256:" + value.hexdigest()


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def selected_units() -> list[str]:
    selection = json.loads((SNAPSHOT / "5-selection.json").read_text())
    groups = [selection["selected"][name] for name in ("DS9", "DS10", "DS11")]
    return [group[index]["unit_id"] for index in range(max(map(len, groups)))
            for group in groups if index < len(group)]


def audit(folder: Path, *, require_complete: bool) -> dict:
    failures: list[str] = []
    expected = selected_units()
    bindings = json.loads((SNAPSHOT / "bindings.json").read_text())
    expected_sources = {path: item["sha256"] for path, item in bindings.items()}
    for _path, item in bindings.items():
        snapshot = ROOT / item["snapshot"]
        require(snapshot.is_file(), f"missing source snapshot: {snapshot}", failures)
        if snapshot.is_file():
            require(digest(snapshot) == item["sha256"],
                    f"source snapshot digest mismatch: {snapshot}", failures)

    documents: dict[str, dict] = {}
    campaign_sources: dict[str, str] | None = None
    crossing_diagnostics: dict[str, dict] = {}
    for path in sorted(folder.glob("batch-*/*-joint.json")):
        receipt = json.loads(path.read_text())
        unit = receipt.get("unit_id")
        require(unit not in documents, f"duplicate receipt: {unit}", failures)
        documents[unit] = receipt
        seal_path = path.with_suffix(".seal.json")
        require(seal_path.is_file(), f"missing seal: {unit}", failures)
        if seal_path.is_file():
            seal = json.loads(seal_path.read_text())
            require(seal.get("prediction_sha256") == digest(path),
                    f"seal mismatch: {unit}", failures)
        require(receipt.get("schema") == "fixed-height-joint-greedy/v1",
                f"schema mismatch: {unit}", failures)
        receipt_sources = receipt.get("source_sha256", {})
        if campaign_sources is None:
            campaign_sources = receipt_sources
        require(receipt_sources == campaign_sources,
                f"source bindings differ within campaign: {unit}", failures)
        for source_path, source_digest in receipt_sources.items():
            require(Path(source_path).is_file(), f"missing bound source: {source_path}", failures)
            if Path(source_path).is_file():
                require(digest(Path(source_path)) == source_digest,
                        f"bound source changed after execution: {source_path}", failures)
        require(receipt.get("student_degrees_of_freedom") == 4.0,
                f"Student-t setting mismatch: {unit}", failures)
        require(receipt.get("seed_limit") == 3, f"seed limit mismatch: {unit}", failures)
        require(receipt.get("height_msl_m") == 30.48,
                f"fixed height mismatch: {unit}", failures)
        height_bindings = receipt.get("height_input_bindings", {})
        grid_path = Path(height_bindings.get("grid_path", ""))
        grid_digest = height_bindings.get("grid_sha256")
        require(grid_path.is_file(), f"missing GEOID grid: {unit}: {grid_path}", failures)
        require(isinstance(grid_digest, str) and grid_digest.startswith("sha256:"),
                f"missing GEOID grid digest: {unit}", failures)
        if grid_path.is_file() and isinstance(grid_digest, str):
            require(digest(grid_path) == grid_digest,
                    f"GEOID grid digest mismatch: {unit}", failures)
        inputs = receipt.get("inputs", {})
        require(bool(inputs), f"missing input bindings: {unit}", failures)
        for input_path, expected_digest in inputs.items():
            source = Path(input_path)
            require(source.is_file(), f"missing input: {unit}: {source}", failures)
            if source.is_file():
                require(digest(source) == expected_digest,
                        f"input digest mismatch: {unit}: {source}", failures)

        evidence_paths = [Path(path) for path in inputs
                          if path.endswith(f"/{unit}.json")]
        original_meta_paths = [Path(path) for path in inputs
                               if path.endswith(f"/{unit}-orbits.json")
                               and "extended" not in path]
        extended_meta_paths = [Path(path) for path in inputs
                               if path.endswith(f"/{unit}-orbits-extended.json")]
        require(len(evidence_paths) == len(original_meta_paths) == len(extended_meta_paths) == 1,
                f"orbit/evidence binding set is ambiguous: {unit}", failures)
        if extended_meta_paths:
            extended_metadata = json.loads(extended_meta_paths[0].read_text())
            crossings = extended_metadata.get("extension", {}).get(
                "post_admission_radius_threshold_crossings", []
            )
            if crossings:
                union = frozen_union_ids(unit)
                crossing_ids = [int(item["norad_id"]) for item in crossings]
                intersection = sorted(set(crossing_ids) & union)
                times = [float(value) for item in crossings for value in item["crossing_times_s"]]
                crossing_diagnostics[unit] = {
                    "crossing_count": len(crossings),
                    "crossing_norad_ids": crossing_ids,
                    "crossing_time_bounds_s": [min(times), max(times)],
                    "frozen_union_count": len(union),
                    "crossing_ids_in_frozen_union": intersection,
                }
                require(not intersection,
                        f"post-admission radius crossing intersects fit union: {unit}: "
                        f"{intersection}", failures)

        fits = receipt.get("fits", [])
        require(len(fits) <= 3, f"too many seed fits: {unit}", failures)
        proposal = receipt.get("proposal")
        if proposal is not None:
            expected_seeds = proposal.get("seeds", [])[:len(fits)]
            require([fit.get("seed") for fit in fits] == expected_seeds,
                    f"fit seeds do not reset from proposal list: {unit}", failures)
            require(proposal.get("track_count") == receipt.get("planned_factors"),
                    f"proposal did not score full scan: {unit}", failures)
        for index, fit in enumerate(fits):
            label = f"{unit} seed {index}"
            objectives = fit.get("objectives", [])
            steps = fit.get("accepted_step_norms", [])
            require(len(steps) == max(0, len(objectives) - 1),
                    f"objective/step count mismatch: {label}", failures)
            require(all(right < left for left, right in zip(
                objectives, objectives[1:], strict=False)),
                f"nondecreasing accepted objective: {label}", failures)
            associations = fit.get("associations", [])
            if objectives:
                require(len(associations) == receipt.get("planned_factors"),
                        f"fit does not associate full scan: {label}", failures)
            if fit.get("reason") == "objective_stable":
                require(bool(steps) and steps[-1] < 1e-4,
                        f"objective_stable without small accepted step: {label}", failures)
            if fit.get("converged"):
                require(fit.get("reason") in {"stationary", "objective_stable"},
                        f"unsupported convergence reason: {label}", failures)
        scored = [fit for fit in fits if fit.get("objectives")]
        if scored:
            winner = min(scored, key=lambda fit: fit["objectives"][-1])
            require(receipt.get("best") == winner,
                    f"best is not lowest objective among all attempted seeds: {unit}", failures)
            expected_status = "converged_local_mode" if winner["converged"] else "unresolved"
            require(receipt.get("status") == expected_status,
                    f"status does not follow winning seed: {unit}", failures)
            if evidence_paths and original_meta_paths and extended_meta_paths:
                evidence = json.loads(evidence_paths[0].read_text())
                source = json.loads(Path(evidence["source"]["path"]).read_text())
                relative_times = [
                    (timestamp - source["start_utc_ns"]) / 1e9
                    for track in evidence["tracks"] for timestamp in track["times_utc_ns"]
                ]
                clock = winner["mean"][2]
                epochs = winner["satellite_epoch_s"] or [0.0]
                query_min = min(relative_times) + clock + min(epochs)
                query_max = max(relative_times) + clock + max(epochs)
                original = json.loads(original_meta_paths[0].read_text())
                extended = json.loads(extended_meta_paths[0].read_text())
                original_bounds = (original["knot_start_s"], original["knot_stop_s"])
                extended_bounds = tuple(extended["extension"]["new_query_bounds_s"])
                receipt["_audit_query_bounds_s"] = [query_min, query_max]
                require(query_min >= original_bounds[0] and query_max <= original_bounds[1],
                        f"winning mode exceeds original candidate-union time envelope: {unit}",
                        failures)
                require(query_min >= extended_bounds[0] and query_max <= extended_bounds[1],
                        f"winning mode exceeds extended four-knot support: {unit}", failures)
        else:
            require(receipt.get("status") in {"unresolved", "error"},
                    f"unscored receipt has invalid status: {unit}", failures)

    for unit in expected:
        if unit in crossing_diagnostics:
            continue
        metadata_path = (Path.home() / ".cache/leo/research/fixed_height_greedy/orbits"
                         / f"{unit}-orbits-extended.json")
        if not metadata_path.is_file():
            continue
        metadata = json.loads(metadata_path.read_text())
        crossings = metadata.get("extension", {}).get(
            "post_admission_radius_threshold_crossings", []
        )
        if crossings:
            union = frozen_union_ids(unit)
            crossing_ids = [int(item["norad_id"]) for item in crossings]
            intersection = sorted(set(crossing_ids) & union)
            times = [float(value) for item in crossings for value in item["crossing_times_s"]]
            crossing_diagnostics[unit] = {
                "crossing_count": len(crossings),
                "crossing_norad_ids": crossing_ids,
                "crossing_time_bounds_s": [min(times), max(times)],
                "frozen_union_count": len(union),
                "crossing_ids_in_frozen_union": intersection,
            }
            require(not intersection,
                    f"post-admission radius crossing intersects fit union: {unit}: "
                    f"{intersection}", failures)

    missing = sorted(set(expected) - set(documents))
    extra = sorted(set(documents) - set(expected))
    require(not extra, f"unexpected units: {extra}", failures)
    if require_complete:
        require(not missing, f"missing units: {missing}", failures)
    statuses = Counter(document.get("status", "missing") for document in documents.values())
    snapshot_matches_execution = campaign_sources == expected_sources
    require(snapshot_matches_execution,
            "frozen source snapshot does not exactly match executed source bindings", failures)
    return {
        "schema": "fixed-height-joint-greedy-audit/v1",
        "campaign": str(folder),
        "expected_units": len(expected),
        "sealed_receipts": len(documents),
        "missing_units": missing,
        "status_counts": dict(sorted(statuses.items())),
        "checks_passed": not failures,
        "failures": failures,
        "snapshot_matches_execution": snapshot_matches_execution,
        "winning_query_bounds_s": {
            unit: document["_audit_query_bounds_s"] for unit, document in documents.items()
            if "_audit_query_bounds_s" in document
        },
        "post_admission_radius_crossings": crossing_diagnostics,
        "scope": (
            "receipt, seal, frozen source, input, seed, full-scan, objective, "
            "time-support, and selection checks"
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.folder, require_complete=args.require_complete)
    encoded = json.dumps(result, indent=2) + "\n"
    if args.output is not None:
        args.output.write_text(encoded)
    print(encoded, end="")
    raise SystemExit(0 if result["checks_passed"] else 1)
