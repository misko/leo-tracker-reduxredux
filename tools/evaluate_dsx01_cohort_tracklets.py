"""Apply frozen S01 tracklet configurations to all DSX01 scans without retuning."""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path

import numpy as np
from compare_tracklet_methods import METHODS, assert_integrity
from evaluate_polynomial_tracklets import (
    DEFAULT_INPUT,
    OBSERVATION_FIELDS,
    REPO,
    digest,
    evaluate_lanes,
    json_default,
    save_results,
)
from review_unassociated_tracklets import replay_fitter
from tune_full_data_tracklets import annotate_full_data_quality

from leo.analysis.polynomial_tracklets import TrackConfig

OUTPUT = REPO / "reports/2026_10_17_dsx01_all_scans_tracklets"
CONFIG_ROOT = REPO / "reports/2026_10_17_dsx01_full_data_tuning"
LABELS = {
    "em": "EM",
    "graph": "Graph",
    "hough": "Hough",
    "mht": "Kalman/MHT",
    "baseline": "RANSAC reference",
}


def load_cohort(directory=DEFAULT_INPUT):
    manifest = json.loads((directory / "manifest.json").read_text())
    hashes = {"manifest.json": digest(directory / "manifest.json")}
    for name in ("sources.json", "dataset.json", "context-observations.jsonl", "membership.csv"):
        bound = next(r for r in manifest["files"] if r["path"] == name)
        p = directory / name
        assert digest(p) == bound["sha256"] and p.stat().st_size == bound["bytes"], name
        hashes[name] = digest(p)
    sources = json.loads((directory / "sources.json").read_text())
    dataset = json.loads((directory / "dataset.json").read_text())
    assert len({r["source_id"] for r in sources}) == len(sources) == dataset["recording_count"]
    rows = [
        {k: r[k] for k in OBSERVATION_FIELDS}
        for r in map(
            json.loads, (directory / "context-observations.jsonl").read_text().splitlines()
        )
    ]
    rows.sort(
        key=lambda r: (
            r["source_id"],
            r["time_s"],
            r["receiver"],
            r["channel"],
            r["observation_id"],
        )
    )
    assert len(rows) == dataset["full_scan_context_observation_count"]
    ids = {(r["source_id"], r["observation_id"]) for r in rows}
    assert len(ids) == len(rows)
    assert Counter(r["source_id"] for r in rows) == {
        r["source_id"]: r["observation_count"] for r in sources
    }
    assert all(np.isfinite(r[k]) for r in rows for k in ("time_s", "measured_cfo_hz"))
    for source in sources:
        assert {
            (r["receiver"], r["channel"]) for r in rows if r["source_id"] == source["source_id"]
        } == {(rx, ch) for rx in (1, 2) for ch in range(1, 9)}
    with (directory / "membership.csv").open() as stream:
        membership = list(csv.DictReader(stream))
    assert len(membership) == dataset["membership_count"]
    members = {(r["source_id"], r["observation_id"]) for r in membership}
    assert len(members) == dataset["unique_member_observation_count"]
    assert members <= ids
    return (
        rows,
        sources,
        membership,
        {
            "input_sha256": hashes,
            "dataset": dataset,
            "selection": "All whole-scan observations; original labels stripped",
        },
    )


def audit_result(rows, summary, exports, cfg):
    assert len(rows) == len(exports) == summary["observations"]
    expected = {(r["source_id"], r["observation_id"]) for r in rows}
    actual = {(r["source_id"], r["observation_id"]) for r in exports}
    assert expected == actual and len(actual) == len(exports)
    assert len({r["source_id"] for r in exports}) == 1
    for lane in summary["lanes"]:
        group = [
            r
            for r in exports
            if (r["receiver"], r["channel"]) == (lane["receiver"], lane["channel"])
        ]
        assert_integrity(
            {
                "tracks": lane["tracks"],
                "assignment": np.array([r["track_id"] for r in group]),
                "alias_lifts": np.array([r["alias_lift"] for r in group]),
            },
            np.array([r["time_s"] for r in group]),
            np.array([r["measured_cfo_hz"] for r in group]),
            cfg,
        )


def metrics(method, source_id, phase, summary, exports, members):
    tracks = [t for lane in summary["lanes"] for t in lane["tracks"]]
    sizes = [len(t["indices"]) for t in tracks]
    durations = [t["end_s"] - t["start_s"] for t in tracks]
    challenge = [r for r in exports if (r["source_id"], r["observation_id"]) in members]
    assert sum(sizes) == summary["assigned"]
    return {
        "method": method,
        "source_id": source_id,
        "phase": phase,
        "observations": summary["observations"],
        "associated": summary["assigned"],
        "associated_percent": 100 * summary["assigned"] / summary["observations"],
        "unassociated": summary["unresolved"],
        "tracks": len(tracks),
        "mean_points_per_track": sum(sizes) / len(tracks) if tracks else 0,
        "median_points_per_track": float(np.median(sizes)) if sizes else 0,
        "mean_duration_s": float(np.mean(durations)) if durations else 0,
        "supported_points": summary["residual_quality"]["no_structure_detected"][
            "associated_points"
        ],
        "flagged_points": summary["residual_quality"]["structure_flagged"]["associated_points"],
        "short_points": summary["residual_quality"]["insufficient_support"]["associated_points"],
        "challenge_observations": len(challenge),
        "challenge_associated": sum(r["track_id"] >= 0 for r in challenge),
        "track_sizes": sizes,
        "track_durations_s": durations,
    }


