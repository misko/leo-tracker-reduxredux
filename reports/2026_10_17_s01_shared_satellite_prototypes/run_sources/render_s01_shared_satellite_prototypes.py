"""Render matched coverage, GLRT associations and the 69333 family comparison."""

import json

import matplotlib
import numpy as np
from run_s01_shared_satellite_prototypes import BASELINE, OUTPUT, RAW

matplotlib.use("Agg")
import matplotlib.pyplot as plt

LABELS = {
    "family_extension": "Shared family extension",
    "prior_orbit_em": "Orbit priors + EM-like iteration",
}


def run():
    summary = json.loads((OUTPUT / "summary.json").read_text())
    raw = [
        r for line in RAW.read_text().splitlines() if (r := json.loads(line))["source_id"] == "S01"
    ]
    methods = ["family_extension", "prior_orbit_em"]
    results = {
        m: json.loads((OUTPUT / m / "fitted_c/association.json").read_text()) for m in methods
    }
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), layout="constrained")
    names = [
        "Phase-expanded\nbaseline",
        "Shared family\nextension",
        "Orbit priors +\nEM-like iteration",
    ]
    values = [2608, *[r["associated"] for r in summary if r["arm"] == "fitted_c"]]
    bars = axes[0].bar(
        names, np.array(values) / 4797 * 100, color=["#888888", "steelblue", "darkorange"]
    )
    axes[0].bar_label(
        bars, labels=[f"{n:,} / 4,797\n{n / 4797 * 100:.2f}%" for n in values], padding=5
    )
    axes[0].set(ylabel="Associated raw GLRT points (%)", ylim=(0, 90))
    for m, style in zip(methods, ["o-", "s--"], strict=True):
        history = json.loads((OUTPUT / m / "fitted_c/history.json").read_text())
        axes[1].plot(
            [r["iteration"] for r in history],
            [r["points"] for r in history],
            style,
            label=LABELS[m],
        )
    axes[1].set(
        xlabel="Association / shared-correction iteration",
        ylabel="Associated GLRT points",
        xticks=[0, 1, 2, 3],
        ylim=(2400, 3700),
    )
    axes[1].legend(fontsize=8)
    for ax in axes:
        ax.grid(axis="y", alpha=0.2)
    fig.suptitle(
        "DSX01 S01 — two shared satellite-correction prototypes\n"
        "Causal TLEs, fixed GPS and hardware; c=0 and fitted-c give identical point sets"
    )
    fig.savefig(OUTPUT / "coverage_and_iterations.png", dpi=170)
    plt.close(fig)
    all_norads = sorted(
        {r["candidate_norad"] for a in results.values() for r in a["rows"] if r["compatible"]}
    )
    colors = {n: plt.get_cmap("turbo")((i * 0.61803398875) % 1) for i, n in enumerate(all_norads)}
    partition = (
        BASELINE.parent / "2026_10_17_robust_curve_reassociation/partition/DSX01-S01/curves.json"
    )
    tracks = json.loads(partition.read_text())
    membership = {oid: t["key"] for t in tracks for oid in t["observation_ids"]}
    raw_byid = {r["observation_id"]: r for r in raw}
    track_colors = {
        t["key"]: plt.get_cmap("turbo")((i * 0.61803398875) % 1) for i, t in enumerate(tracks)
    }
    for view in ("associated", "unassociated"):
        fig, axes = plt.subplots(2, 2, figsize=(15, 9), sharex=True, layout="constrained")
        for column, m in enumerate(methods):
            result = results[m]
            row_bykey = {r["component"]: r for r in result["rows"]}
            admitted = set(result["associated_observation_ids"])
            for rx in (1, 2):
                ax = axes[rx - 1, column]
                observations = [
                    r
                    for r in raw
                    if r["receiver"] == rx
                    and ((r["observation_id"] in admitted) == (view == "associated"))
                ]
                for t in tracks:
                    r = row_bykey[t["key"]]
                    if t["receiver"] != rx or r["compatible"] != (view == "associated"):
                        continue
                    c = (
                        colors[r["candidate_norad"]]
                        if view == "associated"
                        else track_colors[t["key"]]
                    )
                    own = [raw_byid[oid] for oid in t["observation_ids"]]
                    ax.scatter(
                        [r["time_s"] for r in own],
                        [r["measured_cfo_hz"] / 1000 for r in own],
                        color=c,
                        s=8,
                        alpha=0.8,
                        linewidths=0,
                    )
                    native = {
                        oid: round((value - raw_byid[oid]["measured_cfo_hz"]) / (1 / 4.4e-6))
                        for oid, value in zip(t["observation_ids"], t["values"], strict=True)
                    }
                    for piece in t["pieces"]:
                        ids = sorted(
                            piece["observation_ids"], key=lambda oid: raw_byid[oid]["time_s"]
                        )
                        for left, right in zip(ids[:-1], ids[1:], strict=True):
                            start, stop = raw_byid[left]["time_s"], raw_byid[right]["time_s"]
                            if stop - start > 5 or native[left] != native[right]:
                                continue
                            grid = np.linspace(start, stop, 8)
                            x = (grid - piece["reference_time_s"]) / piece["time_scale_s"]
                            pred = np.polynomial.polynomial.polyval(x, piece["coefficients_hz"])
                            ax.plot(grid, (pred - native[left] / 4.4e-6) / 1000, color=c, lw=0.8)
                loose = [r for r in observations if r["observation_id"] not in membership]
                ax.scatter(
                    [r["time_s"] for r in loose],
                    [r["measured_cfo_hz"] / 1000 for r in loose],
                    color="gray",
                    marker="x",
                    s=10,
                    alpha=0.7,
                    linewidths=0.6,
                )
                lane = [r["measured_cfo_hz"] / 1000 for r in raw if r["receiver"] == rx]
                ax.set(
                    title=f"{LABELS[m]} · RX{rx} · {len(observations):,} GLRT",
                    ylabel="Measured GLRT CFO (kHz)",
                    xlabel="Seconds from scan start",
                    xlim=(0, 300),
                    ylim=(min(lane) - 5, max(lane) + 5),
                )
                ax.grid(alpha=0.15)
        color_note = (
            "colour = satellite nomination" if view == "associated" else "colour = graph fragment"
        )
        fig.suptitle(
            f"DSX01 S01 — {view} graph tracks + GLRT\n"
            f"{color_note}; gray crosses = GLRT outside retained polynomials; fitted-c"
        )
        fig.savefig(OUTPUT / f"{view}_glrt_and_tracks.png", dpi=170)
        plt.close(fig)
    fig, axes = plt.subplots(
        1, 3, figsize=(16, 4.5), sharex=True, sharey=True, layout="constrained"
    )
    # Original baseline lacks saved residual vectors; use the independently
    # recorded original residuals for the nine curved69333 members.
    source = OUTPUT.parent / "2026_10_17_s01_ch4_t001_diagnosis/fitted_c/family_summary.json"
    before = json.loads(source.read_text())["current"]["rows"]
    groups = [
        before,
        *[
            [
                r
                for r in results[m]["rows"]
                if r["candidate_norad"] == 69333 and r["active_curvature"]
            ]
            for m in methods
        ],
    ]
    keys = [r["component"] for r in before]
    c = {key: plt.get_cmap("tab10")(i) for i, key in enumerate(keys)}
    for ax, group, title in zip(
        axes, groups, ["Baseline", *[LABELS[m] for m in methods]], strict=True
    ):
        for r in group:
            key = r["component"]
            ax.plot(
                r["times_s"],
                r["residual_hz"],
                ".-",
                color=c[key],
                ms=4,
                lw=0.9,
                label=key.replace("S01-RX1-", ""),
            )
        ax.axhline(0, color="black", lw=0.7)
        ax.set(title=title, xlabel="Seconds from scan start", ylabel="Residual CFO (Hz)")
        ax.grid(alpha=0.2)
    axes[2].legend(fontsize=7, ncol=2)
    fig.suptitle(
        "69333 — same nine curved candidate fragments, shared correction per satellite\n"
        "Family extension accepts CH4 T001; orbit-prior method retains it as unassociated"
    )
    fig.savefig(OUTPUT / "69333_method_comparison.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    run()
