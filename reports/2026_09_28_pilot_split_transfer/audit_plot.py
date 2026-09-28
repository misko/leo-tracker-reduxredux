"""Independent held-coherence least-squares check and report figures."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
checks = 0
for dataset in ("DS7", "DS8", "DS9"):
    result = json.loads((HERE / dataset / "result.json").read_text())
    archive = np.load(HERE / dataset / "matrices.npz", allow_pickle=False)
    times = archive["times_s"][1::2]
    for window in result["windows"]:
        for frame in window["frames"]:
            held = archive[frame["matrix_key"]][1::2]
            rng = np.random.default_rng(frame["seed"])
            scrambled = held * (1j ** rng.integers(0, 4, len(held)))[:, None]
            candidates = [
                (0.0, frame["baseline_held_coherence"], frame["baseline_scrambled_coherence"])
            ]
            candidates += [
                (m["fit"]["frequency_hz"], m["held_coherence"], m["scrambled_coherence"])
                for m in frame["methods"]
            ]
            for frequency, real_score, scrambled_score in candidates:
                design = np.exp(2j * np.pi * frequency * times)[:, None]
                for values, expected in ((held, real_score), (scrambled, scrambled_score)):
                    coefficients = np.linalg.lstsq(design, values, rcond=None)[0]
                    residual = values - design @ coefficients
                    score = 1 - np.linalg.norm(residual) ** 2 / np.linalg.norm(values) ** 2
                    assert abs(score - expected) < 1e-12
                    checks += 1
with (HERE / "independent-audit.json").open("x") as stream:
    json.dump(
        {"least_squares_coherence_checks": checks, "absolute_tolerance": 1e-12, "all_passed": True},
        stream,
        indent=2,
    )
scores = json.loads((HERE / "scores.json").read_text())
fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
for offset, method, color in ((-0.18, "ordinary", "#51758c"), (0.18, "robust", "#d3992e")):
    rows = [r for r in scores["rows"] if r["method"] == method]
    x = np.arange(3) + offset
    axes[0].bar(
        x, [r["equal_window_held_gain"] for r in rows], width=0.34, color=color, label=method
    )
    axes[1].bar(x, [r["max_abs_in_bounds_shift_error_hz"] for r in rows], width=0.34, color=color)
for ax in axes:
    ax.set_xticks(range(3), ["DS7-001", "DS8-001", "DS9-001"])
axes[0].axhline(0, color="black", linewidth=0.8)
axes[0].set_ylabel("Held coherence gain vs acquisition CFO")
axes[0].legend()
axes[1].set_yscale("symlog", linthresh=1)
axes[1].axhline(5, color="black", linestyle=":", label="5 Hz prerequisite")
axes[1].set_ylabel("Maximum absolute injected-shift error (Hz)")
axes[1].legend()
fig.suptitle("Pilot frequency prerequisite: four windows / 56 frames per dataset")
fig.savefig(HERE / "pilot-split.png", dpi=160)
fig.savefig(HERE / "pilot-split.svg")
print(checks, "independent coherence checks passed")
