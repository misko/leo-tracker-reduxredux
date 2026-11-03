#!/usr/bin/env python3
"""Reproduce the fixed-eight wideband candidate comparison.

This is a diagnostic comparator.  It deliberately uses the comparator bounds
already used for the retained detector comparison: continuous symbol epoch
within two samples and tracking CFO within 10 kHz.  It does not turn tolerant
matches into candidate-ID equality.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


VISITS = (126, 191, 193, 283, 301, 307, 346, 418)
DETAIL_VISITS = (126, 191, 193, 346)
EPOCH_TOLERANCE = 2.0
CFO_TOLERANCE_HZ = 10_000.0
MARGIN_GATE = 0.025


def load_call(path: Path) -> dict:
    for line in path.read_text().splitlines():
        item = json.loads(line)
        if isinstance(item.get("result"), dict):
            return item["result"]
    raise ValueError(f"no call result in {path}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def candidate_summary(rank: int, candidate: dict, passing: bool) -> dict:
    fractional = candidate.get("fractional_epoch") or {}
    status = fractional.get("status")
    margin = fractional.get("margin")
    if status != "complete":
        gate_outcome = "fractional_incomplete"
    elif margin is None or margin <= 0 or margin < MARGIN_GATE:
        gate_outcome = "margin_below_0.025"
    else:
        gate_outcome = "passing"
    if passing != (gate_outcome == "passing"):
        raise AssertionError(f"projection gate disagreement at candidate rank {rank}")
    return {
        "rank": rank,
        "coarse_epoch": candidate["coarse_epoch"],
        "coarse_bin": candidate["coarse_bin"],
        "coarse_cfo_hz": candidate["coarse_cfo_hz"],
        "fine_cfo_hz": candidate["fine_cfo_hz"],
        "acquired_cfo_hz": candidate["acquired_cfo_hz"],
        "integer_epoch": candidate["epoch"],
        "tracking_cfo_hz": fractional.get("tracking_cfo_hz"),
        "integer_tracking_cfo_hz": candidate["tracking_cfo_hz"],
        "integer_exact_score": candidate["exact_score"],
        "integer_control_score": candidate["control_score"],
        "integer_margin": candidate["margin"],
        "fractional_status": status,
        "fractional_offset": fractional.get("offset_samples"),
        "fractional_exact_score": fractional.get("exact_score"),
        "fractional_control_score": fractional.get("control_score"),
        "fractional_margin": margin,
        "gate_outcome": gate_outcome,
    }


def reference_summary(item: dict, selected_ids: set[str]) -> dict:
    candidate = item["candidate"]
    return {
        "candidate_id": item["expected"]["candidate_id"],
        "rank": candidate["rank"],
        "integer_epoch": candidate["integer_epoch"],
        "fractional_offset": candidate["fractional_offset"],
        "tracking_cfo_hz": candidate["tracking_cfo_hz"],
        "exact_score": candidate["exact_score"],
        "control_score": candidate["control_score"],
        "margin": candidate["margin"],
        "used_by_reference_track": item["expected"]["candidate_id"] in selected_ids,
    }


def distance(reference: dict, actual: dict) -> tuple[float, float] | None:
    actual_epoch = actual["integer_epoch"] + actual["fractional_offset"]
    reference_epoch = reference["integer_epoch"] + reference["fractional_offset"]
    epoch_delta = abs(actual_epoch - reference_epoch)
    cfo_delta = abs(actual["tracking_cfo_hz"] - reference["tracking_cfo_hz"])
    if epoch_delta > EPOCH_TOLERANCE or cfo_delta > CFO_TOLERANCE_HZ:
        return None
    return epoch_delta, cfo_delta


def best_matching(references: list[dict], actuals: list[dict]) -> list[tuple[int, int]]:
    """Return maximum-cardinality, minimum-distance deterministic matching."""
    best: tuple[int, float, tuple[tuple[int, int], ...]] | None = None

    def walk(index: int, used: set[int], pairs: list[tuple[int, int]], cost: float) -> None:
        nonlocal best
        if index == len(references):
            candidate = (-len(pairs), cost, tuple(pairs))
            if best is None or candidate < best:
                best = candidate
            return
        walk(index + 1, used, pairs, cost)
        for actual_index, actual in enumerate(actuals):
            if actual_index in used:
                continue
            delta = distance(references[index], actual)
            if delta is None:
                continue
            epoch_delta, cfo_delta = delta
            used.add(actual_index)
            pairs.append((index, actual_index))
            walk(
                index + 1,
                used,
                pairs,
                cost + epoch_delta / EPOCH_TOLERANCE + cfo_delta / CFO_TOLERANCE_HZ,
            )
            pairs.pop()
            used.remove(actual_index)

    walk(0, set(), [], 0.0)
    assert best is not None
    return list(best[2])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[5])
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("comparison.json"))
    args = parser.parse_args()

    report = Path(__file__).resolve().parent
    selection_path = report.parent / "missing-rx0-selection.json"
    projection_input_path = (
        args.root
        / "reports/2026_09_30_native_adaptive_deployment/tracking/projection-inputs.jsonl"
    )
    selection = json.loads(selection_path.read_text())
    selected_by_visit = {item["visit"]: item for item in selection["visits"]}
    projected = json.loads((report / "fixed8/projected-rx0-gates.json").read_text())

    references_by_visit: dict[int, list[dict]] = {visit: [] for visit in VISITS}
    for line in projection_input_path.read_text().splitlines():
        item = json.loads(line)
        source = item.get("source")
        if (
            source
            and item.get("candidate")
            and item.get("expected")
            and source["visit"] in references_by_visit
            and source["receiver"] == 0
            and source["probe_index"] == 0
        ):
            references_by_visit[source["visit"]].append(item)

    result = {
        "schema": "org.leo.native-adaptive-wideband-fixed8-comparison/v1",
        "scope": {
            "diagnostic_only": True,
            "production_detector_changed": False,
            "hardware_or_rf_used": False,
            "matching_epoch_tolerance_samples": EPOCH_TOLERANCE,
            "matching_cfo_tolerance_hz": CFO_TOLERANCE_HZ,
            "projection_margin_gate": MARGIN_GATE,
        },
        "inputs": {
            "selection": str(selection_path.relative_to(args.root)),
            "selection_sha256": sha256(selection_path),
            "projection_inputs": str(projection_input_path.relative_to(args.root)),
            "projection_inputs_sha256": sha256(projection_input_path),
        },
        "summary": {
            "visits": len(VISITS),
            "reference_passing_candidates": 0,
            "wideband_passing_candidates": len(projected),
            "matched_candidates": 0,
            "missing_reference_candidates": 0,
            "additional_wideband_candidates": 0,
            "source_groups_recovered": 0,
            "selected_reference_track_candidates_recovered": 0,
        },
        "visits": [],
        "scalar_interval_comparison": [],
    }

    for visit in VISITS:
        projected_visit = sorted(
            (item for item in projected if item["visit"] == visit), key=lambda item: item["rank"]
        )
        passing_ranks = {item["rank"] for item in projected_visit}
        call = load_call(report / f"fixed8/wrapper-{visit}.jsonl")
        row = next(row for row in call["rows"] if row["receiver_id"] == 0)
        actual_all = [
            candidate_summary(rank, candidate, rank in passing_ranks)
            for rank, candidate in enumerate(row["candidates"])
        ]
        actual_passing = [item for item in actual_all if item["gate_outcome"] == "passing"]
        selected_ids = set(selected_by_visit[visit]["reference_used_candidate_ids"])
        references = sorted(
            (reference_summary(item, selected_ids) for item in references_by_visit[visit]),
            key=lambda item: item["rank"],
        )
        pairs = best_matching(references, actual_passing)
        matched_reference = {left for left, _ in pairs}
        matched_actual = {right for _, right in pairs}
        matches = []
        for left, right in pairs:
            reference = references[left]
            actual = actual_passing[right]
            epoch_delta, cfo_delta = distance(reference, actual)  # type: ignore[misc]
            matches.append(
                {
                    "reference_rank": reference["rank"],
                    "reference_candidate_id": reference["candidate_id"],
                    "reference_used_by_track": reference["used_by_reference_track"],
                    "wideband_rank": actual["rank"],
                    "continuous_epoch_delta_samples": epoch_delta,
                    "tracking_cfo_delta_hz": cfo_delta,
                }
            )
        missing = [item for index, item in enumerate(references) if index not in matched_reference]
        additional = [item for index, item in enumerate(actual_passing) if index not in matched_actual]
        selected_recovered = sum(
            1
            for item in matches
            if item["reference_candidate_id"] in selected_ids
        )
        visit_result = {
            "visit": visit,
            "channel": selected_by_visit[visit]["channel"],
            "source_group_id": selected_by_visit[visit]["source_group_id"],
            "inventory": {
                "candidate_count": row["candidate_count"],
                "retained_peak_count": row["retained_peak_count"],
                "coarse_gate_skipped_count": row["coarse_gate_skipped_count"],
                "conditioned_fallback_count": row["conditioned_fallback_count"],
                "actual_executed_glrt_calls": row["actual_executed_glrt_calls"],
            },
            "reference_candidates": references,
            "wideband_candidates": actual_all,
            "matches": matches,
            "missing_reference_candidates": missing,
            "additional_wideband_candidates": additional,
            "source_group_recovered": bool(matches),
            "selected_reference_track_candidate_count": len(selected_ids),
            "selected_reference_track_candidates_recovered": selected_recovered,
        }
        result["visits"].append(visit_result)
        result["summary"]["reference_passing_candidates"] += len(references)
        result["summary"]["matched_candidates"] += len(matches)
        result["summary"]["missing_reference_candidates"] += len(missing)
        result["summary"]["additional_wideband_candidates"] += len(additional)
        result["summary"]["source_groups_recovered"] += int(bool(matches))
        result["summary"]["selected_reference_track_candidates_recovered"] += selected_recovered

    for visit in DETAIL_VISITS:
        interval = load_call(report / f"fixed8/wrapper-{visit}.jsonl")
        scalar = load_call(report / f"scalar4/scalar-{visit}.jsonl")
        interval_candidates = [row["candidates"] for row in interval["rows"]]
        scalar_candidates = [row["candidates"] for row in scalar["rows"]]
        if interval_candidates != scalar_candidates:
            raise AssertionError(f"scalar/interval candidate mismatch at visit {visit}")
        result["scalar_interval_comparison"].append(
            {
                "visit": visit,
                "receiver_rows": len(interval_candidates),
                "candidate_rows": sum(len(row) for row in interval_candidates),
                "candidate_payloads_exact": True,
                "excluded_from_equality": [
                    "timings_ms",
                    "interval_screened_cells",
                    "interval_possible_peaks",
                    "interval_repaired_cells",
                ],
            }
        )

    expected = {
        "reference_passing_candidates": 23,
        "wideband_passing_candidates": 23,
        "matched_candidates": 21,
        "missing_reference_candidates": 2,
        "additional_wideband_candidates": 2,
        "source_groups_recovered": 8,
        "selected_reference_track_candidates_recovered": 6,
    }
    for key, value in expected.items():
        if result["summary"][key] != value:
            raise AssertionError(f"{key}: {result['summary'][key]} != {value}")
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
