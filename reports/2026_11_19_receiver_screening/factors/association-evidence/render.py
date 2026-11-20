"""Render association evidence from sealed point and hypothesis files only."""

import csv
import gzip
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
PERIOD = 1 / 4.4e-6
LEVELS = ["L0", "L1", "L2", "L3", "L4r"]


def figure(case):
    data = json.loads((HERE / f"{case}-candidate-fits.json").read_bytes())
    source = json.loads(gzip.decompress((HERE / f"{case}-native-trace.json.gz").read_bytes()))
    t, y = map(np.asarray, (data["t"], data["y"]))
    held, train = map(np.asarray, (data["held"], data["train"]))
    curve = source["trace"]["observation"]["tracks"][data["target"]["index"]]
    lane = [
        r
        for r in source["native_points"]
        if (r["receiver"], r["channel"]) == (curve["receiver"], curve["channel"])
        and t[0] - 8 <= r["t"] <= t[-1] + 8
    ]
    rows = [r for r in data["fits"] if r["arm"] == "c0"]
    table = {(r["regime"], r["norad"], r["level"]): r for r in rows}
    leaders = {
        regime: sorted(
            (r for r in rows if r["regime"] == regime and r["level"] == "L3"),
            key=lambda r: r["training_loss"],
        )
        for regime in ("causal", "later")
    }
    leaders = {regime: values for regime, values in leaders.items() if values}
    polynomial = min(data["audits"], key=lambda r: r["train_whitened_bic"])
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
    figure, axes = plt.subplots(3, 2, figsize=(14, 12), constrained_layout=True)
    context, score, overlays, residual, ranks, geometry = axes.flat
    for name, group, color, marker in (
        ("Untracked native winner", [r for r in lane if r["graph_track"] is None], ".55", "x"),
        (
            "Graph tracked, unowned by v5",
            [r for r in lane if r["graph_track"] is not None and r["v5_c0"] is None],
            "#bd6822",
            ".",
        ),
    ):
        context.scatter(
            [r["t"] for r in group],
            [r["wrapped_hz"] / 1000 for r in group],
            s=13,
            c=color,
            marker=marker,
            label=name,
        )
    colors = plt.get_cmap("tab10")
    for i, number in enumerate(sorted({r["v5_c0"] for r in lane if r["v5_c0"] is not None})):
        group = [r for r in lane if r["v5_c0"] == number]
        context.scatter(
            [r["t"] for r in group],
            [r["wrapped_hz"] / 1000 for r in group],
            s=13,
            color=colors(i),
            label=f"v5 owner {number}",
        )
    target = [r for r in lane if r["graph_track"] == data["target"]["index"]]
    context.scatter(
        [r["t"] for r in target],
        [r["wrapped_hz"] / 1000 for r in target],
        s=20,
        facecolor="none",
        edgecolor="black",
        linewidths=0.6,
        label="Target",
    )
    context.set(
        title=f"Native context, RX {curve['receiver']} channel {curve['channel']}",
        ylabel="Wrapped CFO (kHz)",
    )
    context.legend(fontsize=7, ncol=2)
    marked = score.scatter(
        [r["t"] for r in lane],
        [r["wrapped_hz"] / 1000 for r in lane],
        c=[r["margin"] for r in lane],
        s=17,
        cmap="viridis",
    )
    figure.colorbar(marked, ax=score, label="Fractional GLRT margin")
    score.set(title="Native frequency evidence", ylabel="Wrapped CFO (kHz)")
    overlays.scatter(t[train], y[train] / 1000, color="black", marker=".", label="Training")
    overlays.scatter(t[held], y[held] / 1000, color="black", facecolors="none", s=24, label="Held")
    for j, (regime, values) in enumerate(leaders.items()):
        best = values[0]
        number = best["norad"]
        f = np.asarray(best["physical_hz"])
        overlays.plot(
            t,
            (f + best["alias"] * PERIOD) / 1000,
            "--",
            color=colors(j + 1),
            label=f"{regime} {number} orbit + alias",
        )
        overlays.plot(
            t,
            np.asarray(best["adjusted_hz"]) / 1000,
            color=colors(j + 1),
            label=f"{regime} + radio / {best['phase_s']:.2f}s",
        )
        residual.plot(
            t, best["residual_hz"], color=colors(j + 1), marker=".", label=f"{regime} {number}"
        )
    overlays.set(
        title="Selected native lift and matched Doppler hypotheses", ylabel="Alias-lifted CFO (kHz)"
    )
    overlays.legend(fontsize=7)
    residual.plot(
        t,
        y - np.asarray(polynomial["polynomial_hz"]),
        color=".3",
        ls="--",
        label=f"Polynomial d={polynomial['degree']}",
    )
    residual.axhline(0, color=".7", linewidth=0.8)
    for group in np.unique(np.asarray(data["blocks"])[held]):
        bound = t[np.asarray(data["blocks"]) == group]
        residual.axvspan(min(bound), max(bound), color="#fdb557", alpha=0.15)
    residual.set(
        title="Residuals with held time groups shaded", ylabel="Measured minus fitted (Hz)"
    )
    residual.legend(fontsize=7)
    finalists = [(regime, r["norad"]) for regime, values in leaders.items() for r in values[:4]]
    matrix = np.asarray(
        [
            [
                table[key]["held_whitened_loss"] if key in table else np.nan
                for key in [(regime, number, level) for level in LEVELS]
            ]
            for regime, number in finalists
        ]
    )
    mesh = ranks.imshow(np.log10(np.maximum(matrix, 1e-4)), aspect="auto", cmap="magma_r")
    ranks.set(
        xlabel="Nuisance level",
        xticks=range(5),
        xticklabels=LEVELS,
        yticks=range(len(finalists)),
        yticklabels=[f"{a} {b}" for a, b in finalists],
        title="Held loss for training-ranked finalists",
    )
    figure.colorbar(mesh, ax=ranks, label="log₁₀ whitened loss per point")
    first = np.asarray(source["trace"]["training"][0]["state"]["xy"])
    last = np.asarray(source["trace"]["fit_states"]["c0"]["xy"])
    geometry.plot(*np.vstack((first, last)).T, "o-", label="Train → pool c=0")
    for j, (regime, values) in enumerate(leaders.items()):
        axis = np.asarray(values[0]["weak_axis_en"])
        geometry.plot(
            *np.vstack((last - 2 * axis, last + 2 * axis)).T,
            "--",
            color=colors(j + 1),
            label=f"{regime} weak axis",
        )
    geometry.set(
        title="Training shift and target geometry",
        xlabel="East of tile center (km)",
        ylabel="North of tile center (km)",
    )
    geometry.set_aspect("equal", adjustable="datalim")
    geometry.legend(fontsize=7)
    for ax in (context, score, overlays, residual):
        ax.set_xlabel("Seconds from native acquisition anchor")
    figure.suptitle(
        f"{case}  |  Graph track {data['target']['index']}"
        "  |  causal and diagnostic later elements",
        fontsize=14,
    )
    figure.savefig(HERE / f"{case}-association.png", dpi=165)
    plt.close(figure)
    return [
        (
            case,
            regime,
            rank + 1,
            row["norad"],
            row["phase_s"],
            row["alias"],
            row["full_rms_hz"],
            row["held_rms_hz"],
            row["training_loss"],
            row["held_whitened_loss"],
            row["element"]["sha256"],
        )
        for regime, values in leaders.items()
        for rank, row in enumerate(values[:5])
    ]


