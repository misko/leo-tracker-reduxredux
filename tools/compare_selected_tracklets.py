"""Label-invariant comparison of frozen full-data tracklet results."""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import os
import platform
import time
from collections import Counter
from itertools import combinations
from pathlib import Path

import numpy as np
from compare_tracklet_methods import METHODS
from evaluate_polynomial_tracklets import DEFAULT_INPUT, digest, load_observations
from render_full_data_tracklet_review import LABELS, load_selected
from tune_full_data_tracklets import OUTPUT

from leo.analysis.polynomial_tracklets import TrackConfig

DESTINATION = OUTPUT / "pairwise"


def choose_two(n):
    return n * (n - 1) // 2


def label(row):
    return (row["receiver"], row["channel"], row["track_id"])


def pair_statistics(first, second):
    """Compare membership sets and within-track observation pairs, never numeric IDs."""
    a = {r["observation_id"]: r for r in first}
    b = {r["observation_id"]: r for r in second}
    if len(a) != len(first) or len(b) != len(second) or a.keys() != b.keys():
        raise ValueError("Unique identical observation sets are required")
    for oid in a:
        if (a[oid]["receiver"], a[oid]["channel"]) != (b[oid]["receiver"], b[oid]["channel"]):
            raise ValueError("Observation lanes must match")
    assigned_a = {oid for oid, r in a.items() if r["track_id"] >= 0}
    assigned_b = {oid for oid, r in b.items() if r["track_id"] >= 0}
    common = assigned_a & assigned_b
    union = assigned_a | assigned_b
    qualified_a = {oid for oid in assigned_a if a[oid]["quality_status"] == "no_structure_detected"}
    qualified_b = {oid for oid in assigned_b if b[oid]["quality_status"] == "no_structure_detected"}
    cells = Counter((label(a[oid]), label(b[oid])) for oid in common)
    count_a, count_b = Counter(), Counter()
    for (left, right), n in cells.items():
        count_a[left] += n
        count_b[right] += n
    agreements = sum(choose_two(n) for n in cells.values())
    pairs_a = sum(choose_two(n) for n in count_a.values())
    pairs_b = sum(choose_two(n) for n in count_b.values())
    # Missing observations are excluded here and reported separately.
    # They never form a shared clutter cluster.
    pair_f1 = 2 * agreements / (pairs_a + pairs_b) if pairs_a + pairs_b else None
    best_a = sum(max(n for (aa, _), n in cells.items() if aa == key) for key in count_a)
    best_b = sum(max(n for (_, bb), n in cells.items() if bb == key) for key in count_b)
    delta = np.array([b[oid]["residual_hz"] - a[oid]["residual_hz"] for oid in sorted(common)])
    alias_offsets = {}
    for oid in common:
        key = (label(a[oid]), label(b[oid]))
        alias_offsets.setdefault(key, []).append(a[oid]["alias_lift"] - b[oid]["alias_lift"])
    inconsistent = sum(len(v) - Counter(v).most_common(1)[0][1] for v in alias_offsets.values())
    return {
        "observations": len(a),
        "both_assigned": len(common),
        "only_a": len(assigned_a - assigned_b),
        "only_b": len(assigned_b - assigned_a),
        "neither_assigned": len(a) - len(union),
        "assignment_jaccard": len(common) / len(union) if union else None,
        "assignment_status_agreement": 1 - len(assigned_a ^ assigned_b) / len(a),
        "supported_both": len(qualified_a & qualified_b),
        "supported_union": len(qualified_a | qualified_b),
        "supported_jaccard": len(qualified_a & qualified_b) / len(qualified_a | qualified_b)
        if qualified_a | qualified_b
        else None,
        "common_pair_f1": pair_f1,
        "same_track_pairs_a": pairs_a,
        "same_track_pairs_b": pairs_b,
        "same_track_pairs_both": agreements,
        "a_to_b_best_overlap_fraction": best_a / len(common) if common else None,
        "b_to_a_best_overlap_fraction": best_b / len(common) if common else None,
        "prediction_difference_rms_hz": float(np.sqrt(np.mean(delta**2))) if len(delta) else None,
        "prediction_difference_p95_abs_hz": float(np.quantile(abs(delta), 0.95))
        if len(delta)
        else None,
        "prediction_difference_over_150_hz": int(np.sum(abs(delta) > 150)),
        "relative_alias_inconsistent_points": inconsistent,
        "contingency": [
            {"a": list(aa), "b": list(bb), "points": n} for (aa, bb), n in sorted(cells.items())
        ],
    }


