"""Frequency diagnostics for a completed sparse GLRT research replay."""

import argparse
import json
from pathlib import Path

import numpy as np

from leo.analysis.glrt_frequency_input import frequency_evidence
from leo.analysis.sparse_glrt_likelihood import SparseConfig, candidate_ratios
from tools.evaluate_sparse_glrt import local_output, prediction, write_json


def weighted_quantile(values, weights, quantile):
    values, weights = np.ravel(values), np.ravel(weights)
    order = np.argsort(values)
    total = weights.sum()
    if total <= 0:
        return None
    index = np.searchsorted(np.cumsum(weights[order]), quantile * total)
    return float(values[order[min(index, len(order) - 1)]])


def diagnostics(evidence, predicted, visible, fit, config, group_labels):
    active = fit["active"]
    offsets = np.array(fit["offsets_hz"])
    ratios = candidate_ratios(evidence, predicted[:, active], visible[:, active], offsets, config)
    weights = np.array(fit["weights"])
    mixture = weights[0] + ratios @ weights[1:]
    residual = (
        evidence.frequency_hz[:, :, None]
        - predicted[:, None, active]
        - offsets[evidence.group, None, None]
    )
    bg = config.background_scale_hz / (
        np.pi * (config.background_scale_hz**2 + evidence.frequency_hz**2)
    )
    signal = config.scale_hz / (np.pi * (config.scale_hz**2 + residual**2))
    responsibility = (
        signal
        / bg[:, :, None]
        * evidence.candidate_weight[:, :, None]
        * evidence.signal_probability[:, None, None]
        * visible[:, None, active]
        * weights[None, None, 1:]
        / mixture[:, None, None]
    )
    groups = []
    for group in range(len(offsets)):
        mask = evidence.group == group
        mass = responsibility[mask]
        groups.append(
            dict(
                receiver=group_labels[group][0],
                band=group_labels[group][1],
                factors=int(mask.sum()),
                signal_support=float(mass.sum()),
                signal_fraction=float(mass.sum() / mask.sum()),
                offset_hz=float(offsets[group]),
                median_absolute_residual_hz=weighted_quantile(np.abs(residual[mask]), mass, 0.5),
                p90_absolute_residual_hz=weighted_quantile(np.abs(residual[mask]), mass, 0.9),
            )
        )
    return dict(
        groups=groups,
        total_signal_support=float(responsibility.sum()),
        median_absolute_residual_hz=weighted_quantile(np.abs(residual), responsibility, 0.5),
        p90_absolute_residual_hz=weighted_quantile(np.abs(residual), responsibility, 0.9),
        warning=(
            "Residual summaries condition on fitted signal assignments; "
            "they do not measure localization error."
        ),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--run", type=Path, required=True)
    args = p.parse_args()
    local_output(args.run)
    metadata = json.loads((args.bundle / "input-receipt.json").read_text())
    result = json.loads((args.run / "result.json").read_text())
    source = json.loads((args.bundle / "tracking-input.json").read_text())
    evidence, _, _ = frequency_evidence(source, uniform_marks=result["uniform_marks"])
    bank = dict(np.load(args.bundle / "orbit-bank.npz"))
    config = SparseConfig(**result["config"])
    summaries = {}
    for name in ("reference", "best"):
        fit = result[name]
        predicted, visible = prediction(
            bank, evidence, metadata["site"], (fit["east_m"], fit["north_m"])
        )
        summaries[name] = diagnostics(
            evidence, predicted, visible, fit, config, metadata["group_labels"]
        )
    write_json(args.run / "frequency-diagnostics.json", summaries)

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(13, 8), sharex=True, constrained_layout=True)
    fit = result["best"]
    offsets = np.array(fit["offsets_hz"])
    strongest = evidence.frequency_hz[
        np.arange(len(evidence.ids)), evidence.candidate_weight.argmax(axis=1)
    ]
    for group, ax in enumerate(axes.flat):
        rows = np.flatnonzero(evidence.group == group)
        order = rows[np.argsort(evidence.time_s[rows])]
        strong = evidence.signal_probability[order] > 0.8
        ax.scatter(
            evidence.time_s[order], strongest[order] / 1000, s=3, c="silver", rasterized=True
        )
        ax.scatter(
            evidence.time_s[order[strong]],
            strongest[order[strong]] / 1000,
            s=5,
            c="black",
            alpha=0.5,
            rasterized=True,
        )
        for s, norad in zip(fit["active"], fit["norad"], strict=True):
            frequency = np.where(visible[order, s], predicted[order, s] + offsets[group], np.nan)
            ax.plot(
                evidence.time_s[order], frequency / 1000, linewidth=1, label=str(norad), alpha=0.8
            )
        rx, band = metadata["group_labels"][group]
        ax.set_title(
            f"RX{rx}, CH{'1–4' if band == 0 else '5–8'}; offset {offsets[group] / 1000:.2f} kHz"
        )
        ax.set_xlabel("Seconds from capture anchor")
        ax.set_ylabel("Observed / predicted CFO (kHz)")
    axes[0, 0].legend(ncol=3, fontsize=7, loc="best")
    fig.suptitle(
        "Best evaluated position: strongest GLRT peaks and selected satellite curves\n"
        "All distinct candidate peaks enter the score; black marks indicate strong GLRT"
    )
    fig.savefig(args.run / "frequency-fit.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
