"""Synthetic position-gradient check while crossing taper boundaries."""

import json
from pathlib import Path
from types import SimpleNamespace

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from test_elevation import evaluate, fixture, predict_elevation, predict_orbits  # noqa: E402

HERE = Path(__file__).resolve().parent
bank, obs, prior, center, shifts = fixture()
obs.times_s[:] = 10
bank.position_km -= 10 * bank.velocity_km_s
score = SimpleNamespace(sigma_hz=150, detection_budget=1.2, clutter_rate=0.3)
measured = predict_orbits(bank, obs, prior, center, shifts)[0][:, 2] + 40


def value(point):
    frequency, _, spatial, _ = predict_orbits(bank, obs, prior, point, shifts)
    elevation, e_spatial, _ = predict_elevation(bank, obs, prior, point, shifts)
    terms = evaluate(measured, frequency, elevation, score)
    gradient = np.einsum("nk,nki->i", terms["prediction_gradient"], spatial)
    gradient += np.einsum("nk,nki->i", terms["elevation_gradient"], e_spatial)
    return terms["nll"], gradient[0], elevation[0, 1]


rows = []
for offset in np.linspace(-0.2, 0.2, 81):
    point = center + np.array([offset, 0])
    nll, gradient, elevation = value(point)
    step = np.array([0.001, 0])
    fd = (value(point + step)[0] - value(point - step)[0]) / 0.002
    rows.append(
        dict(
            offset_km=float(offset),
            nll=nll,
            analytic=float(gradient),
            finite_difference=fd,
            elevation_deg=float(elevation),
        )
    )
summary = dict(
    maximum_absolute_gradient_difference=max(
        abs(r["analytic"] - r["finite_difference"]) for r in rows
    ),
    rows=rows,
)
(HERE / "synthetic.json").write_text(json.dumps(summary, indent=2) + "\n")
fig, axes = plt.subplots(1, 2, figsize=(10, 4), layout="constrained")
x = [r["offset_km"] * 1000 for r in rows]
axes[0].plot(x, [r["elevation_deg"] for r in rows])
axes[0].axhline(0, linestyle="--", color="gray")
axes[0].set_ylabel("Candidate elevation (degrees)")
axes[1].plot(x, [r["analytic"] for r in rows], label="Chain-rule derivative")
axes[1].plot(x, [r["finite_difference"] for r in rows], "--", label="Central difference")
axes[1].set_ylabel("Objective derivative per km east")
axes[1].legend()
for ax in axes:
    ax.set_xlabel("Hypothesized receiver displacement east (m)")
fig.suptitle("Synthetic geometry check across the horizon")
fig.savefig(HERE / "geometry.png", dpi=160)
print(summary["maximum_absolute_gradient_difference"])