def aggregate(records):
    result = []
    for method in LABELS:
        for phase in ("primary", "recovered"):
            group = [r for r in records if (r["method"], r["phase"]) == (method, phase)]
            if not group:
                continue
            totals = {
                k: sum(r[k] for r in group)
                for k in (
                    "observations",
                    "associated",
                    "unassociated",
                    "tracks",
                    "supported_points",
                    "flagged_points",
                    "short_points",
                    "challenge_observations",
                    "challenge_associated",
                )
            }
            sizes = [n for r in group for n in r["track_sizes"]]
            durations = [n for r in group for n in r["track_durations_s"]]
            result.append(
                {
                    "method": method,
                    "phase": phase,
                    "scans": len(group),
                    **totals,
                    "associated_percent": 100 * totals["associated"] / totals["observations"],
                    "mean_points_per_track": totals["associated"] / totals["tracks"]
                    if sizes
                    else 0,
                    "median_points_per_track": float(np.median(sizes)) if sizes else 0,
                    "mean_duration_s": float(np.mean(durations)) if durations else 0,
                    "challenge_associated_percent": 100
                    * totals["challenge_associated"]
                    / totals["challenge_observations"]
                    if totals["challenge_observations"]
                    else 0,
                }
            )
    return result


def strip_lists(records):
    return [{k: v for k, v in r.items() if not isinstance(v, (dict, list))} for r in records]


def write_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run_method(method, output=OUTPUT):
    rows, sources, membership, provenance = load_cohort()
    members = {(r["source_id"], r["observation_id"]) for r in membership}
    selected = json.loads((CONFIG_ROOT / method / "selected.json").read_text())
    cfg = TrackConfig(**selected["config"])
    relaxed = replace(cfg, points_per_coefficient=2)
    module = importlib.import_module(METHODS[method])
    paths = [
        Path(module.__file__),
        Path(__file__),
        REPO / "src/leo/analysis/polynomial_tracklets.py",
        REPO / "src/leo/analysis/tracklet_fitting.py",
        REPO / "src/leo/analysis/residual_tracklets.py",
        REPO / "tools/review_unassociated_tracklets.py",
        REPO / "tools/tune_full_data_tracklets.py",
    ]
    hashes = {str(p.relative_to(REPO)): digest(p) for p in paths}
    folder = output / method
    folder.mkdir(parents=True, exist_ok=True)
    records, controls, region_records = [], [], []
    for source_index, source in enumerate(sources):
        source_id = source["source_id"]
        scan = [r for r in rows if r["source_id"] == source_id]
        primary, exports = evaluate_lanes(scan, cfg, module.fit_lane)
        annotate_full_data_quality(primary, exports)
        audit_result(scan, primary, exports, cfg)
        recovered, recovered_exports = evaluate_lanes(
            scan, relaxed, replay_fitter(primary, exports, cfg, module.fit_lane, True)
        )
        annotate_full_data_quality(recovered, recovered_exports)
        audit_result(scan, recovered, recovered_exports, relaxed)
        old = {r["observation_id"]: r for r in exports if r["track_id"] >= 0}
        for r in recovered_exports:
            if r["observation_id"] in old:
                prior = old[r["observation_id"]]
                assert (r["track_id"], r["alias_lift"], r["residual_hz"]) == (
                    prior["track_id"],
                    prior["alias_lift"],
                    prior["residual_hz"],
                )
        if source_id == "S01":
            frozen = json.loads(
                (
                    REPO
                    / "reports/2026_10_17_dsx01_residual_review"
                    / method
                    / "support2/results.json"
                ).read_text()
            )
            assert (
                recovered["assigned"],
                recovered["track_count"],
                recovered["residual_quality"],
            ) == (frozen["assigned"], frozen["track_count"], frozen["residual_quality"])
        for phase, summary, table in (
            ("primary", primary, exports),
            ("recovered", recovered, recovered_exports),
        ):
            summary.pop(
                "audit_regions", None
            )  # The older evaluator's three fixed audit windows are S01-only.
            summary.update(
                {
                    "method": method,
                    "source_id": source_id,
                    "source": source,
                    "phase": phase,
                    "provenance": {**provenance, "source_hashes": hashes},
                    "policy": "S01-selected parameters fixed; each scan fit independently; "
                    "no holdout or retuning.",
                }
            )
            save_results(folder / source_id / phase, summary, table)
            record = metrics(method, source_id, phase, summary, table, members)
            records.append(record)
            lookup = {r["observation_id"]: r for r in table}
            for region_id in sorted(
                {m["region_id"] for m in membership if m["source_id"] == source_id}
            ):
                group = [
                    lookup[m["observation_id"]]
                    for m in membership
                    if (m["source_id"], m["region_id"]) == (source_id, region_id)
                ]
                region_records.append(
                    {
                        "method": method,
                        "source_id": source_id,
                        "phase": phase,
                        "region_id": region_id,
                        "observations": len(group),
                        "associated": sum(r["track_id"] >= 0 for r in group),
                    }
                )
            print("COHORT", json.dumps(strip_lists([record])[0]), flush=True)
        # Matched frequency-shuffle null: every method gets identical permutations.
        shuffled = [dict(r) for r in scan]
        rng = np.random.default_rng(1701 + source_index)
        for rx in (1, 2):
            for ch in range(1, 9):
                ix = [
                    i for i, r in enumerate(shuffled) if (r["receiver"], r["channel"]) == (rx, ch)
                ]
                values = rng.permutation([shuffled[i]["measured_cfo_hz"] for i in ix])
                for i, v in zip(ix, values, strict=True):
                    shuffled[i]["measured_cfo_hz"] = float(v)
        null_primary, null_exports = evaluate_lanes(shuffled, cfg, module.fit_lane)
        annotate_full_data_quality(null_primary, null_exports)
        audit_result(shuffled, null_primary, null_exports, cfg)
        null_final, null_final_exports = evaluate_lanes(
            shuffled, relaxed, replay_fitter(null_primary, null_exports, cfg, module.fit_lane, True)
        )
        annotate_full_data_quality(null_final, null_final_exports)
        audit_result(shuffled, null_final, null_final_exports, relaxed)
        controls.append(
            {
                "source_id": source_id,
                "seed": 1701 + source_index,
                "observations": len(scan),
                "primary_associated": null_primary["assigned"],
                "recovered_associated": null_final["assigned"],
                "recovered_tracks": null_final["track_count"],
                "residual_quality": null_final["residual_quality"],
            }
        )
        (folder / "results.json").write_text(
            json.dumps(
                {
                    "records": records,
                    "controls": controls,
                    "config": selected["config"],
                    "provenance": provenance,
                    "source_hashes": hashes,
                },
                indent=2,
                default=json_default,
                allow_nan=False,
            )
            + "\n"
        )
        write_csv(folder / "per-scan.csv", strip_lists(records))
        write_csv(folder / "challenge-regions.csv", region_records)
    assert all(digest(REPO / p) == v for p, v in hashes.items())
    return records


