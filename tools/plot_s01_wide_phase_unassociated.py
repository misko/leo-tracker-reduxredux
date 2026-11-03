"""Plot remaining graph-derived polynomial fragments on original GLRT branches."""

import json

import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from plot_s01_phase_sensitivity import OUTPUT, RAW, ROOT

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

PERIOD = 1 / 4.4e-6
PARTITION = ROOT / "reports/2026_10_17_robust_curve_reassociation/partition/DSX01-S01/curves.json"


def run():
    result = json.loads((OUTPUT / "fitted_c/association_cap_2.7.json").read_text())
    final = json.loads((OUTPUT / "summary.json").read_text())
    assert all(r["associated"] == result["compatible_points"] for r in final
               if r["phase_bound_floor_s"] >= 2.7)
    tracks = json.loads(PARTITION.read_text())
    raw = [r for line in RAW.read_text().splitlines()
           if (r := json.loads(line))["source_id"] == "S01"]
    byid = {r["observation_id"]: r for r in raw}
    admitted = set(result["associated_observation_ids"])
    rows = {r["component"]: r for r in result["association"]["rows"]}
    remaining = [t for t in tracks if not rows[t["key"]]["compatible"]]
    graph_ids = {oid for t in tracks for oid in t["observation_ids"]}
    unassociated = set(byid) - admitted
    remaining_ids = {oid for t in remaining for oid in t["observation_ids"]}
    assert remaining_ids == graph_ids - admitted
    assert unassociated == set(result["unassociated_observation_ids"])
    loose_ids = unassociated - graph_ids
    color = {t["key"]: plt.get_cmap("turbo")((i * 0.61803398875) % 1)
             for i, t in enumerate(remaining)}

    def panel(ax, rx, channel=None):
        lane = [r for r in raw if r["receiver"] == rx
                and (channel is None or r["channel"] == channel)]
        shown = [r for r in lane if r["observation_id"] in unassociated]
        loose = [r for r in shown if r["observation_id"] in loose_ids]
        ax.scatter([r["time_s"] for r in loose],
                   [r["measured_cfo_hz"] / 1000 for r in loose],
                   color="#777777", marker="x", s=10, linewidths=0.6, alpha=0.75)
        selected = [t for t in remaining if t["receiver"] == rx
                    and (channel is None or t["channel"] == channel)]
        for t in selected:
            observations = [byid[oid] for oid in t["observation_ids"]]
            c = color[t["key"]]
            ax.scatter([r["time_s"] for r in observations],
                       [r["measured_cfo_hz"] / 1000 for r in observations],
                       s=11, color=c, alpha=0.85, linewidths=0, zorder=3)
            native = {}
            for oid, time, value in zip(t["observation_ids"], t["times"], t["values"],
                                        strict=True):
                assert byid[oid]["time_s"] == time
                alias = (value - byid[oid]["measured_cfo_hz"]) / PERIOD
                assert abs(alias - round(alias)) < 1e-8
                native[oid] = round(alias)
            for piece in t["pieces"]:
                ordered = sorted(piece["observation_ids"], key=lambda oid: byid[oid]["time_s"])
                for left, right in zip(ordered[:-1], ordered[1:], strict=True):
                    start, stop = byid[left]["time_s"], byid[right]["time_s"]
                    if stop - start > 5 or native[left] != native[right]:
                        continue
                    time = np.linspace(start, stop, 12)
                    x = (time - piece["reference_time_s"]) / piece["time_scale_s"]
                    prediction = np.polynomial.polynomial.polyval(x, piece["coefficients_hz"])
                    ax.plot(time, (prediction - native[left] * PERIOD) / 1000,
                            color=c, linewidth=1.2, zorder=4)
            if channel is not None:
                middle = observations[len(observations) // 2]
                ax.annotate(t["key"].split("-", 3)[-1],
                            (middle["time_s"], middle["measured_cfo_hz"] / 1000),
                            xytext=(3, 4), textcoords="offset points", color=c, fontsize=7,
                            bbox=dict(facecolor="white", alpha=0.75, edgecolor="none", pad=0.3))
        lo = min(r["measured_cfo_hz"] for r in lane) / 1000
        hi = max(r["measured_cfo_hz"] for r in lane) / 1000
        name = f"RX{rx}" + (f" CH{channel}" if channel else " · all 8 channels")
        ax.set(title=f"{name} · {len(shown):,} GLRT · {len(selected)} fragments",
               xlabel="Seconds from scan start", ylabel="Measured GLRT CFO (kHz)",
               xlim=(0, 300), ylim=(lo - 7, hi + 7))
        ax.grid(alpha=0.15)
        return dict(receiver=rx, channel=channel, glrt_points=len(shown),
                    polynomial_fragments=len(selected), raw_without_polynomial=len(loose))

    handles = [Line2D([], [], marker="o", color="steelblue", markersize=4,
                      label="GLRT dots + polynomial lines; colour identifies a graph fragment"),
               Line2D([], [], marker="x", color="#777777", linestyle="none",
                      label="Unassociated GLRT without retained polynomial")]
    title = ("DSX01 S01 — unassociated after wider satellite-phase search\n"
             f"{len(unassociated):,} GLRT = {len(remaining_ids):,} on {len(remaining)} "
             f"polynomial fragments + {len(loose_ids)} without a retained polynomial\n"
             "Graph tracks preserved; provisional matches at −1.0 s and −2.7 s; "
             "same remainder through ±15 s")
    fig, axes = plt.subplots(2, 1, figsize=(14, 9), layout="constrained")
    stats = [panel(axes[rx - 1], rx) for rx in (1, 2)]
    fig.suptitle(title, fontsize=13)
    fig.legend(handles=handles, loc="outside lower center", fontsize=9)
    fig.savefig(OUTPUT / "unassociated_tracks_and_glrt.png", dpi=170)
    plt.close(fig)
    fig, axes = plt.subplots(8, 2, figsize=(16, 23), layout="constrained")
    for ch in range(1, 9):
        for rx in (1, 2):
            stats.append(panel(axes[ch - 1, rx - 1], rx, ch))
    fig.suptitle(title, fontsize=14)
    fig.legend(handles=handles, loc="outside lower center", fontsize=9)
    fig.savefig(OUTPUT / "unassociated_tracks_and_glrt_by_channel.png", dpi=160)
    plt.close(fig)
    write(OUTPUT / "unassociated_plot_counts.json", dict(
        raw_points=len(raw), associated=len(admitted), unassociated=len(unassociated),
        polynomial_fragments=len(remaining), polynomial_points=len(remaining_ids),
        without_polynomial=len(loose_ids), panels=stats,
    ))


if __name__ == "__main__":
    run()