def phase_figure():
    data = json.loads((HERE / "DS26-0223-v5-phase.json").read_bytes())
    t = np.array(data["times_s"])
    figure, (time, magnitude) = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    conditions = ("current_zero", "current_saved", "later_zero", "previous_saved")
    labels = (
        "Causal · zero phase",
        "Causal · saved phase",
        "Later · zero phase",
        "Previous · saved phase",
    )
    colors = ("#6e6564", "#007780", "#a86d0c", "#703a82")
    c0 = data["arms"]["c0"]["projections"]
    for key, label, color in zip(conditions, labels, colors, strict=True):
        time.plot(t, np.array(c0[key]["raw_residual_hz"]) / 1000, ".-", label=label, color=color)
    time.set(
        xlabel="Seconds from acquisition anchor",
        ylabel="Fixed-state residual (kHz)",
        title="Original v5 site, hardware and alias · c=0",
    )
    time.legend(fontsize=8)
    for i, arm in enumerate(("c0", "fitted_c")):
        rows = data["arms"][arm]["projections"]
        values = [rows[key]["fixed_rms_hz"] for key in conditions]
        values.append(data["arms"][arm]["saved_gate"]["conditional_rms_hz"])
        magnitude.bar(
            np.arange(5) + (i - 0.5) * 0.34,
            values,
            width=0.34,
            label=("c=0", "Fitted c")[i],
            color=("#007780", "#587bbc")[i],
        )
    magnitude.set(
        yscale="log",
        ylabel="Whole-component RMS (Hz)",
        title="Phase sensitivity and published gate",
        xticks=np.arange(5),
        xticklabels=(
            "Causal\nzero",
            "Causal\nsaved",
            "Later\nzero",
            "Previous\nsaved",
            "Published\ngate",
        ),
    )
    magnitude.legend(fontsize=8)
    figure.suptitle("DS26-0223 · 62 native points published as NORAD 67315")
    figure.savefig(HERE / "DS26-0223-v5-phase.png", dpi=165)
    plt.close(figure)


def main():
    rows = [r for ident in ("DS26-0223", "DS29-0316") for r in figure(ident)]
    phase_figure()
    with (HERE / "association_summary.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            (
                "case",
                "regime",
                "training_rank",
                "norad",
                "phase_s",
                "lift_alias",
                "all_rms_hz",
                "held_rms_hz",
                "train_loss",
                "held_loss",
                "element_sha256",
            )
        )
        writer.writerows(rows)
    names = [p.name for p in HERE.iterdir() if p.is_file() and p.name != "artifact-lock.json"]
    (HERE / "artifact-lock.json").write_text(
        json.dumps(
            {k: hashlib.sha256((HERE / k).read_bytes()).hexdigest() for k in sorted(names)},
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
