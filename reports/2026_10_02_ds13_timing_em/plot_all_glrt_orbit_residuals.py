"""Show every retained GLRT peak against each selected orbit, without association cuts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
SESSION = "scan-fw-ffa1cc19d8d7c09f"


def observation_mask(times, receiver, selected_receiver):
    times = np.asarray(times)
    return (times >= 0) & (times <= 300) & (np.asarray(receiver) == selected_receiver)


def residual_limits(axis):
    axis.set_xlim(0, 300)
    axis.set_ylim(-300, 300)
    axis.set_yticks([-300, -150, 0, 150, 300])
    axis.tick_params(labelbottom=True)
    axis.axhline(0, color="black", linewidth=.7)
    axis.grid(alpha=.2)
    axis.set_xlabel("Receive time (s)")
    axis.set_ylabel("Observed − modeled (Hz)")


def main():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    source = ROOT / "tle-doppler-overlay" / f"{SESSION}-plot-data.npz"
    receipt_path = source.parent / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if receipt["artifact_sha256"][str(source)] != source_hash:
        raise ValueError("sealed plotting arrays changed")
    arrays = np.load(source)
    output = ROOT / "all-glrt-orbit-residuals"
    output.mkdir(exist_ok=False)
    numbers = arrays["catalog_numbers"]
    overview = plt.figure(figsize=(15, 24))
    layout = overview.add_gridspec(6, 2, left=.07, right=.98, top=.93, bottom=.045,
                                   hspace=.48, wspace=.23)
    residual_figure, residual_axes = plt.subplots(4, 3, figsize=(16, 12), sharex=True,
                                                 sharey=True)
    masks = [observation_mask(arrays["times_s"], arrays["receiver"], rx) for rx in (0, 1)]
    counts = []
    for column, number in enumerate(numbers):
        inner = layout[column // 2, column % 2].subgridspec(
            2, 1, height_ratios=(2, 1), hspace=.12)
        orbit_axis = overview.add_subplot(inner[0])
        error_axis = overview.add_subplot(inner[1], sharex=orbit_axis)
        standalone = residual_axes.flat[column]
        for rx, color in ((0, "#0072B2"), (1, "#D55E00")):
            selected = masks[rx]
            times = arrays["times_s"][selected]
            values = arrays["residual_hz"][selected, column]
            options = {"s": 7, "color": color, "alpha": .5, "linewidths": 0,
                       "rasterized": True}
            orbit_axis.scatter(times, arrays["doppler_hz"][selected, column] / 1000,
                               **{**options, "alpha": .10, "s": 3})
            for axis in (error_axis, standalone):
                axis.scatter(times, values, **options)
        dense_times = arrays["dense_times_s"]
        orbit_axis.plot(dense_times, arrays["unshifted_tle_doppler_hz"][:, column] / 1000,
                        color=".55", linestyle=":", linewidth=.8)
        orbit_axis.plot(dense_times, arrays["dense_doppler_hz"][:, column] / 1000,
                        color="black", linewidth=1)
        in_window = masks[0] | masks[1]
        inside = in_window & (np.abs(arrays["residual_hz"][:, column]) <= 300)
        title = f"NORAD {number} · {int(inside.sum())} peaks within ±300 Hz"
        counts.append({"satellite": int(number), "within_300hz": int(inside.sum())})
        orbit_axis.set_title(title, fontsize=10)
        orbit_axis.set_ylabel("Doppler (kHz)")
        orbit_axis.tick_params(labelbottom=False)
        orbit_axis.grid(alpha=.2)
        standalone.set_title(title, fontsize=10)
        for axis in (error_axis, standalone):
            residual_limits(axis)
    residual_axes.flat[-1].set_visible(False)
    handles = [Line2D([], [], color="black", label="Timing-adjusted TLE Doppler"),
               Line2D([], [], color=".55", linestyle=":", label="TLE without timing shift")]
    handles += [Line2D([], [], color=color, marker="o", linestyle="", label=f"RX{rx}: all GLRT")
                for rx, color in ((0, "#0072B2"), (1, "#D55E00"))]
    footer = ("All 6,784 retained GLRT family representatives; no satellite-assignment, posterior, "
              "or visibility filter.\n"
              "Same fixed reference position and fitted RX/RF/timing corrections; each point uses "
              "the nearest alias to the panel's orbit, normalized to 11.085 GHz.\n"
              "Residual axes clip outside ±300 Hz; points are not moved onto the boundaries. "
              "Proximity alone is not an association. No refitting.")
    artifacts = []
    for figure, name in ((overview, "scan-B-all-glrt-overview"),
                         (residual_figure, "scan-B-all-glrt-residuals")):
        figure.suptitle("DS13 scan B · all GLRT versus each selected satellite · 0–300 s",
                       y=.99, fontsize=14)
        legend_handles = handles[-2:] if figure is residual_figure else handles
        figure.legend(handles=legend_handles, loc="upper center", bbox_to_anchor=(.5, .972),
                      ncol=4, fontsize=9)
        figure.text(.5, .012, footer, ha="center", fontsize=8)
        if figure is residual_figure:
            figure.tight_layout(rect=(0, .075, 1, .925))
        for extension in ("png", "svg"):
            path = output / f"{name}.{extension}"
            figure.savefig(path, dpi=160)
            artifacts.append(path)
        plt.close(figure)
    metadata = {"source": str(source), "source_sha256": source_hash,
                "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "session": SESSION, "input_rows": len(arrays["times_s"]),
                "plotted_rows_per_satellite": sum(int(mask.sum()) for mask in masks),
                "counts": counts, "semantics": footer,
                "artifacts": {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in artifacts}}
    (output / "receipt.json").write_text(json.dumps(metadata, indent=2))
    print(json.dumps({"output": str(output), "rows": metadata["plotted_rows_per_satellite"]}))


if __name__ == "__main__":
    main()
