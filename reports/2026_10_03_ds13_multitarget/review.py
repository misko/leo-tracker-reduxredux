"""Validate and compare common frozen replay outputs; no hidden accuracy claims."""
from __future__ import annotations
import csv
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from common import ROOT, SOURCE, SESSIONS, load_scan, baseline, write_assignments, digest


def read_records(paths):
    result = []
    for path in paths:
        with Path(path).open() as stream:
            for row in csv.DictReader(stream):
                if row["scan"] not in SESSIONS:
                    raise ValueError(f"Unknown scan label in {path}: {row['scan']}")
                for key in ("row_index", "catalog_number", "receiver", "channel"):
                    row[key] = int(row[key])
                row["time_s"] = float(row["time_s"])
                row["residual_hz"] = float(row["residual_hz"])
                result.append(row)
    return result


def longest_segment(times, max_gap=3.):
    times = np.unique(np.sort(times))
    if not len(times):
        return 0., 0
    parts = np.split(times, np.flatnonzero(np.diff(times) > max_gap)+1)
    best = max(parts, key=lambda p: (np.ptp(p), len(p)))
    return float(np.ptp(best)), len(best)


def validate_and_score(data, records):
    a = data["arrays"]
    columns = {int(n): i for i, n in enumerate(a["catalog_numbers"])}
    rows_seen, pairs_seen = set(), set()
    groups = Counter()
    by_track = defaultdict(list)
    residuals, native, gain = [], [], []
    for record in records:
        row = record["row_index"]
        col = columns[record["catalog_number"]]
        group = int(a["group"][row])
        if row in rows_seen or (group, col) in pairs_seen:
            raise ValueError("Nonexclusive hard assignments")
        if row in data["duplicate_rows"]:
            raise ValueError("Alias-period copy assigned as an independent peak")
        if not np.isfinite(data["log_gain"][row, col]):
            raise ValueError("Assignment outside shared visibility/retrieval gate")
        for name in ("receiver", "channel"):
            if record[name] != int(a[name][row]):
                raise ValueError("CSV provenance mismatch")
        if not np.isclose(record["time_s"], a["times_s"][row], atol=1e-9, rtol=0):
            raise ValueError("CSV time mismatch")
        if not np.isclose(record["residual_hz"], a["residual_hz"][row, col], atol=1e-6, rtol=0):
            raise ValueError("CSV residual mismatch")
        rows_seen.add(row); pairs_seen.add((group, col)); groups[group] += 1
        by_track[(record["catalog_number"], record["receiver"])].append(record)
        residuals.append(float(a["residual_hz"][row, col]))
        native.append(float(data["native_residual_hz"][row, col]))
        gain.append(float(data["log_gain"][row, col]))
    rms = lambda x: float(np.sqrt(np.mean(np.square(x)))) if len(x) else None
    tracks = []
    for (number, rx), selected in sorted(by_track.items()):
        times = np.asarray([r["time_s"] for r in selected])
        y = np.asarray([r["residual_hz"] for r in selected])
        span, count = longest_segment(times)
        fits = []
        t = (times - np.mean(times)) / 30.
        for degree in (1, 2):
            design = np.column_stack([t**p for p in range(degree+1)])
            fits.append(rms(y-design @ np.linalg.lstsq(design, y, rcond=None)[0])
                        if len(times) > degree+1 and np.linalg.matrix_rank(design) == degree+1 else None)
        tracks.append(dict(catalog_number=number, receiver=rx, assigned_peaks=len(selected),
                           envelope_span_s=float(np.ptp(times)), longest_segment_s=span,
                           longest_segment_groups=count, rms_hz=rms(y),
                           linear_rms_hz=fits[0], quadratic_rms_hz=fits[1]))
    return dict(assigned_peaks=len(records), observed_groups_with_assignments=len(groups),
                simultaneous_target_groups=sum(n >= 2 for n in groups.values()),
                maximum_simultaneous_targets=max(groups.values(), default=0),
                rms_normalized_hz=rms(residuals), rms_native_hz=rms(native),
                shared_raw_assignment_gain=float(sum(gain)),
                tracks_with_segment_at_least_30s=sum(t["longest_segment_s"] >= 30 for t in tracks),
                tracks=tracks, validation="exclusive rows and satellite/group pairs; no alias copies; exact source fields")


def timeline(label, data, methods):
    keys = [(int(n), rx) for n in data["arrays"]["catalog_numbers"] for rx in (0, 1)]
    fig, axes = plt.subplots(1, len(methods), figsize=(18, 10), sharey=True, sharex=True)
    for ax, (name, records) in zip(axes, methods.items()):
        for rx in (0, 1):
            selected = [r for r in records if r["receiver"] == rx]
            ax.scatter([r["time_s"] for r in selected],
                       [keys.index((r["catalog_number"], rx)) for r in selected],
                       s=4, linewidths=0, color=("#0072B2", "#D55E00")[rx], alpha=.65)
        ax.set_title(name)
        ax.set_xlim(0, 300)
        ax.set_xticks([0, 100, 200, 300])
        ax.grid(axis="x", alpha=.2)
        ax.set_xlabel("Receive time (s)")
    axes[0].set_yticks(range(len(keys)), [f"{n} / RX{rx}" for n, rx in keys])
    axes[0].invert_yaxis()
    fig.suptitle(f"DS13 scan {label} · concurrent-target prototype comparison\n"
                 "Same archived orbit/RX/RF fit and peak evidence; no seed-ownership gate", fontsize=15)
    fig.text(.5, .012, "Dots are assigned detections, not continuous coverage. Blue RX0 · orange RX1. "
             "Frozen in-sample replay; methods use different temporal selection rules.", ha="center", fontsize=10)
    fig.tight_layout(rect=(0, .035, 1, .94))
    fig.savefig(ROOT/f"scan-{label.lower()}-timelines.png", dpi=160)
    plt.close(fig)


