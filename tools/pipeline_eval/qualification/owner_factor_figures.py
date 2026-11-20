"""Plot sealed position and same-observation residuals for the owner oracle."""

import argparse
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from ..__main__ import save_json
from ..scoring import ARMS
from .fresh_scenes import _read, _sha
from .owner_factor import CASES, FILE, REPORT, RESIDUALS, _load

LABELS = {
    "archived_v5": "Original v5 archive",
    "blind_exact": "Blind lean exact",
    "lean_owner_lean_alias": "Lean owners · lean aliases",
    "lean_owner_v5_alias": "Lean owners · v5 aliases",
    "v5_owner_lean_alias": "v5 owners · lean aliases",
    "v5_owner_v5_alias": "v5 owners · v5 aliases",
    "v5_common_clock": "v5 owners · compact clock/prior",
    "v5_full_lean": "Full v5 mask · lean model",
    "v5_full_clock": "Full v5 mask · compact clock/prior",
    "v5_full_diagonal": "Full v5 mask · compact diagonal noise",
}
COMMON = (
    "archived_v5",
    "lean_owner_lean_alias",
    "lean_owner_v5_alias",
    "v5_owner_lean_alias",
    "v5_owner_v5_alias",
    "v5_common_clock",
)
COLORS = ("#0c6d79", "#a3411d")


def _bars(folder, name, title, xlabel, cells, rows, *, status=False):
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.facecolor": "#f7f8fa",
        }
    )
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), sharex=True, sharey=True)
    fig.subplots_adjust(left=0.26, right=0.96, top=0.86, bottom=0.11, hspace=0.37, wspace=0.15)
    fig.suptitle(title, fontsize=20, weight="bold", x=0.04, ha="left")
    for axis, case in zip(axes.flat, CASES, strict=True):
        axis.set_facecolor("white")
        axis.set_title(case, loc="left", fontweight="bold")
        for index, cell in enumerate(cells):
            if cell in ("lean_owner_lean_alias", "v5_full_lean"):
                axis.axhline(index - 0.5, color="#d7dde4", linewidth=0.8)
            for j, arm in enumerate(ARMS):
                observed = rows.get((case, cell, arm))
                if observed is None:
                    continue
                x, state = observed
                marker = "D" if cell == "archived_v5" else "o"
                solid = (
                    not status or cell == "archived_v5" or (cell == "blind_exact" and state == "ok")
                )
                axis.scatter(
                    x,
                    index + 0.14 * (-1 if j == 0 else 1),
                    marker=marker,
                    s=44,
                    facecolors=COLORS[j] if solid else "white",
                    edgecolors=COLORS[j],
                    linewidths=1.5,
                    zorder=3,
                )
        axis.set_xscale("symlog", linthresh=0.1 if status else 20)
        axis.set_yticks(range(len(cells)), [LABELS[cell] for cell in cells], fontsize=9)
        axis.set_ylim(len(cells) - 0.4, -0.6)
        axis.grid(axis="x", alpha=0.30, linewidth=0.8)
        axis.set_xlabel(xlabel)
    fig.text(0.04, 0.906, "Common conditional samples and causal orbit snapshots", fontsize=11)
    fig.text(0.27, 0.033, "Teal · c = 0", color=COLORS[0], weight="bold", fontsize=11)
    fig.text(0.41, 0.033, "Rust · fitted c", color=COLORS[1], weight="bold", fontsize=11)
    if status:
        fig.text(0.56, 0.033, "Open marker · forced diagnostic or withheld fit", fontsize=10)
    fig.savefig(folder / f"{name}.png", dpi=165)
    fig.savefig(folder / f"{name}.pdf")
    plt.close(fig)


def generate(folder):
    seal = _read(folder / "prediction-lock.json")
    if any(_sha(folder / n) != seal["files"][n] for n in (FILE, RESIDUALS)):
        raise ValueError("samples or fits changed after the prediction seal")
    positions = {
        (r["case"], r["cell"], r["arm"]): (r["error_km"], r.get("status"))
        for r in _read(folder / "scores.json")
        if r["error_km"] is not None
    }
    _bars(
        folder,
        "owner-oracle-position",
        "Position error · privileged owner and alias oracle",
        "Distance to reference (km)",
        tuple(LABELS),
        positions,
        status=True,
    )
    samples = defaultdict(list)
    v5 = defaultdict(list)
    for row in _load(folder / RESIDUALS):
        case, cell, arm = row["case"], row["cell"], row["arm"]
        if cell in COMMON:
            samples[case, cell, arm].append(row["residual_hz"])
        if cell == "v5_owner_v5_alias":
            v5[case, "archived_v5", arm].append(row["archived_v5_residual_hz"])
    fit = {
        k: (float(np.sqrt(np.mean(np.square(values)))), None)
        for k, values in (samples | v5).items()
    }
    _bars(
        folder,
        "owner-oracle-frequency",
        "CFO residual on identical points · privileged oracle",
        "Unweighted conditional residual RMS (Hz)",
        COMMON,
        fit,
    )
    figures = [
        f"owner-oracle-{k}.{ext}" for k in ("position", "frequency") for ext in ("png", "pdf")
    ]
    save_json(
        folder / "figure-lock.json",
        dict(
            cases=list(CASES),
            prediction_lock_sha256=_sha(folder / "prediction-lock.json"),
            files={name: _sha(folder / name) for name in ("scores.json", *figures)},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=REPORT)
    generate(parser.parse_args().evidence)
