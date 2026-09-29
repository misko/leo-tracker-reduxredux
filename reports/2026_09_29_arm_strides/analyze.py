"""Audit stride inventories, original-hit recovery and the actual tracker policy."""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import statistics
from pathlib import Path
from types import SimpleNamespace

from experiment import HERE, save, sha


def positives(row):
    return [c for c in row["candidates"] if c["margin"] >= 0.025]


def matches(reference, actual):
    adjacency = [
        [
            j
            for j, value in enumerate(actual)
            if abs(expected["epoch_sample"] - value["refined_epoch"]) <= 2
            and abs(expected["tracking_cfo_hz"] - value["tracking_cfo_hz"]) <= 8000
        ]
        for expected in reference
    ]
    owner = [-1] * len(actual)

    def augment(i, seen):
        for j in adjacency[i]:
            if j in seen:
                continue
            seen.add(j)
            if owner[j] < 0 or augment(owner[j], seen):
                owner[j] = i
                return True
        return False

    return sum(augment(i, set()) for i in range(len(reference)))


def projection(case, output, digest):
    """Diagnostic ONLY: use zero fractional offsets and synthetic UTC authority.

    This exercises the unchanged public projector; it never publishes an ARM
    result as a fractional-detector product or claims capture UTC qualification.
    """
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.contracts.scanner_tracking import TrackingCandidate, TrackingInput, TrackingProbe

    c = case["context"]
    timing = SimpleNamespace(
        sample_rate_hz=c["rate_hz"],
        session_id=c["session_id"],
        first_sample_bracket_width_ns=0,
        first_sample_estimate_utc_ns=1000000000000000,
        session_start_device_sample_counter=c["sample_start_counter"],
    )
    probes = tuple(
        TrackingProbe(
            c["visit_index"],
            row["receiver_id"],
            row["probe_index"],
            row["probe_start_ms"],
            c["target"]["channel"],
            c["target"]["edge"],
            c["target"]["rf_center_hz"] - c["actual_if_offset_hz"],
            c["sample_start_counter"],
            0,
            tuple(
                TrackingCandidate(
                    rank,
                    candidate["refined_epoch"],
                    0.0,
                    candidate["tracking_cfo_hz"],
                    candidate["exact_score"],
                    candidate["control_score"],
                    candidate["margin"],
                    candidate["margin"] >= 0.025,
                )
                for rank, candidate in enumerate(row["candidates"])
            ),
        )
        for row in output["rows"]
    )
    source = TrackingInput(
        c["session_id"],
        "adaptive",
        c["rate_hz"],
        "diagnostic-only",
        "diagnostic-only",
        c["manifest_sha256"],
        digest,
        "sha256:" + case["ci16_sha256"],
        timing,
        True,
        probes,
        capture_start_utc_ns=timing.first_sample_estimate_utc_ns,
    )
    starts = {(probe.receiver_id, probe.probe_index): probe.probe_start_ms for probe in probes}
    projected = {}
    next_start = {}
    for probe in sorted(probes, key=lambda p: (p.visit_index, p.receiver_id, p.probe_start_ms)):
        overlap_key = probe.visit_index, probe.receiver_id
        if probe.probe_start_ms < next_start.get(overlap_key, -1):
            continue
        next_start[overlap_key] = probe.probe_start_ms + source.probe_ms
        projected[(probe.receiver_id, probe.probe_start_ms)] = []
    for value in project_scanner_candidates(source):
        key = value.receiver_id, starts[(value.receiver_id, value.probe_index)]
        scientific = {
            k: v
            for k, v in dataclasses.asdict(value).items()
            if k not in {"candidate_id", "source_group_id", "probe_index"}
        }
        projected[key].append(scientific)
    return projected


def science(output):
    return {(r["receiver_id"], r["probe_start_ms"]): r["candidates"] for r in output["rows"]}


def original_inventories(lines):
    original = {}
    for line in lines:
        row = json.loads(line)
        if row["method"] != "original" or row["repeat"] != 0 or row["status"] != "ok":
            continue
        context = row["context"]
        identity = context["session_id"], context["visit_index"]
        if identity in original:
            raise ValueError(f"duplicate original baseline row: {identity}")
        inventory = {}
        for probe in row["result"]["probes"]:
            key = probe["receiver_id"], probe["probe_start_ms"]
            if key in inventory:
                raise ValueError(f"duplicate original probe: {identity + key}")
            inventory[key] = probe
        original[identity] = inventory
    return original


