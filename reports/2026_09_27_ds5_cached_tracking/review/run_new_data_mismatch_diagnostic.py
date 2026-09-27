#!/usr/bin/env python3
"""Post-outcome all-window diagnostic for the nine new-data mismatches."""
from __future__ import annotations

import argparse
import ctypes as ct
import hashlib
import json
import math
import signal
import sys
from contextlib import ExitStack
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "native"
DEPLOY = Path("/home/mouse9911/gits/leo-adaptive-position-deploy")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEPLOY))
sys.path.insert(0, str(DEPLOY / "src"))
from tracking import Observation, circular_samples, reference_match  # noqa: E402
from tools.presence_dwell import NativeDwell  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def observation(value: dict) -> Observation:
    return Observation(**value)


def positive(value: dict | None) -> bool:
    return bool(value and value["supported"] and value["exact"] - value["control"] > 0.025)


def mismatches(receipt: dict) -> dict[tuple[str, int], dict]:
    rows = {}
    for row in receipt["rows"]:
        if positive(row.get("reference")) and not row["matched_reference"]:
            key = (row["case_id"], row["rx"])
            if key in rows:
                raise ValueError("duplicate receiver visit")
            if not positive(row.get("observation")) or row.get("reason") != "cache_hit":
                raise ValueError("mismatch is not an accepted cached positive")
            rows[key] = row
    return rows


def fitted(result, rank_position: int) -> Observation | None:
    confirmation = result.confirmations[rank_position]
    if not confirmation.candidate_count:
        return None
    if confirmation.candidate_count != 1:
        raise ValueError("diagnostic expects the frozen one-candidate profile")
    candidate = confirmation.candidates[0]
    return Observation(
        int(result.rank.order[rank_position]),
        candidate.epoch + candidate.fractional_offset_samples,
        candidate.tracking_cfo_hz,
        candidate.exact_score,
        candidate.control_score,
        bool(candidate.fractional_complete),
        "fitted",
        candidate.acquired_cfo_hz,
    )