def benchmark(repeats):
    """Sequential single-core measurements of fit_lane, excluding I/O and report diagnostics."""
    rows, provenance = load_observations(DEFAULT_INPUT)
    lanes = []
    for rx in (1, 2):
        for ch in range(1, 9):
            group = [r for r in rows if (r["receiver"], r["channel"]) == (rx, ch)]
            lanes.append(
                (
                    np.array([r["time_s"] for r in group]),
                    np.array([r["measured_cfo_hz"] for r in group]),
                )
            )
    modules = {m: importlib.import_module(METHODS[m]) for m in LABELS}
    source_hashes = {m: digest(Path(module.__file__)) for m, module in modules.items()}
    samples = {m: [] for m in LABELS}
    order_rng = np.random.default_rng(1701)
    for repeat in range(repeats):
        for method in order_rng.permutation(list(LABELS)):
            selected, summary, _ = load_selected(method)
            cfg = TrackConfig(**selected["config"])
            started, cpu = time.perf_counter(), time.process_time()
            results = [modules[method].fit_lane(t, y, cfg) for t, y in lanes]
            elapsed, cpu_elapsed = time.perf_counter() - started, time.process_time() - cpu
            counts = (
                sum(len(r["tracks"]) for r in results),
                sum(int(np.sum(r["assignment"] >= 0)) for r in results),
            )
            assert counts == (summary["track_count"], summary["assigned"]), (method, counts)
            record = {
                "repeat": repeat,
                "wall_s": elapsed,
                "cpu_s": cpu_elapsed,
                "tracks": counts[0],
                "assigned": counts[1],
            }
            samples[method].append(record)
            print("BENCHMARK", method, record, flush=True)
        report = {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_affinity": sorted(os.sched_getaffinity(0)),
            "thread_environment": {
                k: os.environ.get(k)
                for k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
            },
            "policy": "Sequential, pinned to one allowed CPU; BLAS threads=1. "
            "No warm-up discarded. All 16 lanes per sample. Only fit_lane timed; "
            "loading, report diagnostics, plots excluded.",
            "repeats": repeat + 1,
            "samples": samples,
            "source_hashes": source_hashes,
            "input_provenance": provenance,
            "median_wall_s": {
                m: float(np.median([r["wall_s"] for r in values]))
                for m, values in samples.items()
                if values
            },
        }
        (DESTINATION / "runtime.json").write_text(json.dumps(report, indent=2) + "\n")
    assert all(digest(Path(modules[m].__file__)) == value for m, value in source_hashes.items())
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-repeats", type=int, default=0)
    args = parser.parse_args()
    DESTINATION.mkdir(parents=True, exist_ok=True)
    data = {m: load_selected(m)[2] for m in LABELS}
    records = []
    for a, b in combinations(LABELS, 2):
        record = {"a": a, "b": b, **pair_statistics(data[a], data[b])}
        records.append(record)
    sets = {
        m: {r["observation_id"] for r in rows if r["track_id"] >= 0} for m, rows in data.items()
    }
    qualified_sets = {
        m: {
            r["observation_id"]
            for r in rows
            if r["track_id"] >= 0 and r["quality_status"] == "no_structure_detected"
        }
        for m, rows in data.items()
    }
    report = {
        "pairwise": records,
        "methods": list(LABELS),
        "selected_inputs": {
            m: {
                "trial": load_selected(m)[0]["name"],
                "assignments_sha256": digest(
                    OUTPUT / m / "trials" / load_selected(m)[0]["name"] / "assignments.csv"
                ),
            }
            for m in LABELS
        },
        "observations": 4797,
        "assigned_union": len(set.union(*sets.values())),
        "assigned_intersection": len(set.intersection(*sets.values())),
        "supported_union": len(set.union(*qualified_sets.values())),
        "supported_intersection": len(set.intersection(*qualified_sets.values())),
        "definitions": {
            "assignment_jaccard": "Intersection / union of associated original IDs.",
            "common_pair_f1": "F1 of within-track unordered observation pairs, "
            "restricted to observations assigned by both methods. Labels include RX/channel. "
            "Numeric track IDs are never compared directly; unassociated is not a cluster.",
            "prediction_difference": "Model CFO difference on shared observations, "
            "modulo the alias period. Equal to residual_b - residual_a; "
            "each residual is within 450 Hz, so no additional wrapping is needed.",
            "support": "Same full-data residual policy as the selected tuning reports. "
            "Agreement does not establish physical identity or correctness.",
        },
    }
    (DESTINATION / "comparison.json").write_text(json.dumps(report, indent=2) + "\n")
    flat = [{k: v for k, v in r.items() if k != "contingency"} for r in records]
    with (DESTINATION / "comparison.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(flat[0]))
        writer.writeheader()
        writer.writerows(flat)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(17, 5))
    methods = list(LABELS)
    labels = ["EM", "Graph", "Hough", "MHT", "Ref."]
    fig.subplots_adjust(wspace=0.3)
    for ax, key, title in zip(
        axes,
        ("assignment_jaccard", "common_pair_f1", "supported_jaccard"),
        ("Associated-point overlap", "Track grouping agreement", "Supported-point overlap"),
        strict=True,
    ):
        matrix = np.eye(len(methods))
        for r in records:
            i, j = methods.index(r["a"]), methods.index(r["b"])
            matrix[i, j] = matrix[j, i] = r[key]
        im = ax.imshow(matrix, vmin=0.6, vmax=1, cmap="YlGnBu")
        for i in range(len(methods)):
            for j in range(len(methods)):
                ax.text(
                    j,
                    i,
                    f"{matrix[i, j]:.1%}",
                    ha="center",
                    va="center",
                    color="white" if matrix[i, j] > 0.85 else "black",
                )
        ax.set(
            xticks=range(len(methods)),
            yticks=range(len(methods)),
            xticklabels=labels,
            yticklabels=labels,
            title=title,
        )
    fig.colorbar(im, ax=axes.tolist(), shrink=0.75, label="Similarity", pad=0.025)
    fig.suptitle("DSX01 S01 · Pairwise comparison of selected full-data fits")
    fig.savefig(DESTINATION / "similarity.png", dpi=160, bbox_inches="tight")
    fig.savefig(DESTINATION / "similarity.pdf", bbox_inches="tight")
    plt.close(fig)
    print(json.dumps({k: v for k, v in report.items() if k != "pairwise"}, indent=2))
    for row in flat:
        print(json.dumps(row))
    if args.benchmark_repeats:
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
        benchmark(args.benchmark_repeats)


if __name__ == "__main__":
    main()
