"""Saved-result slope and estimator diagnostics for fixed satellite 65745 matches."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from south_glrt_surface_probe import ROOT, digest

SOURCE = ROOT / "south-orbit-glrt-refinement"
OUTPUT = ROOT / "satellite65745-glrt-audit"
SESSION = "scan-fw-ffa1cc19d8d7c09f"
BIN_HZ = 1 / (512 * 4.4e-6)


def slope(times, values):
    times, values = np.asarray(times, float), np.asarray(values, float)
    if len(times) < 3 or np.ptp(times) == 0:
        return {"count": len(times), "available": False}
    centered = times - np.mean(times)
    rate = float(centered @ (values - np.mean(values)) / (centered @ centered))
    residual = values - np.mean(values) - rate * centered
    before, after = np.triu_indices(len(times), 1)
    distinct = times[after] != times[before]
    pair_rates = ((values[after[distinct]] - values[before[distinct]])
                  / (times[after[distinct]] - times[before[distinct]]))
    return {"count": len(times), "available": True, "time_min_s": float(min(times)),
            "time_max_s": float(max(times)), "ols_hz_per_s": rate,
            "theil_sen_hz_per_s": float(np.median(pair_rates)),
            "ols_fitted_change_hz": rate * float(np.ptp(times)),
            "mean_hz": float(np.mean(values)), "rms_hz": float(np.sqrt(np.mean(values**2))),
            "detrended_rms_hz": float(np.sqrt(np.mean(residual**2)))}


def correlation(left, right):
    left, right = np.asarray(left, float), np.asarray(right, float)
    left, right = left - left.mean(), right - right.mean()
    norm = np.linalg.norm(left) * np.linalg.norm(right)
    return float(left @ right / norm) if norm > 1e-10 else None


def residualize(values, design):
    values = np.asarray(values, float)
    return values - design @ np.linalg.lstsq(design, values, rcond=None)[0]


def analyze(rows):
    times = np.array([float(row["time_s"]) for row in rows])
    raw = np.array([float(row["measured_hz"]) - float(row["truth_frequency_hz"])
                    for row in rows])
    refined = np.array([float(row["control_residual_to_truth_hz"]) for row in rows])
    offset = refined - raw
    labels = np.array([f"RX{row['receiver']}/CH{row['channel']}" for row in rows])
    levels = sorted(set(labels))
    fixed_effects = np.column_stack([labels == label for label in levels]).astype(float)
    design = np.column_stack([fixed_effects, times - np.mean(times)])
    groups = {}
    for label in ["all", *levels, *sorted({f"RX{row['receiver']}" for row in rows})]:
        mask = (np.ones(len(rows), bool) if label == "all" else labels == label
                if "/" in label else np.array([f"RX{row['receiver']}" == label for row in rows]))
        groups[label] = {"raw": slope(times[mask], raw[mask]),
                         "refined": slope(times[mask], refined[mask]),
                         "refinement_offset": slope(times[mask], offset[mask])}
    features = {name: np.array([float(row[key]) for row in rows]) for name, key in (
        ("time", "time_s"), ("margin", "margin"), ("exact_score", "stored_exact_score"),
        ("control_score", "stored_control_score"),
        ("truth_posterior", "truth_match_probability"),
        ("integer_epoch_samples", "integer_epoch_sample"),
        ("fractional_epoch_samples", "fractional_epoch_offset_samples"),
        ("native_residual_hz", "native_residual_hz"),
    )}
    phase = np.array([(float(row["integer_epoch_sample"])
                      + float(row["fractional_epoch_offset_samples"]))
                     / (float(row["sample_rate_hz"]) / 750.) for row in rows])
    features.update(epoch_frame_phase_sin=np.sin(2 * np.pi * phase),
                    epoch_frame_phase_cos=np.cos(2 * np.pi * phase))
    correlations = {}
    for target_name, values in (("raw", raw), ("refined", refined), ("offset", offset)):
        correlations[target_name] = {
            name: {"pearson": correlation(values, feature),
                   "after_time_and_rx_channel": correlation(residualize(values, design),
                                                              residualize(feature, design))}
            for name, feature in features.items()
        }
    native = features["native_residual_hz"]
    return {
        "count": len(rows), "groups": groups,
        "rx_channel_fixed_effect_slope_hz_per_s": {
            name: float(np.linalg.lstsq(design, values, rcond=None)[0][-1])
            for name, values in (("raw", raw), ("refined", refined), ("offset", offset))},
        "correlations": correlations,
        "independent_peak_boundary_hits": sum(
            row["control_boundary_hit"] == "True" for row in rows),
        "refinement_offset_quantiles_hz": np.quantile(offset, [0, .1, .5, .9, 1]).tolist(),
        "offset_exceeding_half_native_bin": int(np.sum(np.abs(offset) > BIN_HZ / 2)),
        "native_residual_values_hz": {str(value): int(np.sum(native == value))
                                      for value in np.unique(native)},
        "native_bin_spacing_hz": BIN_HZ,
        "raw_refined_residual_correlation": correlation(raw, refined),
        "absolute_acquired_cfo_on_100hz_grid_count": sum(
            abs(float(row["acquired_cfo_hz"]) / 100 - round(float(row["acquired_cfo_hz"]) / 100))
            < 1e-8 for row in rows),
    }


def plot(rows, summaries):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(2, 2, figsize=(13, 8))
    levels = sorted({(row["receiver"], row["channel"]) for row in rows})
    colors = {key: plt.get_cmap("tab10")(index) for index, key in enumerate(levels)}
    for axis, scope in zip(axes[0], ("full_track", "240_290s"), strict=True):
        selected = rows if scope == "full_track" else [row for row in rows
                                                       if 240 <= float(row["time_s"]) <= 290]
        for key in levels:
            subset = [row for row in selected if (row["receiver"], row["channel"]) == key]
            times = [float(row["time_s"]) for row in subset]
            raw = [float(row["truth_residual_hz"]) for row in subset]
            fine = [float(row["control_residual_to_truth_hz"]) for row in subset]
            axis.scatter(times, raw, marker="x", s=25, color=colors[key], alpha=.65)
            axis.scatter(times, fine, marker="o", s=15, facecolors="none", edgecolors=colors[key],
                         label=f"RX{key[0]} CH{key[1]}")
        stats = summaries[scope]["groups"]["all"]
        axis.set_title(f"{scope}: raw/fine OLS "
                       f"{stats['raw']['ols_hz_per_s']:.2f}/"
                       f"{stats['refined']['ols_hz_per_s']:.2f} Hz/s")
        axis.set_xlabel("Receive time (s)")
        axis.set_ylabel("Residual to compensated truth curve (Hz)")
        axis.axhline(0, color="black", linewidth=.5)
        axis.legend(fontsize=7, ncol=2)
    for key in levels:
        subset = [row for row in rows if (row["receiver"], row["channel"]) == key]
        offsets = [float(row["control_refined_frequency_hz"]) - float(row["measured_hz"])
                   for row in subset]
        axes[1, 0].scatter([float(row["time_s"]) for row in subset], offsets,
                           s=16, color=colors[key])
        axes[1, 1].scatter([float(row["margin"]) for row in subset], offsets,
                           s=16, color=colors[key])
    for axis in axes[1]:
        axis.axhline(0, color="black", linewidth=.5)
        axis.axhline(BIN_HZ / 2, linestyle=":", color="grey")
        axis.axhline(-BIN_HZ / 2, linestyle=":", color="grey")
        axis.set_ylabel("Independent fine CFO minus stored CFO (Hz)")
    axes[1, 0].set_xlabel("Receive time (s)")
    axes[1, 1].set_xlabel("Stored fractional GLRT margin (strength proxy)")
    figure.suptitle("65745 estimator audit — crosses: stored CFO; circles: independent local peak")
    figure.text(.5, .02, "Fixed original identity/epoch and original-posterior-selected cohort. "
                "Frozen compensated truth curve; descriptive slopes/correlations, no causal test.",
                ha="center", fontsize=9)
    figure.tight_layout(rect=(0, .055, 1, .95))
    for suffix in ("png", "svg"):
        figure.savefig(OUTPUT / f"residual-trend.{suffix}", dpi=160)
    plt.close(figure)


def run():
    paths = [Path(__file__), ROOT / "south_glrt_surface_probe.py", SOURCE / "summary.json",
             SOURCE / "all-stable-points.csv"]
    hashes = {str(path.resolve()): digest(path) for path in paths}
    source = json.loads((SOURCE / "summary.json").read_text())
    if source["artifacts"]["all-stable-points.csv"] != digest(SOURCE / "all-stable-points.csv"):
        raise ValueError("sealed refinement CSV digest mismatch")
    with (SOURCE / "all-stable-points.csv").open() as stream:
        selected = [row for row in csv.DictReader(stream) if row["session"] == SESSION
                    and row["truth_satellite"] == "65745"]
    rows = sorted([row for row in selected if row["status"] == "available"],
                  key=lambda row: float(row["time_s"]))
    scopes = {"full_track": rows, "240_290s": [row for row in rows
                                              if 240 <= float(row["time_s"]) <= 290]}
    summaries = {name: analyze(values) for name, values in scopes.items()}
    OUTPUT.mkdir(exist_ok=False)
    with (OUTPUT / "points.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    plot(rows, summaries)
    if any(digest(path) != value for path, value in hashes.items()):
        raise ValueError("source changed during audit")
    receipt = {"schema": "ds13-satellite65745-glrt-audit/v1", "source_hashes": hashes,
               "session": SESSION, "satellite": 65745, "selected_rows": len(selected),
               "unavailable_rows": len(selected) - len(rows), "scopes": summaries,
               "scope": "No IQ rerun or fit. Full track means full retained stable-confident "
                        "cohort for this fixed identity, not all possible detections. Raw/fine "
                        "RMS and correlations are conditioned on selection using original "
                        "posteriors. Residuals subtract the same frozen compensated truth curve. "
                        "OLS and pairwise Theil-Sen are descriptive; no independent-error "
                        "significance assumed. Partial Pearson removes time and RX/channel "
                        "intercepts, not arbitrary nonlinear confounding. GLRT margin/score "
                        "are strength proxies, not calibrated SNR. Native residual grid is "
                        "relative to each acquired CFO, not an absolute frequency quantizer.",
               "artifacts": {name: digest(OUTPUT / name) for name in
                             ("points.csv", "residual-trend.png", "residual-trend.svg")}}
    with (OUTPUT / "summary.json").open("x") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
    print(json.dumps({name: value["groups"] for name, value in summaries.items()}), flush=True)


if __name__ == "__main__":
    run()
