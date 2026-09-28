"""Independent full-cohort inventory, parity, and positive-hit audit."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

MARGIN_GATE = 0.025
EPOCH_TOLERANCE = 2
HIT_CFO_TOLERANCE_HZ = 8_000.0
SCIENCE_CFO_TOLERANCE_HZ = 2e-6
SCIENCE_SCORE_TOLERANCE = 2e-9
WINDOW_KEYS = {(receiver, probe) for receiver in range(2) for probe in range(11)}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def maximum_matches(reference: list[dict], native: list[dict]) -> int:
    """Maximum-cardinality bipartite matching under timing/CFO association."""
    adjacency = [
        [
            index
            for index, actual in enumerate(native)
            if abs(int(expected["epoch_sample"]) - int(actual["epoch"])) <= EPOCH_TOLERANCE
            and abs(float(expected["tracking_cfo_hz"]) - float(actual["tracking_cfo_hz"]))
            <= HIT_CFO_TOLERANCE_HZ
        ]
        for expected in reference
    ]
    owner = [-1] * len(native)

    def augment(reference_index: int, seen: set[int]) -> bool:
        for native_index in adjacency[reference_index]:
            if native_index in seen:
                continue
            seen.add(native_index)
            if owner[native_index] < 0 or augment(owner[native_index], seen):
                owner[native_index] = reference_index
                return True
        return False

    return sum(augment(index, set()) for index in range(len(reference)))


def science_mismatch(actual: dict, expected: dict) -> tuple[bool, dict[str, float]]:
    deltas = {
        "epoch": abs(int(actual["epoch"]) - int(expected["epoch_sample"])),
        "acquired_cfo_hz": abs(
            float(actual["acquired_cfo_hz"]) - float(expected["acquired_cfo_hz"])
        ),
        "tracking_cfo_hz": abs(
            float(actual["tracking_cfo_hz"]) - float(expected["tracking_cfo_hz"])
        ),
        "exact_score": abs(float(actual["exact_score"]) - float(expected["exact_score"])),
        "control_score": abs(float(actual["control_score"]) - float(expected["control_score"])),
        "margin": abs(float(actual["margin"]) - float(expected["margin"])),
    }
    mismatch = (
        deltas["epoch"] != 0
        or deltas["acquired_cfo_hz"] > SCIENCE_CFO_TOLERANCE_HZ
        or deltas["tracking_cfo_hz"] > SCIENCE_CFO_TOLERANCE_HZ
        or deltas["exact_score"] > SCIENCE_SCORE_TOLERANCE
        or deltas["control_score"] > SCIENCE_SCORE_TOLERANCE
        or deltas["margin"] > SCIENCE_SCORE_TOLERANCE
    )
    return mismatch, deltas


def empty_counts() -> dict[str, int]:
    return {
        "dwells": 0,
        "windows": 0,
        "candidates": 0,
        "reference_positive_windows": 0,
        "native_positive_windows": 0,
        "windows_with_recovered_hit": 0,
        "reference_positive_hits": 0,
        "native_positive_hits": 0,
        "recovered_positive_hits": 0,
        "ordered_mismatched_windows": 0,
        "ordered_mismatched_candidates": 0,
        "missing_native_windows": 0,
    }


def summarize(
    selected: list[dict],
    baseline: dict[tuple[str, int], dict[tuple[int, int], dict]],
    native: dict[tuple[str, int], dict[tuple[int, int], dict]],
) -> dict:
    totals = empty_counts()
    by_rate: dict[int, dict[str, int]] = defaultdict(empty_counts)
    maximum_deltas = defaultdict(float)
    mismatch_examples = []
    for context in selected:
        case = (context["session_id"], context["visit_index"])
        rate = int(context["rate_hz"])
        if case not in baseline:
            raise ValueError(f"selected case absent from sealed baseline: {case}")
        expected_windows = baseline[case]
        if set(expected_windows) != WINDOW_KEYS:
            raise ValueError(f"sealed baseline window inventory differs: {case}")
        totals["dwells"] += 1
        by_rate[rate]["dwells"] += 1
        actual_windows = native.get(case, {})
        for key in sorted(WINDOW_KEYS):
            expected = expected_windows[key]["candidates"]
            if len(expected) != 8:
                raise ValueError(f"sealed candidate inventory differs: {case} {key}")
            actual_row = actual_windows.get(key)
            actual = [] if actual_row is None else actual_row["candidates"]
            for counts in (totals, by_rate[rate]):
                counts["windows"] += 1
                counts["candidates"] += 8
            reference_hits = [item for item in expected if item["margin"] >= MARGIN_GATE]
            native_hits = [item for item in actual if item["margin"] >= MARGIN_GATE]
            matched = maximum_matches(reference_hits, native_hits)
            for counts in (totals, by_rate[rate]):
                counts["reference_positive_windows"] += bool(reference_hits)
                counts["native_positive_windows"] += bool(native_hits)
                counts["windows_with_recovered_hit"] += matched > 0
                counts["reference_positive_hits"] += len(reference_hits)
                counts["native_positive_hits"] += len(native_hits)
                counts["recovered_positive_hits"] += matched
            window_mismatch = actual_row is None or len(actual) != 8
            mismatched_candidates = 8 if actual_row is None else abs(8 - len(actual))
            if actual_row is None:
                totals["missing_native_windows"] += 1
                by_rate[rate]["missing_native_windows"] += 1
            for index, (left, right) in enumerate(zip(actual, expected, strict=False)):
                mismatch, deltas = science_mismatch(left, right)
                for field, delta in deltas.items():
                    maximum_deltas[field] = max(maximum_deltas[field], delta)
                if mismatch:
                    window_mismatch = True
                    mismatched_candidates += 1
                    if len(mismatch_examples) < 32:
                        mismatch_examples.append(
                            {
                                "ordinal": context["ordinal"],
                                "receiver_id": key[0],
                                "probe_index": key[1],
                                "candidate_rank": index,
                                "deltas": deltas,
                                "reference_margin": right["margin"],
                                "native_margin": left["margin"],
                            }
                        )
            if window_mismatch:
                totals["ordered_mismatched_windows"] += 1
                by_rate[rate]["ordered_mismatched_windows"] += 1
            totals["ordered_mismatched_candidates"] += mismatched_candidates
            by_rate[rate]["ordered_mismatched_candidates"] += mismatched_candidates
    return {
        "totals": totals,
        "by_rate": {str(rate): counts for rate, counts in sorted(by_rate.items())},
        "maximum_ordered_deltas": dict(maximum_deltas),
        "ordered_mismatch_examples": mismatch_examples,
    }


def load_baseline(path: Path) -> dict:
    result = {}
    for line in path.read_text().splitlines():
        row = json.loads(line)
        context = row["context"]
        if row["method"] == "original" and row["repeat"] == 0 and row["status"] == "ok":
            case = (context["session_id"], context["visit_index"])
            result[case] = {
                (probe["receiver_id"], probe["probe_index"]): probe
                for probe in row["result"]["probes"]
            }
    return result


def load_native(path: Path) -> dict:
    result = {}
    for line in path.read_text().splitlines():
        record = json.loads(line)
        context = record["context"]
        case = (context["session_id"], context["visit_index"])
        if case in result:
            raise ValueError(f"duplicate native case: {case}")
        if record["returncode"] != 0 or record["stderr"] or len(record["rows"]) != 22:
            raise ValueError(f"invalid native execution: {case}")
        windows = {}
        for row in record["rows"]:
            key = (row["receiver_id"], row["probe_index"])
            if key in windows:
                raise ValueError(f"duplicate native window: {case} {key}")
            if row["candidate_count"] != 8 or row["retained_peak_count"] != 8:
                raise ValueError(f"native candidate count differs: {case} {key}")
            if len(row["candidates"]) != 8:
                raise ValueError(f"native candidate payload differs: {case} {key}")
            windows[key] = row
        if set(windows) != WINDOW_KEYS:
            raise ValueError(f"native window inventory differs: {case}")
        result[case] = windows
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--build", type=Path)
    parser.add_argument("--compressed", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    manifest = json.loads(arguments.manifest.read_text())
    selected = manifest["selected"]
    cases = [(item["session_id"], item["visit_index"]) for item in selected]
    if len(selected) != 704 or len(set(cases)) != 704:
        raise ValueError("selected manifest must contain 704 unique cases")
    if not manifest["complete"] or manifest["processed_dwells"] != 704:
        raise ValueError("native cohort manifest is incomplete")
    baseline = load_baseline(arguments.baseline)
    native = load_native(arguments.native)
    if set(native) != set(cases):
        raise ValueError("native case inventory differs from selected manifest")
    summary = summarize(selected, baseline, native)
    summary.update(
        {
            "schema": "arm-full-optimization-independent-summary/v1",
            "manifest_sha256": sha256(arguments.manifest),
            "native_uncompressed_sha256": sha256(arguments.native),
            "baseline_sha256": sha256(arguments.baseline),
            "margin_gate": MARGIN_GATE,
            "hit_epoch_tolerance_samples": EPOCH_TOLERANCE,
            "hit_cfo_tolerance_hz": HIT_CFO_TOLERANCE_HZ,
            "science_cfo_tolerance_hz": SCIENCE_CFO_TOLERANCE_HZ,
            "science_score_tolerance": SCIENCE_SCORE_TOLERANCE,
        }
    )
    if arguments.build and arguments.compressed:
        summary["archived_artifacts"] = {
            "build_sha256": sha256(arguments.build),
            "compressed_native_sha256": sha256(arguments.compressed),
            "compressed_native_bytes": arguments.compressed.stat().st_size,
        }
    arguments.output.write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
