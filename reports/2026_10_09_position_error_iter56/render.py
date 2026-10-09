"""Synthetic horizon illustration; no recording or reference coordinates."""

from pathlib import Path
from types import SimpleNamespace

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from smooth_likelihood import evaluate, taper  # noqa: E402

from leo.analysis.hard60_score import likelihood  # noqa: E402

HERE = Path(__file__).resolve().parent
score = SimpleNamespace(sigma_hz=150, detection_budget=1.2, clutter_rate=0.3)
x = np.linspace(-0.2, 1.2, 701)
measured = np.array([0.0])
prediction = np.array([[40.0, 400.0, -300.0]])
hard, smooth = [], []
for elevation in x:
    elevations = np.array([[elevation, 10.0, 20.0]])
    hard.append(likelihood(measured, prediction, elevations >= 0, score).nll)
    smooth.append(evaluate(measured, prediction, elevations, score)["nll"])
fig, axes = plt.subplots(1, 2, figsize=(10, 4), layout="constrained")
axes[0].plot(x, (x >= 0).astype(float), label="Hard visibility")
axes[0].plot(x, taper(x)[0], label="Smooth detection weight")
axes[0].set(ylabel="Detection multiplier")
axes[1].plot(x, hard, label="Existing likelihood")
axes[1].plot(x, smooth, label="Smooth likelihood")
axes[1].set(ylabel="Negative log likelihood")
for ax in axes:
    ax.set_xlabel("One candidate elevation (degrees)")
    ax.legend()
fig.suptitle("Synthetic check: smooth signal and no-detection normalization")
fig.savefig(HERE / "horizon.png", dpi=160)