def summarize(output=OUTPUT):
    records = []
    for method in LABELS:
        path = output / method / "results.json"
        if path.exists():
            records.extend(json.loads(path.read_text())["records"])
    totals = aggregate(records)
    write_csv(output / "comparison.csv", totals)
    write_csv(output / "per-scan.csv", strip_lists(records))
    (output / "summary.json").write_text(
        json.dumps(
            {
                "totals": totals,
                "records": records,
                "policy": "Whole-scan aggregate weighted by observations; mean track size is "
                "total associated / total tracks. Scans and receiver/channel lanes never joined. "
                "All original observations retained. Recovered includes the explicit "
                "sparse-support trial and provisional/flagged tracks.",
            },
            indent=2,
        )
        + "\n"
    )
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    names = [m for m in LABELS if any(r["method"] == m for r in totals)]
    x = np.arange(len(names))
    for phase, offset, color in (("primary", -0.2, "#92b4cb"), ("recovered", 0.2, "#267e69")):
        group = {r["method"]: r for r in totals if r["phase"] == phase}
        for ax, key, title in zip(
            axes,
            ("associated_percent", "mean_points_per_track", "tracks"),
            (
                "Associated GLRT observations (%)",
                "Mean GLRT points per track",
                "Tracklets across five scans",
            ),
            strict=True,
        ):
            bars = ax.bar(
                x + offset, [group[m][key] for m in names], 0.38, label=phase, color=color
            )
            ax.bar_label(bars, fmt="%.1f", fontsize=8, padding=3)
            ax.set(xticks=x, xticklabels=[LABELS[m] for m in names], title=title)
            ax.tick_params(axis="x", rotation=20)
            ax.grid(axis="y", alpha=0.15)
    axes[0].set_ylim(0, 105)
    axes[0].legend(frameon=False)
    fig.suptitle("DSX01 · All five scans · Frozen S01 configurations and append-only recovery")
    fig.tight_layout()
    for extension in ("png", "pdf"):
        fig.savefig(output / f"comparison.{extension}", dpi=160)
    plt.close(fig)
    print(json.dumps(totals, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", choices=METHODS)
    parser.add_argument("--summarize", action="store_true")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    started = time.perf_counter()
    if args.method:
        run_method(args.method, args.output)
    if args.summarize:
        summarize(args.output)
    print("ELAPSED_S", time.perf_counter() - started)


if __name__ == "__main__":
    main()