def summarize(folder, baseline):
    panel = json.loads((HERE / "panel.json").read_text())
    manifest = json.loads((folder / "manifest.json").read_text())
    assert manifest["complete"] and manifest["panel_sha256"] == sha(HERE / "panel.json")
    assert all(sha(folder / name) == digest for name, digest in manifest["files"].items())
    with baseline.open() as lines:
        original = original_inventories(lines)
    results = []
    for index, case in enumerate(panel["selected"]):
        c = case["context"]
        reference = original[(c["session_id"], c["visit_index"])]
        outputs = {}
        measured = {}
        for stride in panel["strides_ms"]:
            runs = [
                json.loads((folder / f"{index:03d}-{repeat}-{stride}.json").read_text())
                for repeat in range(panel["rounds"])
            ]
            assert all(
                run["context"] == c
                and run["stride_ms"] == stride
                and run["binary_sha256"] == manifest["binary_sha256"]
                for run in runs
            )
            assert all(science(run["output"]) == science(runs[0]["output"]) for run in runs)
            outputs[stride] = runs[0]["output"]
            measured[stride] = [r["output"]["timings_ms"]["detector_cpu"] for r in runs]
        dense = science(outputs[10])
        dense_positive_count = sum(len(positives(r)) for r in outputs[10]["rows"])
        projected = {
            stride: projection(case, out, "sha256:" + manifest["binary_sha256"])
            for stride, out in outputs.items()
        }
        for stride, output in outputs.items():
            actual = science(output)
            scheduled = {
                (rx, start)
                for start in range(0, panel["dwell_ms"] - 20 + 1, stride)
                for rx in (0, 1)
            }
            assert set(actual) == scheduled
            shared_identical = all(candidates == dense[key] for key, candidates in actual.items())
            original_full = sum(len(positives(r)) for r in reference.values())
            original_selected = sum(len(positives(reference[key])) for key in scheduled)
            recovered = sum(
                matches(positives(reference[key]), positives(row))
                for row in output["rows"]
                for key in [(row["receiver_id"], row["probe_start_ms"])]
            )
            assert recovered <= original_selected <= original_full
            native_positives = sum(len(positives(row)) for row in output["rows"])
            projected_shared_exact = all(
                key in projected[10] and candidates == projected[10][key]
                for key, candidates in projected[stride].items()
            )
            results.append(
                {
                    "case_index": index,
                    "rate_hz": c["rate_hz"],
                    "stride_ms": stride,
                    "windows": len(actual),
                    "candidate_entries": sum(map(len, actual.values())),
                    "native_positive_hits": native_positives,
                    "native_dense_positive_hits": dense_positive_count,
                    "original_dense_positive_hits": original_full,
                    "original_scheduled_positive_hits": original_selected,
                    "original_hits_recovered": recovered,
                    "shared_candidates_exact": shared_identical,
                    "projected_observations": len(projected[stride]),
                    "projected_candidate_entries": sum(map(len, projected[stride].values())),
                    "projected_shared_science_exact": projected_shared_exact,
                    "projected_inventory_equals_dense": projected[stride] == projected[10],
                    "detector_cpu_ms": measured[stride],
                }
            )
    aggregates = []
    count_keys = (
        "windows",
        "candidate_entries",
        "native_positive_hits",
        "native_dense_positive_hits",
        "original_dense_positive_hits",
        "original_scheduled_positive_hits",
        "original_hits_recovered",
        "projected_observations",
        "projected_candidate_entries",
    )
    for rate in (2500000, 5000000, 7500000, 10000000):
        for stride in panel["strides_ms"]:
            selected = [r for r in results if r["rate_hz"] == rate and r["stride_ms"] == stride]
            per_dwell = sorted(statistics.mean(r["detector_cpu_ms"]) for r in selected)
            timings = [t for r in selected for t in r["detector_cpu_ms"]]
            aggregates.append(
                {
                    "rate_hz": rate,
                    "stride_ms": stride,
                    "dwells": len(selected),
                    **{k: sum(r[k] for r in selected) for k in count_keys},
                    "shared_candidates_exact": all(r["shared_candidates_exact"] for r in selected),
                    "projected_shared_science_exact": all(
                        r["projected_shared_science_exact"] for r in selected
                    ),
                    "projected_inventory_equals_dense": all(
                        r["projected_inventory_equals_dense"] for r in selected
                    ),
                    "mean_detector_cpu_ms": statistics.mean(per_dwell),
                    "median_detector_cpu_ms": statistics.median(per_dwell),
                    "p95_dwell_mean_cpu_ms": per_dwell[math.ceil(0.95 * len(per_dwell)) - 1],
                    "max_individual_cpu_ms": max(timings),
                    "individual_runs_below_120ms": sum(t <= 120 for t in timings),
                    "individual_runs": len(timings),
                }
            )
    result = {
        "schema": "arm-stride-comparison/v1",
        "panel_sha256": sha(HERE / "panel.json"),
        "execution_manifest_sha256": sha(folder / "manifest.json"),
        "original_baseline_sha256": sha(baseline),
        "aggregates": aggregates,
        "cases": results,
        "original_reference": (
            "Frozen eight-candidate GLRT; predates deployed fractional refinement"
        ),
        "projection_scope": (
            "Unchanged public projector, diagnostic zero fractional offsets and "
            "synthetic UTC authority; not a published fractional tracking product"
        ),
        "timing_scope": manifest["timing_scope"],
    }
    save(HERE / "comparison.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort", type=Path, default=HERE / "local/arm")
    parser.add_argument("--baseline", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(summarize(args.cohort, args.baseline)["aggregates"], indent=2))