def comparison(cached: Observation, candidate: Observation | None, rate: int) -> dict:
    if candidate is None:
        return {"candidate_present": False, "coordinate_match": False,
                "positive_match": False, "timing_error_us": None, "cfo_error_hz": None}
    delta = (cached.window - candidate.window) * (rate // 50)
    delta += cached.epoch_samples - candidate.epoch_samples
    timing = abs(circular_samples(delta, rate)) / rate * 1e6
    cfo = abs(cached.cfo_hz - candidate.cfo_hz)
    coordinate = timing <= 2 and cfo <= 8000
    return {"candidate_present": True, "coordinate_match": coordinate,
            "positive_match": reference_match(cached, candidate, rate),
            "candidate_positive": candidate.positive,
            "timing_error_us": timing, "cfo_error_hz": cfo}


def asdict(value: Observation | None) -> dict | None:
    if value is None:
        return None
    return {name: getattr(value, name) for name in (
        "window", "epoch_samples", "cfo_hz", "exact", "control", "supported",
        "timing_kind", "scoring_cfo_hz")}


def run(output: Path) -> dict:
    signal.alarm(120)
    if output.exists():
        raise FileExistsError(output)
    dataset_path = ROOT / "new_data" / "cases.json"
    v6_path, partial_path = ROOT / "new_data_v6.json", ROOT / "new_data_partial2.json"
    inputs = {path: sha256(path) for path in (dataset_path, v6_path, partial_path)}
    dataset = json.loads(dataset_path.read_text())
    v6, partial = json.loads(v6_path.read_text()), json.loads(partial_path.read_text())
    if v6["dataset_sha256"] != inputs[dataset_path] or partial["dataset_sha256"] != inputs[dataset_path]:
        raise ValueError("replays do not bind the selected new dataset")
    left, right = mismatches(v6), mismatches(partial)
    if set(left) != set(right) or len(left) != 9:
        raise ValueError("replay mismatch sets are not the same nine receiver visits")
    cases = {case["case_id"]: case for case in dataset["cases"]}
    for case_id, _ in left:
        case = cases[case_id]
        if case["split"] != "dev" or case["is_holdout"] or case["evaluation_role"] != "newdevelopment":
            raise ValueError("post-outcome diagnostic selected nondevelopment IQ")

    library = NATIVE / "libblind_strided_v4.so"
    build_path = library.with_name(library.name + ".build.json")
    build = json.loads(build_path.read_text())
    if sha256(library) != v6["baseline_sha256"] or sha256(library) != build["binary_sha256"]:
        raise ValueError("packed diagnostic library differs from frozen replay baseline")
    protected = {**inputs, library: build["binary_sha256"], build_path: sha256(build_path),
                 Path(__file__).resolve(): sha256(Path(__file__).resolve())}
    for name, expected in build["sources_sha256"].items():
        path = Path(name)
        if sha256(path) != expected:
            raise ValueError(f"frozen native source changed: {path}")
        protected[path] = expected

    rows = []
    workspaces = {}
    with ExitStack() as stack:
        for key in sorted(left):
            original = left[key]
            case = cases[key[0]]
            geometry = (case["rate_hz"], case["edge"])
            if geometry not in workspaces:
                workspaces[geometry] = stack.enter_context(NativeDwell(library, *geometry, 512))
            raw_path = dataset_path.parent / case["raw_npy"]["path"]
            expected_raw = case["raw_npy"]["sha256"].removeprefix("sha256:")
            if sha256(raw_path) != expected_raw:
                raise ValueError("selected IQ hash changed")
            raw = np.load(raw_path, allow_pickle=False)
            if raw.dtype != np.dtype("<i2") or raw.shape != (case["rate_hz"] * 120 // 1000, 2, 2):
                raise ValueError("selected IQ geometry differs")
            caller_hash = hashlib.sha256(raw).hexdigest()
            result = workspaces[geometry].run(raw[:, key[1], :], maximum=6, seeded=False)
            if result.confirmation_count != 6 or result.confirmation_window_mask != 0x3F:
                raise ValueError("all six windows were not freshly fitted")
            candidates = [fitted(result, index) for index in range(6)]
            reference = observation(original["reference"])
            if candidates[0] != reference:
                raise ValueError("all-window top result differs from frozen replay reference")
            cached = {"v6": observation(original["observation"]),
                      "partial2": observation(right[key]["observation"])}
            if not reference_match(cached["v6"], cached["partial2"], case["rate_hz"]):
                raise ValueError("the two cached variants do not identify the same trajectory")
            matches = {variant: [comparison(value, candidate, case["rate_hz"])
                                 for candidate in candidates]
                       for variant, value in cached.items()}
            if hashlib.sha256(raw).hexdigest() != caller_hash or sha256(raw_path) != expected_raw:
                raise ValueError("diagnostic mutated selected IQ")
            rows.append({
                "case_id": key[0], "receiver": key[1], "rate_hz": case["rate_hz"],
                "edge": case["edge"], "channel": case["channel"],
                "visit_index": case["visit_index"], "raw_sha256": expected_raw,
                "rank_order": [int(result.rank.order[k]) for k in range(6)],
                "rank_scores": [float(result.rank.scores[k]) for k in range(6)],
                "cached": {name: asdict(value) for name, value in cached.items()},
                "fitted_candidates": [asdict(value) for value in candidates],
                "comparisons": matches,
                "any_positive_fitted_match": {
                    name: any(item["positive_match"] for item in values)
                    for name, values in matches.items()},
                "diagnostic_native_cpu_ms": result.total_cpu_ms,
                "diagnostic_native_wall_ms": result.total_wall_ms,
            })

    post = {path: sha256(path) for path in protected}
    if post != protected:
        raise ValueError("diagnostic input or source changed during execution")
    corroborated = sum(row["any_positive_fitted_match"]["v6"] for row in rows)
    payload = {
        "schema": "org.leo.research.new-data-mismatch-diagnostic/v1",
        "scope": "post-outcome development-only nine-mismatch diagnostic",
        "selection_is_post_outcome": True,
        "qualification_result": False,
        "timing_valid_for_performance_claim": False,
        "holdout_opened": False,
        "maximum_confirmations": 6,
        "seeded": False,
        "profile": "frozen-v4-library-packed-NativeDwell",
        "source_receipts": {"dataset_sha256": inputs[dataset_path],
            "v6_sha256": inputs[v6_path], "partial2_sha256": inputs[partial_path],
            "native_binary_sha256": build["binary_sha256"],
            "native_build_receipt_sha256": protected[build_path],
            "runner_sha256": protected[Path(__file__).resolve()]},
        "summary": {"receiver_visits": len(rows),
            "v6_positive_fitted_matches": corroborated,
            "v6_without_positive_fitted_match": len(rows) - corroborated,
            "partial2_positive_fitted_matches": sum(
                row["any_positive_fitted_match"]["partial2"] for row in rows)},
        "rows": rows,
    }
    output.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "new_data_mismatch_diagnostic.json")
    args = parser.parse_args()
    run(args.output.resolve())