def residual_details(datasets, all_methods):
    cases = [("A", 64361, 0), ("B", 62953, 1)]
    names = ["Baseline", "Activity", "History", "Tracklet"]
    fig, axes = plt.subplots(4, 2, figsize=(14, 12), sharex="col", sharey="col")
    colors = {1:"#0072B2", 2:"#E69F00", 3:"#009E73", 4:"#CC79A7"}
    for column, (label, number, rx) in enumerate(cases):
        for i, name in enumerate(names):
            ax = axes[i, column]
            rows = [r for r in all_methods[label][name] if r["catalog_number"] == number and r["receiver"] == rx]
            for ch in range(1, 5):
                rr = [r for r in rows if r["channel"] == ch]
                ax.scatter([r["time_s"] for r in rr], [r["residual_hz"] for r in rr],
                           s=9, color=colors[ch], alpha=.7, label=f"CH{ch}")
            ax.axhline(0, color=".45", lw=.7)
            ax.set_title(f"{name} · scan {label} · {number}/RX{rx} · {len(rows)} peaks")
            ax.set_ylabel("GLRT − frozen orbit (Hz)")
            ax.grid(alpha=.15)
            ax.set_xlim((35, 145) if label == "A" else (130, 240))
    for ax in axes[-1]: ax.set_xlabel("Receive time (s)")
    axes[0,0].legend(ncol=4, fontsize=8)
    fig.suptitle("Residual comparison · identical physical predictions, different associations\n"
                 "Residuals normalized to 11.085 GHz; no per-track state/line/quadratic subtracted", fontsize=14)
    fig.tight_layout(rect=(0, 0, 1, .94))
    fig.savefig(ROOT/"key-track-residuals.png", dpi=150)
    plt.close(fig)


def main():
    sources = {
        "Activity": [ROOT/"activity/assignments.csv"],
        "History": [ROOT/"history/results/beam32-state"/f"{sid}-assignments.csv" for sid in SESSIONS.values()],
        "Tracklet": [ROOT/"tracklet/outputs/assignments.csv"],
    }
    loaded = {name: read_records(paths) for name, paths in sources.items()}
    result = dict(scope="Stage A: frozen physical-fit association replay, not held-out or location validation",
                  caution="RMS values use different selected points; do not rank accuracy by RMS or assignment count alone.",
                  sources={str(p): digest(p) for paths in sources.values() for p in paths}, scans=[])
    datasets, all_methods = {}, {}
    for label in SESSIONS:
        data = load_scan(label)
        datasets[label] = data
        started = time.monotonic()
        records, score = baseline(data)
        elapsed = time.monotonic()-started
        write_assignments(ROOT/"baseline"/f"{label}-assignments.csv", records)
        methods = {"Baseline": records, **{name: [r for r in rows if r["scan"] == label] for name, rows in loaded.items()}}
        all_methods[label] = methods
        metrics = {name: validate_and_score(data, rows) for name, rows in methods.items()}
        metrics["Baseline"]["runtime_s"] = elapsed
        base = {(r["row_index"], r["catalog_number"]) for r in records}
        for name, rows in methods.items():
            selected = {(r["row_index"], r["catalog_number"]) for r in rows}
            metrics[name]["added_vs_baseline"] = len(selected-base)
            metrics[name]["removed_vs_baseline"] = len(base-selected)
        result["scans"].append(dict(scan=label, session=data["session"],
                                    total_peaks=len(data["arrays"]["times_s"]),
                                    exact_alias_copies_removed=len(data["duplicate_rows"]),
                                    provenance=data["provenance"], methods=metrics))
        timeline(label, data, methods)
    residual_details(datasets, all_methods)
    (ROOT/"comparison.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    fields = ["scan", "method", "assigned_peaks", "simultaneous_target_groups", "rms_normalized_hz",
              "tracks_with_segment_at_least_30s", "added_vs_baseline", "removed_vs_baseline"]
    with (ROOT/"comparison.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for scan in result["scans"]:
            for method, m in scan["methods"].items():
                writer.writerow(dict(scan=scan["scan"], method=method, **{f:m[f] for f in fields[2:]}))
    track_fields = ["scan", "method", "catalog_number", "receiver", "assigned_peaks", "envelope_span_s",
                    "longest_segment_s", "longest_segment_groups", "rms_hz", "linear_rms_hz", "quadratic_rms_hz"]
    with (ROOT/"tracks.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=track_fields)
        writer.writeheader()
        for scan in result["scans"]:
            for method, metrics in scan["methods"].items():
                writer.writerows(dict(scan=scan["scan"], method=method, **t) for t in metrics["tracks"])
    print(json.dumps([{ "scan": s["scan"], "methods": {n:{k:v for k,v in m.items() if k != "tracks"}
                      for n,m in s["methods"].items()}} for s in result["scans"]], indent=2))


if __name__ == "__main__": main()
