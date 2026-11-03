"""Compare contemporaneous receiver residuals without refitting orbital parameters."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
SESSION = "scan-fw-ffa1cc19d8d7c09f"


def fit_line(times, values, channels=None, robust=False):
    times = np.asarray(times, dtype=float)
    values = np.asarray(values, dtype=float)
    channels = np.zeros(len(times), dtype=int) if channels is None else np.asarray(channels)
    if times.shape != values.shape or channels.shape != times.shape or len(times) < 3:
        raise ValueError("at least three aligned observations required")
    levels = np.unique(channels)
    design = np.column_stack([times - 265] + [(channels == level) for level in levels])
    if np.linalg.matrix_rank(design) != design.shape[1]:
        raise ValueError("rank deficient line design")
    weights = np.ones(len(times))
    for _iteration in range(30 if robust else 1):
        estimate = np.linalg.lstsq(design * np.sqrt(weights[:, None]),
                                   values * np.sqrt(weights), rcond=None)[0]
        residual = values - design @ estimate
        scale = max(1., 1.4826 * np.median(np.abs(residual - np.median(residual))))
        weights = np.minimum(1., 1.345 * scale / np.maximum(np.abs(residual), 1e-12))
    return {"count": len(times), "start_s": float(times.min()), "stop_s": float(times.max()),
            "slope_hz_s": float(estimate[0]),
            "channel_intercepts_at_265s_hz": dict(zip(map(str, levels), estimate[1:].tolist(),
                                                      strict=True)),
            "rms_after_line_hz": float(np.sqrt(np.mean(residual ** 2)))}


def run():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    source = ROOT / "tle-doppler-overlay" / f"{SESSION}-plot-data.npz"
    data = np.load(source)
    times, receiver, channel = (data[key] for key in ("times_s", "receiver", "channel"))
    residual = data["residual_hz"] * data["rf_hz"][:, None] / 11.085e9
    output = ROOT / "satellite65745-peer-audit"
    output.mkdir(exist_ok=False)
    records = []
    for satellite_column, number in enumerate(data["catalog_numbers"]):
        for rx in (0, 1):
            for stop in (270., 290.):
                selected = (data["accepted"][:, satellite_column] & (receiver == rx)
                            & (times >= 240) & (times <= stop))
                if selected.sum() < 10 or np.ptp(times[selected]) < 10:
                    continue
                entry = {"satellite": int(number), "receiver": rx, "window_s": [240, stop]}
                for adjusted in (False, True):
                    for robust in (False, True):
                        label = f"{'channel_adjusted' if adjusted else 'pooled'}_"
                        label += "huber" if robust else "ols"
                        entry[label] = fit_line(
                            times[selected], residual[selected, satellite_column],
                            channel[selected] if adjusted else None, robust)
                entry["channels"] = {}
                for band in np.unique(channel[selected]):
                    mask = selected & (channel == band)
                    if mask.sum() >= 3 and np.ptp(times[mask]) > 1:
                        entry["channels"][str(band)] = fit_line(
                            times[mask], residual[mask, satellite_column], robust=True)
                records.append(entry)
    target = np.flatnonzero(data["catalog_numbers"] == 65745)[0]
    peer = np.flatnonzero(data["catalog_numbers"] == 62847)[0]
    overlap = []
    for band in np.unique(channel):
        masks = [data["accepted"][:, column] & (receiver == 0) & (channel == band)
                 & (times >= 240) & (times <= 290) for column in (target, peer)]
        if not all(mask.any() for mask in masks):
            continue
        start = max(times[mask].min() for mask in masks)
        stop = min(times[mask].max() for mask in masks)
        overlap.append({"channel": int(band), "overlap_span_s": max(0., float(stop - start)),
                        "start_s": float(start), "stop_s": float(stop),
                        "shared_groups": len(set(data["group"][masks[0]])
                                             & set(data["group"][masks[1]]))})
    figure, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True, sharey=True)
    for axis, column in zip(axes, (target, peer), strict=True):
        mask = data["accepted"][:, column] & (receiver == 0) & (times >= 240) & (times <= 290)
        for band in np.unique(channel[mask]):
            chosen = mask & (channel == band)
            axis.scatter(times[chosen], residual[chosen, column], s=15, label=f"channel {band}")
        fitted = fit_line(times[mask], residual[mask, column], robust=True)
        grid = np.array([times[mask].min(), times[mask].max()])
        axis.plot(grid, fitted["slope_hz_s"] * (grid - 265)
                  + fitted["channel_intercepts_at_265s_hz"]["0"], color="black", linestyle="--",
                  label=f"pooled Huber slope {fitted['slope_hz_s']:+.2f} Hz/s")
        axis.set_title(f"NORAD {data['catalog_numbers'][column]} · RX0 · {mask.sum()} points")
        axis.axhline(0, color="black", linewidth=.5)
        axis.set_ylabel("Observed − modeled (Hz)")
        axis.legend(fontsize=8, ncol=3)
        axis.grid(alpha=.2)
    axes[-1].set_xlabel("Receive time (s)")
    figure.suptitle("Same receiver, overlapping time: different satellite residual trends")
    figure.text(.5, .015, "Original posterior ≥0.8; actual RF Hz, no carrier normalization. "
                "Different channel coverage limits causal attribution.\n"
                "Frozen known-position RX/timing/RF fit. Dashed lines are diagnostics, not orbits.",
                ha="center", fontsize=9)
    figure.tight_layout(rect=(0, .06, 1, .96))
    for extension in ("png", "svg"):
        figure.savefig(output / f"peer-comparison.{extension}", dpi=160)
    result = {"session": SESSION, "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "rx0_existing_slope_hz_s": float(data["parameters"][3]),
              "fits": records, "same_channel_overlap": overlap,
              "scope": "Descriptive frozen-association regressions; no independent validation or "
                       "geographic fit. Huber handles isolated outliers, not correlated bias. "
                       "Channel-adjusted regressions allow separate constant channel intercepts. "
                       "Opposite contemporaneous slopes disfavor only a simple common additive RX "
                       "line; channel-dependent receiver effects and orbit/signal mismatch remain."}
    (output / "summary.json").write_text(json.dumps(result, indent=2, allow_nan=False))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    run()
