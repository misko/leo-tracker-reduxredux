"""Independent dense joint/train evidence audit and ablation figure."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "2026_09_28_pilot_split_transfer"


def lme(values):
    top = max(values)
    return float(top + np.log(np.mean(np.exp(values - top))))


def dense_bf(values, times, frequencies, variance):
    n, tones = values.shape
    covariance = np.eye(n) + np.ones((n, n))
    precision = np.linalg.inv(covariance)
    _, logdet = np.linalg.slogdet(covariance)
    rotated = (
        np.exp(-2j * np.pi * frequencies[:, None, None] * times[None, :, None]) * values[None, :, :]
    )
    energy = np.sum(np.abs(values) ** 2 / variance)
    quadratic = np.einsum("fnt,nm,fmt->ft", rotated.conj(), precision, rotated, optimize=True).real
    return -tones * logdet + energy - np.sum(quadratic / variance, axis=1)


checks = []
for dataset in ("DS7", "DS8", "DS9"):
    result = json.loads((HERE / dataset / "result.json").read_text())
    source = json.loads((SOURCE / dataset / "result.json").read_text())
    archive = np.load(SOURCE / dataset / "matrices.npz", allow_pickle=False)
    posterior = np.load(HERE / dataset / "posterior.npz", allow_pickle=False)
    # First frame in each of four frozen windows; no quality/outcome selection.
    for window in source["windows"]:
        original = window["frames"][0]
        key = original["matrix_key"]
        (row,) = [r for r in result["rows"] if r["matrix_key"] == key]
        (ordinary,) = [m for m in original["methods"] if m["method"] == "ordinary"]
        frequencies = np.r_[posterior["frequencies_hz"], ordinary["fit"]["frequency_hz"]]
        values, times = archive[key], archive["times_s"]
        variance = np.mean(np.abs(values[::2]) ** 2, axis=0)
        training = dense_bf(values[::2], times[::2], frequencies, variance)
        norm = max(training[:-1]) + np.log(np.exp(training[:-1] - max(training[:-1])).sum())
        weight_error = float(
            np.max(np.abs(np.exp(training[:-1] - norm) - posterior[key + "_weights"]))
        )
        assert weight_error < 1e-10
        rng = np.random.default_rng(original["seed"])
        control = values.copy()
        control[1::2] *= (1j ** rng.integers(0, 4, 75))[:, None]
        for label, observed in (("real", values), ("scrambled", control)):
            joint = dense_bf(observed, times, frequencies, variance)
            zero = 200
            expected = {
                "fixed_zero": joint[zero] - training[zero],
                "ordinary_point": joint[-1] - training[-1],
                "frequency_mixture": lme(joint[:-1]) - lme(training[:-1]),
                "fixed_zero_null": np.logaddexp(0, joint[zero]) - np.logaddexp(0, training[zero]),
                "frequency_mixture_null": np.logaddexp(0, lme(joint[:-1]))
                - np.logaddexp(0, lme(training[:-1])),
            }
            for name, value in expected.items():
                error = abs(float(value) - row["arms"][name][label]["log_ratio_to_noise"])
                assert error < 1e-8, (dataset, key, label, name, error)
                checks.append(
                    {
                        "dataset": dataset,
                        "matrix": key,
                        "label": label,
                        "method": name,
                        "absolute_error": error,
                    }
                )
with (HERE / "independent-audit.json").open("x") as stream:
    json.dump(
        {"dense_joint_train_checks": len(checks), "posterior_weight_checks": 12, "rows": checks},
        stream,
        indent=2,
    )
scores = json.loads((HERE / "scores.json").read_text())
fig, ax = plt.subplots(figsize=(11, 4.5), constrained_layout=True)
methods = [
    ("ordinary_point", "Point refinement", "#999999"),
    ("frequency_mixture", "Frequency mixture", "#51758c"),
    ("fixed_zero_null", "Acquisition + null", "#72935b"),
    ("frequency_mixture_null", "Frequency mixture + null", "#d3992e"),
]
for i, (method, label, color) in enumerate(methods):
    values = [
        s["arms"][method]["held_gain_vs_fixed_zero_nats_per_frame"] for s in scores["summaries"]
    ]
    ax.bar(np.arange(3) + (i - 1.5) * 0.19, values, width=0.18, label=label, color=color)
ax.axhline(0, color="black", linewidth=0.8)
ax.set_xticks(range(3), ["DS7-001", "DS8-001", "DS9-001"])
ax.set_ylabel("Held predictive gain (nats/frame) vs fixed acquisition CFO")
ax.set_title("Frequency uncertainty and noise-only hypothesis: separate ablations")
ax.legend(loc="upper left", fontsize=9)
fig.savefig(HERE / "ablation.png", dpi=160)
fig.savefig(HERE / "ablation.svg")
print(len(checks), "dense joint/train checks passed")
