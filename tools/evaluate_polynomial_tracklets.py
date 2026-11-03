"""Reproduce alias-aware polynomial clustering of every frozen DSX01 S01 point.

This is a lane-level descriptive experiment, not satellite identification. Residual
checks are conditional on fitted memberships and cannot establish generalization.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import time
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
from numpy.polynomial.legendre import legfit, legval

REPO = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO / "reports/2026_10_16_dsx01_fast_association_losses"
DEFAULT_OUTPUT = REPO / "reports/2026_10_17_dsx01_tracklets"
OBSERVATION_FIELDS = (
    "source_id", "observation_id", "time_s", "receiver", "channel",
    "actual_rf_hz", "measured_cfo_hz",
)


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_observations(directory: Path) -> tuple[list[dict], dict]:
    """Verify the frozen manifest, then strip all original association labels."""
    manifest = json.loads((directory / "manifest.json").read_text())
    hashes = {"manifest.json": digest(directory / "manifest.json")}
    for name in ("context-observations.jsonl", "sources.json"):
        expected = next(x for x in manifest["files"] if x["path"] == name)
        path = directory / name
        actual = digest(path)
        if actual != expected["sha256"] or path.stat().st_size != expected["bytes"]:
            raise ValueError(f"Frozen input does not match manifest: {name}")
        hashes[name] = actual
    source = next(x for x in json.loads((directory / "sources.json").read_text())
                  if x["source_id"] == "S01")
    rows = []
    with (directory / "context-observations.jsonl").open() as stream:
        for line in stream:
            row = json.loads(line)
            if row["source_id"] == "S01":
                rows.append({key: row[key] for key in OBSERVATION_FIELDS})
    rows.sort(key=lambda x: (x["time_s"], x["receiver"], x["channel"], x["observation_id"]))
    if len(rows) != source["observation_count"] or len(rows) != 4797:
        raise ValueError("Expected every one of the 4,797 frozen S01 observations")
    if len({x["observation_id"] for x in rows}) != len(rows):
        raise ValueError("Duplicate observation IDs")
    if {(x["receiver"], x["channel"]) for x in rows} != {
        (rx, ch) for rx in (1, 2) for ch in range(1, 9)
    }:
        raise ValueError("Expected both receivers and all eight channels")
    if not all(math.isfinite(x[k]) for x in rows for k in ("time_s", "measured_cfo_hz")):
        raise ValueError("Nonfinite observation")
    return rows, {
        "source_id": "S01", "recording_id": source["recording_id"],
        "first_sample_estimate_utc": source["first_sample_estimate_utc"],
        "input_sha256": hashes,
        "selection": "All frozen S01 winning observations; no association labels used",
    }


def residual_diagnostics(time_s, residual_hz) -> dict:
    """Descriptive checks, deliberately not an automatic whiteness acceptance test."""
    order = np.argsort(time_s, kind="stable")
    t, r = np.asarray(time_s)[order], np.asarray(residual_hz)[order]
    if len(r) == 0:
        return {"count": 0}
    centered = r - np.mean(r)
    scale = float(np.std(r))
    lag1 = None
    if len(r) > 3 and np.std(r[:-1]) > 0 and np.std(r[1:]) > 0:
        lag1 = float(np.corrcoef(r[:-1], r[1:])[0, 1])
    bins = np.array_split(np.arange(len(r)), min(6, max(1, len(r) // 5)))
    means = [float(np.mean(r[b])) for b in bins]
    spreads = [float(np.std(r[b])) for b in bins]
    return {
        "count": len(r), "mean_hz": float(np.mean(r)),
        "rms_hz": float(np.sqrt(np.mean(r**2))),
        "median_absolute_hz": float(np.median(np.abs(r))),
        "p95_absolute_hz": float(np.quantile(np.abs(r), 0.95)),
        "lag1_correlation_observation_order": lag1,
        "median_adjacent_elapsed_s": float(np.median(np.diff(t))) if len(t) > 1 else None,
        "sign_runs": int(1 + np.count_nonzero(np.signbit(r[1:]) != np.signbit(r[:-1]))),
        "normalized_cusum_max": float(np.max(np.abs(np.cumsum(centered))) /
                                      (max(scale, 1e-12) * np.sqrt(len(r)))),
        "equal_count_bin_mean_hz": means, "equal_count_bin_std_hz": spreads,
        "interpretation": "In-sample selected members; zero global moments are fitted constraints",
    }


def conditional_block_prediction(time_s, lifted_hz, piece) -> dict:
    """Refit coefficients with contiguous blocks excluded, holding membership fixed.

    This isolates coefficient interpolation; it does not validate clustering or
    alias selection, which used the full data. Every selected member is scored.
    """
    order = np.argsort(time_s, kind="stable")
    t, y = np.asarray(time_s)[order], np.asarray(lifted_hz)[order]
    degree = int(piece["degree"])
    if len(t) < max(16, 4 * (degree + 1)):
        return {"count": 0, "status": "insufficient_support"}
    x = (t - piece["reference_time_s"]) / piece["time_scale_s"]
    residual = np.full(len(t), np.nan)
    for block in np.array_split(np.arange(len(t)), 4):
        train = np.ones(len(t), dtype=bool)
        train[block] = False
        coeff = legfit(x[train], y[train], degree)
        residual[block] = y[block] - legval(x[block], coeff)
    return {"count": len(t), "status": "conditional_on_full_data_membership_and_alias_lifts",
            "rms_hz": float(np.sqrt(np.mean(residual**2))),
            "p95_absolute_hz": float(np.quantile(np.abs(residual), 0.95))}


def evaluate_lanes(rows: list[dict], config, fitter=None) -> tuple[dict, list[dict]]:
    if fitter is None:
        from leo.analysis.polynomial_tracklets import fit_lane
        fitter = fit_lane
    lanes, exports = [], []
    start = time.perf_counter()
    for rx in (1, 2):
        for channel in range(1, 9):
            lane_rows = [x for x in rows if x["receiver"] == rx and x["channel"] == channel]
            t = np.array([x["time_s"] for x in lane_rows])
            y = np.array([x["measured_cfo_hz"] for x in lane_rows])
            lane_start = time.perf_counter()
            result = fitter(t, y, config)
            assignment = np.asarray(result["assignment"], dtype=int)
            lifts = np.asarray(result["alias_lifts"], dtype=int)
            if assignment.shape != t.shape or lifts.shape != t.shape:
                raise ValueError("Fitter must return one assignment and alias lift per input")
            residual = np.full(len(t), np.nan)
            piece_ids = np.full(len(t), -1, dtype=int)
            tracks = []
            for track_id, track in enumerate(result["tracks"]):
                track = dict(track)
                pieces = []
                for piece_id, piece in enumerate(track["pieces"]):
                    piece = dict(piece)
                    idx = np.asarray(piece["indices"], dtype=int)
                    if np.any(assignment[idx] != track_id) or np.any(piece_ids[idx] >= 0):
                        raise ValueError("Inconsistent or duplicate piece membership")
                    x = (t[idx] - piece["reference_time_s"]) / piece["time_scale_s"]
                    lifted = y[idx] + lifts[idx] * config.alias_spacing_hz
                    residual[idx] = lifted - legval(x, piece["coefficients_hz"])
                    piece_ids[idx] = piece_id
                    piece["start_s"] = float(np.min(t[idx]))
                    piece["end_s"] = float(np.max(t[idx]))
                    piece["residual_diagnostics"] = residual_diagnostics(t[idx], residual[idx])
                    piece["conditional_block_prediction"] = conditional_block_prediction(
                        t[idx], lifted, piece)
                    piece["observation_ids"] = [lane_rows[i]["observation_id"] for i in idx]
                    pieces.append(piece)
                track["pieces"] = pieces
                diagnostic = track.get("diagnostics", {})
                statuses = [p.get("quality_status", "insufficient_support")
                            for p in diagnostic.get("pieces", [])]
                if "structure_flagged" in statuses:
                    quality = "structure_flagged"
                elif not statuses or "insufficient_support" in statuses:
                    quality = "insufficient_support"
                else:
                    quality = "no_structure_detected"
                track["quality_status"] = quality
                tracks.append(track)
            if np.any((assignment >= 0) != np.isfinite(residual)):
                raise ValueError("Every assigned observation must belong to exactly one piece")
            if np.any(assignment >= len(tracks)) or np.any(assignment < -1):
                raise ValueError("Invalid track assignment")
            assigned = int(np.count_nonzero(assignment >= 0))
            lane = {"receiver": rx, "channel": channel, "observations": len(t),
                    "track_count": len(tracks), "assigned": assigned,
                    "unresolved": len(t) - assigned,
                    "assigned_fraction": assigned / len(t) if len(t) else 0,
                    "runtime_s": time.perf_counter() - lane_start, "tracks": tracks,
                    "fitter_diagnostics": result.get("diagnostics", {}),
                    "degree_histogram": dict(Counter(str(p["degree"]) for track in tracks
                                                       for p in track["pieces"]))}
            lanes.append(lane)
            for i, row in enumerate(lane_rows):
                exports.append({**row, "track_id": int(assignment[i]),
                                "track_key": f"RX{rx}-CH{channel}-T{assignment[i]:03d}"
                                if assignment[i] >= 0 else "unresolved",
                                "quality_status": tracks[assignment[i]]["quality_status"]
                                if assignment[i] >= 0 else "unresolved",
                                "piece_id": int(piece_ids[i]), "alias_lift": int(lifts[i]),
                                "residual_hz": float(residual[i]) if assignment[i] >= 0 else None})
            print(f"RX{rx} CH{channel}: {len(tracks)} tracks; {assigned}/{len(t)} assigned; "
                  f"{lane['runtime_s']:.2f}s", flush=True)
    assigned = sum(x["assigned"] for x in lanes)
    degree_hist = Counter()
    for lane in lanes:
        degree_hist.update(lane["degree_histogram"])
    summary = {
        "observations": len(rows), "track_count": sum(x["track_count"] for x in lanes),
        "piece_count": sum(sum(len(t["pieces"]) for t in x["tracks"]) for x in lanes),
        "assigned": assigned, "unresolved": len(rows) - assigned,
        "assigned_fraction": assigned / len(rows), "degree_histogram": dict(degree_hist),
        "runtime_s": time.perf_counter() - start, "config": asdict(config), "lanes": lanes,
        "residual_diagnostics": residual_diagnostics(
            [x["time_s"] for x in exports if x["track_id"] >= 0],
            [x["residual_hz"] for x in exports if x["track_id"] >= 0]),
    }
    regions = []
    for name, rx, channel, lower, upper, expected in (
        ("001", 1, 4, 40, 100, 86), ("002", 1, 2, 50, 75, 35),
        ("003", 1, 2, 170, 190, 27),
    ):
        subset = [r for r in exports if r["receiver"] == rx and r["channel"] == channel
                  and lower <= r["time_s"] <= upper]
        regions.append({"region_id": name, "receiver": rx, "channel": channel,
                        "time_range_s": [lower, upper], "observations": len(subset),
                        "expected_observations": expected,
                        "assigned": sum(r["track_id"] >= 0 for r in subset),
                        "distinct_assigned_tracks": len({r["track_id"] for r in subset
                                                         if r["track_id"] >= 0}),
                        "interpretation": "Descriptive post-fit coverage; not identity accuracy"})
    summary["audit_regions"] = regions
    # Pooling neighboring residuals across receivers/channels creates an arbitrary
    # temporal sequence. Only per-piece diagnostics assess temporal structure.
    pooled = summary["residual_diagnostics"]
    summary["residual_diagnostics"] = {
        k: pooled[k] for k in ("count", "mean_hz", "rms_hz", "median_absolute_hz",
                              "p95_absolute_hz") if k in pooled
    }
    summary["residual_diagnostics"]["interpretation"] = (
        "Pooled descriptive residual magnitudes; temporal structure is assessed per piece."
    )
    summary["residual_quality"] = {
        status: {"tracks": sum(t["quality_status"] == status for lane in lanes
                              for t in lane["tracks"]),
                 "associated_points": sum(len(t["indices"]) for lane in lanes
                                          for t in lane["tracks"]
                                          if t["quality_status"] == status)}
        for status in ("no_structure_detected", "structure_flagged", "insufficient_support")
    }
    summary["residual_quality_interpretation"] = (
        "No structure detected is a conditional diagnostic outcome, not proof of white noise "
        "or independent validation; totals also include flagged and short tracks."
    )
    return summary, exports


def json_default(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def save_results(directory: Path, summary: dict, exports: list[dict]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "results.json").write_text(
        json.dumps(summary, indent=2, default=json_default, allow_nan=False) + "\n")
    with (directory / "assignments.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(exports[0]))
        writer.writeheader()
        writer.writerows(exports)
    with (directory / "lanes.csv").open("w", newline="") as stream:
        fields = ["receiver", "channel", "observations", "track_count", "assigned",
                  "unresolved", "assigned_fraction", "runtime_s"]
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(summary["lanes"])


def plot_results(directory: Path, summary: dict, rows: list[dict]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False})
    palette = plt.get_cmap("turbo")
    for residuals in (False, True):
        fig, axes = plt.subplots(8, 2, figsize=(16, 23), sharex=True)
        for lane in summary["lanes"]:
            rx, ch = lane["receiver"], lane["channel"]
            ax = axes[ch - 1, rx - 1]
            group = [r for r in rows if r["receiver"] == rx and r["channel"] == ch]
            if not residuals:
                noise = [r for r in group if r["track_id"] < 0]
                ax.scatter([r["time_s"] for r in noise],
                           [r["measured_cfo_hz"] / 1000 for r in noise],
                           s=10, c="#aaaaaa", alpha=0.65, linewidths=0, rasterized=True)
            for tid in range(lane["track_count"]):
                selected = [r for r in group if r["track_id"] == tid]
                color = palette((tid * 0.61803398875) % 1)
                values = [r["residual_hz"] if residuals else r["measured_cfo_hz"] / 1000
                          for r in selected]
                ax.scatter([r["time_s"] for r in selected], values, s=11, color=color,
                           alpha=0.85, linewidths=0, rasterized=True)
                if not residuals:
                    for piece_id, piece in enumerate(lane["tracks"][tid]["pieces"]):
                        members = sorted((r for r in selected if r["piece_id"] == piece_id),
                                         key=lambda r: r["time_s"])
                        for left, right in zip(members[:-1], members[1:], strict=True):
                            # Draw only observed alias-continuous intervals; gaps and
                            # raw-frequency branch changes remain visually explicit.
                            if (left["alias_lift"] != right["alias_lift"] or
                                    right["time_s"] - left["time_s"] >
                                    summary["config"]["max_gap_s"]):
                                continue
                            dense = np.linspace(left["time_s"], right["time_s"], 8)
                            x = ((dense - piece["reference_time_s"]) /
                                 piece["time_scale_s"])
                            predicted = (legval(x, piece["coefficients_hz"]) -
                                         left["alias_lift"] *
                                         summary["config"]["alias_spacing_hz"])
                            ax.plot(dense, predicted / 1000, color=color,
                                    linewidth=0.75, alpha=0.65)
                if selected and not residuals:
                    mid = selected[len(selected) // 2]
                    ax.annotate(str(tid), (mid["time_s"], mid["measured_cfo_hz"] / 1000),
                                xytext=(3, 4), textcoords="offset points", fontsize=7,
                                color=color)
            if residuals:
                ax.axhline(0, color="#444444", linewidth=0.6)
                limit = summary["config"]["noise_sigma_hz"] * summary["config"]["association_sigma"]
                ax.axhline(limit, color="#aaaaaa", linewidth=0.6, linestyle="--")
                ax.axhline(-limit, color="#aaaaaa", linewidth=0.6, linestyle="--")
            ax.set_title(f"RX{rx} · CH{ch} · {lane['track_count']} tracks · "
                         f"{lane['assigned']}/{lane['observations']} assigned", loc="left")
            ax.set_xlim(0, 300)
            ax.grid(alpha=0.18)
        title = "Selected-member residuals" if residuals else "Alias-aware polynomial tracklets"
        fig.suptitle(f"DSX01 S01 · {title}\n{summary['track_count']} lane-level tracks; "
                     f"{summary['assigned']:,}/{summary['observations']:,} points assigned "
                     f"({summary['assigned_fraction']:.1%})", fontsize=17, y=0.995)
        fig.supxlabel("Time since first-sample estimate (s)")
        fig.supylabel("Fitted residual (Hz)" if residuals else "Measured GLRT CFO (kHz)")
        fig.text(0.5, 0.027,
                 "Residuals are conditional on selected memberships; not independent validation."
                 if residuals else "Gray: unresolved. Colors identify lane-level tracks; "
                 "they do not identify satellites.", ha="center", fontsize=10)
        fig.tight_layout(rect=(0.025, 0.04, 1, 0.96))
        stem = "residuals" if residuals else "clusters-by-receiver"
        for extension in ("png", "pdf"):
            fig.savefig(directory / f"{stem}.{extension}", dpi=150)
        plt.close(fig)
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    tracks = [t for lane in summary["lanes"] for t in lane["tracks"]]
    axes[0].hist([len(t["indices"]) for t in tracks], bins=20, color="#36739b")
    axes[0].set(xlabel="Points per track", ylabel="Tracks")
    axes[1].hist([max(p["end_s"] for p in t["pieces"]) -
                  min(p["start_s"] for p in t["pieces"]) for t in tracks],
                 bins=20, color="#36739b")
    axes[1].set(xlabel="Track span (s)", ylabel="Tracks")
    axes[2].bar(list(summary["degree_histogram"]), list(summary["degree_histogram"].values()),
                color="#36739b")
    axes[2].set(xlabel="Polynomial degree", ylabel="Pieces")
    fig.suptitle("DSX01 S01 · Tracklet complexity and support")
    fig.tight_layout()
    for extension in ("png", "pdf"):
        fig.savefig(directory / f"track-distributions.{extension}", dpi=150)
    plt.close(fig)


def main() -> None:
    from leo.analysis.polynomial_tracklets import TrackConfig

    fitter_hash = digest(REPO / "src/leo/analysis/polynomial_tracklets.py")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", "--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--noise-sigma-hz", type=float)
    parser.add_argument("--max-degree", type=int)
    parser.add_argument("--max-slope-hz-s", type=float)
    parser.add_argument("--skip-baseline", action="store_true")
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    rows, provenance = load_observations(args.input)
    config = TrackConfig()
    if args.noise_sigma_hz is not None:
        config = replace(config, noise_sigma_hz=args.noise_sigma_hz)
    if args.max_degree is not None:
        config = replace(config, max_degree=args.max_degree)
    if args.max_slope_hz_s is not None:
        config = replace(config, max_slope_hz_s=args.max_slope_hz_s)
    comparison = {}
    for name, cfg in [("polynomial", config)] + (
        [] if args.skip_baseline else [("linear_baseline", replace(config, max_degree=1))]
    ):
        print(f"Evaluating {name}", flush=True)
        summary, exports = evaluate_lanes(rows, cfg)
        if digest(REPO / "src/leo/analysis/polynomial_tracklets.py") != fitter_hash:
            raise RuntimeError("Fitter source changed during evaluation; rerun with frozen source")
        summary["provenance"] = {
            **provenance, "evaluator_sha256": digest(Path(__file__)),
            "fitter_sha256": fitter_hash,
        }
        summary["limitations"] = [
            "Tracks are separate receiver/channel curve clusters, not satellite counts.",
            "Assignments and residual diagnostics use the same full dataset.",
            "Block prediction holds full-data membership and alias lifts fixed; "
            "it tests coefficients only.",
            "Absolute alias branch is unidentifiable without external information.",
            "Unresolved observations remain in the denominator and the assignment export.",
        ]
        folder = args.output / name
        save_results(folder, summary, exports)
        if not args.no_plots:
            plot_results(folder, summary, exports)
        comparison[name] = {k: v for k, v in summary.items() if k not in ("lanes", "provenance")}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "comparison.json").write_text(
        json.dumps(comparison, indent=2, default=json_default, allow_nan=False) + "\n")
    print(json.dumps(comparison, indent=2, default=json_default), flush=True)


if __name__ == "__main__":
    main()
