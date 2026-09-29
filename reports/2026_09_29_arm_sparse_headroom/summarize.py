"""Audit exact candidates and summarize measured native sparse ARM calls."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import statistics
import sys
from pathlib import Path

from execute import HERE, digest, save

PREVIOUS = HERE.parent / "2026_09_29_arm_strides"
sys.path.insert(0, str(PREVIOUS))
spec = importlib.util.spec_from_file_location("stride_analysis", PREVIOUS / "analyze.py")
stride = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stride)


def distribution(values, *, deadlines=True):
    values = sorted(values)
    if not values:
        return None
    assert all(
        isinstance(value, (int, float)) and math.isfinite(value) and value >= 0 for value in values
    )
    result = {
        "count": len(values),
        "mean": statistics.mean(values),
        "p50": statistics.median(values),
        "p95": values[math.ceil(0.95 * len(values)) - 1],
        "max": max(values),
    }
    if deadlines:
        result.update(
            {
                "over_100_ms": sum(v > 100 for v in values),
                "at_least_120_ms": sum(v >= 120 for v in values),
            }
        )
    return result


def thermal_summary(records):
    available = [
        r
        for r in records
        if r["result"]["thermal_available_before"] and r["result"]["thermal_available_after"]
    ]
    deltas = [
        r["result"]["thermal_millidegrees_after"] - r["result"]["thermal_millidegrees_before"]
        for r in available
    ]
    return {
        "available_calls": len(available),
        "missing_calls": len(records) - len(available),
        "before_millidegrees": distribution(
            [r["result"]["thermal_millidegrees_before"] for r in available],
            deadlines=False,
        ),
        "after_millidegrees": distribution(
            [r["result"]["thermal_millidegrees_after"] for r in available],
            deadlines=False,
        ),
        "absolute_delta_millidegrees": distribution(
            [abs(value) for value in deltas], deadlines=False
        ),
        "warming_calls": sum(value > 0 for value in deltas),
        "flat_calls": sum(value == 0 for value in deltas),
        "cooling_calls": sum(value < 0 for value in deltas),
    }


def load(label, groups):
    folder = HERE / "local" / label
    manifest = json.loads((folder / "manifest.json").read_text())
    assert manifest["execution_panel_sha256"] == digest(HERE / "execution-panel.json")
    records, setups, summaries = [], [], []
    for group in groups:
        filename = group["id"] + ".jsonl"
        if filename not in manifest["files"]:
            continue
        assert digest(folder / filename) == manifest["files"][filename]
        rows = [json.loads(line) for line in (folder / filename).read_text().splitlines()]
        assert rows[0]["kind"] == "setup" and rows[-1]["kind"] == "summary"
        assert rows[-1]["destroy_status"] == 0
        assert len(rows[-1]["e2e_cpu_ms"]) == len(group["calls"])
        assert len(rows[-1]["e2e_wall_ms"]) == len(group["calls"])
        setups.append({"group": group["id"], **rows[0]})
        summaries.append({"group": group["id"], **rows[-1]})
        assert len(rows) == len(group["calls"]) + 2
        for call_index, (source, wrapper) in enumerate(
            zip(group["calls"], rows[1:-1], strict=True)
        ):
            result = wrapper["result"]
            assert result["kind"] == "call"
            assert result["sequence"] == source["sequence"]
            assert result["stride_ms"] == result["dwell_ms"] == 120
            assert [(r["receiver_id"], r["probe_start_ms"]) for r in result["rows"]] == [
                (0, 0),
                (1, 0),
            ]
            records.append(
                {
                    "group": group["id"],
                    "source": source,
                    "e2e_cpu_ms": rows[-1]["e2e_cpu_ms"][call_index],
                    "e2e_wall_ms": rows[-1]["e2e_wall_ms"][call_index],
                    **wrapper,
                }
            )
    return records, setups, summaries, manifest


def science(result):
    return [{k: v for k, v in row.items() if k != "timings_ms"} for row in result["rows"]]


def key(record):
    c = record["source"]["case"]["context"]
    return c["session_id"], c["visit_index"]


def summarize(labels, baseline):
    panel = json.loads((HERE / "execution-panel.json").read_text())
    with baseline.open() as lines:
        original = stride.original_inventories(lines)
    variants = {}
    baseline_science = {}
    baseline_results = {}
    for index, label in enumerate(labels):
        records, setups, summaries, manifest = load(label, panel["groups"])
        seen = {}
        for record in records:
            identity = key(record)
            values = science(record["result"])
            if identity in seen:
                assert seen[identity] == values, (label, identity, "repeat drift")
            seen[identity] = values
            if index == 0:
                baseline_science[identity] = values
                baseline_results[identity] = record["result"]
        if index:
            assert set(seen) == set(baseline_science), (label, "scientific identity set")
        counts = []
        for identity, values in seen.items():
            exact = values == baseline_science[identity]
            record = next(r for r in records if key(r) == identity)
            result = record["result"]
            reference = original[identity]
            recovered = sum(
                stride.matches(
                    stride.positives(reference[(r["receiver_id"], 0)]), stride.positives(r)
                )
                for r in result["rows"]
            )
            scheduled = sum(len(stride.positives(reference[(rx, 0)])) for rx in (0, 1))
            dense = sum(len(stride.positives(r)) for r in reference.values())
            case = {
                **record["source"]["case"],
                "ci16_sha256": record["source"]["case"]["raw_file"].split(".")[0],
            }
            projected = stride.projection(case, result, "sha256:" + manifest["binary_sha256"])
            original_projected = stride.projection(
                case, baseline_results[identity], "sha256:" + manifest["binary_sha256"]
            )
            counts.append(
                {
                    "session_id": identity[0],
                    "visit_index": identity[1],
                    "rate_hz": record["source"]["case"]["context"]["rate_hz"],
                    "current_native_rows_and_candidates_exact": exact,
                    "exact_rows_and_candidates": exact,
                    "candidate_entries": sum(len(r["candidates"]) for r in result["rows"]),
                    "positive_candidates": sum(len(stride.positives(r)) for r in result["rows"]),
                    "receiver_windows_run": len(result["rows"]),
                    "positive_receiver_windows": sum(
                        bool(stride.positives(r)) for r in result["rows"]
                    ),
                    "original_scheduled_positive_windows": sum(
                        bool(stride.positives(reference[(rx, 0)])) for rx in (0, 1)
                    ),
                    "original_scheduled_positive_windows_recovered": sum(
                        bool(
                            stride.matches(
                                stride.positives(reference[(r["receiver_id"], 0)]),
                                stride.positives(r),
                            )
                        )
                        for r in result["rows"]
                    ),
                    "original_hits_recovered": recovered,
                    "original_scheduled_hits": scheduled,
                    "original_dense_hits": dense,
                    "original_dense_windows": len(reference),
                    "original_dense_positive_windows": sum(
                        bool(stride.positives(r)) for r in reference.values()
                    ),
                    "projected_entries": sum(map(len, projected.values())),
                    "projected_science_exact": projected == original_projected,
                }
            )
        by_rate = []
        for rate in (2500000, 5000000, 7500000, 10000000):
            chosen = [r for r in records if r["result"]["rate_hz"] == rate]
            if not chosen:
                continue
            scientific = [c for c in counts if c["rate_hz"] == rate]
            phases = chosen[0]["result"]["profile"]
            by_rate.append(
                {
                    "rate_hz": rate,
                    "unique_dwells": len(scientific),
                    "call_cpu_ms": distribution([r["result"]["call_cpu_ms"] for r in chosen]),
                    "call_wall_ms": distribution([r["result"]["call_wall_ms"] for r in chosen]),
                    "e2e_cpu_ms": distribution([r["e2e_cpu_ms"] for r in chosen]),
                    "e2e_wall_ms": distribution([r["e2e_wall_ms"] for r in chosen]),
                    "serialization_cpu_ms": distribution(
                        [r["serialization_cpu_ms"] for r in chosen]
                    ),
                    "serialization_wall_ms": distribution(
                        [r["serialization_wall_ms"] for r in chosen]
                    ),
                    "stages": {
                        k: distribution([r["result"]["profile"][k] for r in chosen])
                        for k in phases
                        if k.endswith("_ms")
                    },
                    "row_stages_cpu_ms": {
                        k: distribution(
                            [
                                sum(row["timings_ms"][k] for row in r["result"]["rows"])
                                for r in chosen
                            ]
                        )
                        for k in chosen[0]["result"]["rows"][0]["timings_ms"]
                    },
                    "current_native_rows_and_candidates_exact": all(
                        c["current_native_rows_and_candidates_exact"] for c in scientific
                    ),
                    "exact_rows_and_candidates": all(
                        c["exact_rows_and_candidates"] for c in scientific
                    ),
                    "projected_science_exact": all(
                        c["projected_science_exact"] for c in scientific
                    ),
                    **{
                        k: sum(c[k] for c in scientific)
                        for k in (
                            "candidate_entries",
                            "positive_candidates",
                            "receiver_windows_run",
                            "positive_receiver_windows",
                            "original_scheduled_positive_windows",
                            "original_scheduled_positive_windows_recovered",
                            "original_hits_recovered",
                            "original_scheduled_hits",
                            "original_dense_hits",
                            "original_dense_windows",
                            "original_dense_positive_windows",
                            "projected_entries",
                        )
                    },
                    "max_peak_rss_kib": max(r["result"]["peak_rss_kib_after"] for r in chosen),
                    "thermal_available": all(
                        r["result"]["thermal_available_after"] for r in chosen
                    ),
                    "thermal": thermal_summary(chosen),
                    "by_repeat": {
                        str(i): distribution(
                            [
                                r["result"]["call_wall_ms"]
                                for r in chosen
                                if r["source"]["repeat"] == i
                            ]
                        )
                        for i in range(10)
                    },
                    "worst": [
                        {
                            "identity": key(r),
                            "repeat": r["source"]["repeat"],
                            "cpu_ms": r["result"]["call_cpu_ms"],
                            "wall_ms": r["result"]["call_wall_ms"],
                            "profile": r["result"]["profile"],
                        }
                        for r in sorted(
                            chosen, key=lambda r: r["result"]["call_wall_ms"], reverse=True
                        )[:5]
                    ],
                }
            )
        variants[label] = {
            "binding": manifest,
            "rates": by_rate,
            "science": counts,
            "setups": setups,
            "summaries": summaries,
        }
    output = {
        "schema": "native-sparse-headroom-comparison/v1",
        "comparison_authorities": {
            "current_native_exact": (
                "all row fields and ordered candidate fields except timings_ms, "
                "compared exactly to the first measured variant"
            ),
            "frozen_dense_reference": (
                "positive-hit recovery through the frozen stride matcher; "
                "this is not exact current-native equality"
            ),
            "projected_current_native_exact": (
                "diagnostic projector output compared exactly to the first measured variant"
            ),
        },
        "variants": variants,
        "reference_sha256": digest(baseline),
        "execution_panel_sha256": digest(HERE / "execution-panel.json"),
    }
    save(HERE / "comparison.json", output)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", nargs="+", required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.labels, args.baseline)
    for label, variant in result["variants"].items():
        for rate in variant["rates"]:
            print(
                label,
                rate["rate_hz"],
                rate["call_cpu_ms"],
                rate["call_wall_ms"],
                "exact",
                rate["exact_rows_and_candidates"],
            )
