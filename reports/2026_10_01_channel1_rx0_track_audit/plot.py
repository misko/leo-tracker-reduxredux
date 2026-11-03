import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

data = json.loads(Path(__file__).with_name("evidence.json").read_text())
rows = data["candidates"]
times = np.array([(row["support_center_utc_ns"] - data["origin_utc_ns"]) / 1e9 for row in rows])
frequencies = np.array([row["measured_cfo_hz"] for row in rows])
scale = 11_200_000_000 / rows[0]["actual_rf_hz"]
alias = scale / 4.4e-6
residual = (frequencies * scale + 3700 * (times - 200)) % alias
figure, axes = plt.subplots(2, 1, figsize=(14, 9), sharex=True, layout="constrained")
axes[0].scatter(times, frequencies / 1000, s=9, c="0.65")
axes[1].scatter(times, residual / 1000, s=12, c="0.7", label="Passing GLRT candidates")
for index, track in enumerate(data["replays"]["baseline"]):
    selected = np.array([row["candidate_id"] in track["point_ids"] for row in rows])
    label = f"Track {index + 1}: {track['start_s']:.1f}–{track['end_s']:.1f}s"
    axes[0].scatter(times[selected], frequencies[selected] / 1000, s=14, label=label)
    axes[1].scatter(times[selected], residual[selected] / 1000, s=18, label=label)
axes[0].set_ylabel("Measured CFO (kHz)")
axes[1].set_ylabel("Alias-wrapped CFO after removing −3700 Hz/s trend (kHz)")
axes[1].set_xlabel("Seconds from capture start")
axes[0].set_title("scan-fw-4971402f107cf8e1 · channel 1 RX0 · GLRT detections and published tracks")
for axis in axes:
    axis.set_xlim(160, 285)
    axis.grid(alpha=0.2)
axes[1].legend(loc="upper left", fontsize=8)
figure.savefig(Path(__file__).with_name("track-audit.png"), dpi=140)

comparison = json.loads(Path(__file__).with_name("curvature.json").read_text())
figure, axis = plt.subplots(figsize=(12, 6), layout="constrained")
axis.scatter(times, frequencies / 1000, s=12, c="0.75", label="Passing GLRT detections")
for index, colour in ((2, "#198754"), (0, "#2463b3")):
    track = data["replays"]["baseline"][index]
    selected = np.array([row["candidate_id"] in track["point_ids"] for row in rows])
    axis.scatter(
        times[selected],
        frequencies[selected] / 1000,
        s=24,
        c=colour,
        label=f"Published: {track['start_s']:.1f}–{track['end_s']:.1f}s",
    )
bridge = data["replays"]["capacity16"][11]
selected = np.array([row["candidate_id"] in bridge["point_ids"] for row in rows])
axis.scatter(
    times[selected],
    frequencies[selected] / 1000,
    s=45,
    facecolors="none",
    edgecolors="#d35400",
    linewidths=1.5,
    label="Bridge discarded by eight-track limit",
)
grid = np.linspace(194.3, 275.1, 300)
for model, style, colour in (
    (comparison["models"][0], "--", "#aa3333"),
    (comparison["models"][2], "-", "#222222"),
):
    predicted = np.polynomial.polynomial.polyval(grid - 230, model["coefficients_about_230s"])
    name = "Straight line" if model["degree"] == 1 else "Diagnostic curved fit"
    axis.plot(
        grid,
        predicted / scale / 1000,
        style,
        c=colour,
        linewidth=1.3,
        label=f"{name}: held-out RMS {model['evaluation_rms_hz'] / 1000:.2f} kHz (normalized)",
    )
axis.axvspan(219.4, 228.54, alpha=0.08, color="#d35400")
axis.set(
    xlim=(185, 280),
    ylim=(-340, -45),
    xlabel="Seconds from capture start",
    ylabel="Measured CFO (kHz)",
    title="Channel 1 RX0: continuous GLRT support, fragmented tracks",
)
axis.grid(alpha=0.2)
axis.legend(fontsize=9)
figure.savefig(Path(__file__).with_name("root-cause.png"), dpi=150)
