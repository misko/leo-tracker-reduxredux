"""Publish the Austin timing-perturbation stage from the frozen comparison scores."""

import argparse
from pathlib import Path
from statistics import median

import matplotlib.pyplot as plt

from ..__main__ import save_json
from . import austin_timing_transfer as trial
from . import austin_waveform_figures as first

SOURCE = "transfer-scores.csv"
IMAGE = "timing-transfer.png"
KEY = (
    ("stock4", "Stock four", "#146453", "o"),
    ("fifth", "Waveform fifth", "#9c5629", "s"),
    ("sham", "Half-frame sham", "#4a6685", "^"),
)


def publish(out):
    trial.wave.stock.sealed(out, "score-lock.json")
    rows = first.table(out / SOURCE)
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 6.75), sharex=True, layout="constrained")
    panels = (
        ("gated_phase_cfo_hit", "Any admitted Austin candidate", "Hits out of 4"),
        ("winner_phase_cfo_hit", "Highest-margin Austin observation", "Hits out of 4"),
        ("off_target_gate_candidates", "Other passing target-lane candidates", "Count"),
        ("cpu_ms_median", "Host detector and scout", "Median CPU (ms)"),
    )
    for axis, (field, title, unit) in zip(axes.flat, panels, strict=True):
        for j, (method, label, color, marker) in enumerate(KEY, -1):
            values = []
            for ratio in trial.RATIOS:
                cohort = [
                    r
                    for r in rows
                    if r["kind"] == "mixed"
                    and r["method"] == method
                    and r["ratio_db"] == str(ratio)
                ]
                if len(cohort) != 4:
                    raise ValueError("strength chart needs four fixed source edge/interval pairs")
                raw = [r[field] for r in cohort]
                if field.endswith("hit"):
                    values.append(sum(r == "True" for r in raw))
                elif field.endswith("candidates"):
                    values.append(sum(int(r) for r in raw))
                else:
                    values.append(median(float(r) for r in raw))
            axis.plot(
                [x + 0.31 * j for x in trial.RATIOS],
                values,
                label=label,
                color=color,
                marker=marker,
            )
        axis.set(title=title, ylabel=unit, xticks=trial.RATIOS)
        if field.endswith("hit"):
            axis.set(ylim=(-0.23, 4.24), yticks=range(5))
        axis.grid(axis="y", alpha=0.25)
    for axis in axes[-1]:
        axis.set_xlabel("Austin excerpt / recorded roof IF power (dB)")
    axes[0, 0].legend(loc="center left", fontsize=8, frameon=False)
    fig.suptitle("Stock four versus a fifth center on shifted physical Austin IQ", fontsize=14)
    fig.savefig(out / IMAGE, dpi=180)
    plt.close(fig)
    first.descriptor(
        out,
        "austin-fifth-timing-transfer",
        "Stock four versus a fifth center on shifted physical Austin IQ",
        "20 mixtures · 4 clean transfers · 2 roof-only controls · one Austin recording",
        "Measured Austin carrier/epoch shifts + two archived roof windows → blind wide GLRT",
        "The four source edge/interval combinations share one Austin recording. "
        "The CSV includes clean and roof-only controls, phase-only recovery and native telemetry.",
        IMAGE,
        SOURCE,
        trial.wave.stock.digest(out / "score-lock.json"),
    )
    path = out / "stage-lock.json"
    record = trial.wave.stock.read(path)
    save_json(path, dict(record, renderer_sha256=trial.wave.stock.digest(Path(__file__))))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=trial.REPORT)
    publish(p.parse_args().out)


if __name__ == "__main__":
    main()
