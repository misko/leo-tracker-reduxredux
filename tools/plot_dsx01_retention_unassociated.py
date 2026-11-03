"""Render sealed S01 remainders on the original measured GLRT CFO branches."""

import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/2026_10_18_dsx01_retention_localization"
OUTPUT = REPORT / "s01_unassociated"
RAW = ROOT / "reports/2026_10_16_dsx01_fast_association_losses/context-observations.jsonl"
PARTITION = ROOT / "reports/2026_10_17_robust_curve_reassociation/partition/DSX01-S01/curves.json"
ENDPOINTS = REPORT / "DSX01-S01/exact_validated_endpoints.json"
METHODS = {
    "shared_phase": "Shared phase",
    "family_rate": "Satellite family rate",
    "orbit_em": "Orbital MAP / EM-like",
    "penalized_split": "Penalized subdivision",
    "correlated_noise": "Correlated frequency noise",
    "receiver_smooth": "Smooth receiver error",
}
PERIOD = 1 / 4.4e-6


def run():
    OUTPUT.mkdir(exist_ok=True)
    raw = [
        r for line in RAW.read_text().splitlines() if (r := json.loads(line))["source_id"] == "S01"
    ]
    by_id = {r["observation_id"]: r for r in raw}
    tracks = json.loads(PARTITION.read_text())
    fits = json.loads(ENDPOINTS.read_text())
    graph_ids = {oid for t in tracks for oid in t["observation_ids"]}
    assert len(graph_ids) == sum(len(t["observation_ids"]) for t in tracks)
    colors = {
        t["key"]: plt.get_cmap("turbo")((i * 0.61803398875) % 1)
        for i, t in enumerate(sorted(tracks, key=lambda t: t["key"]))
    }
    ylimits = {}
    for rx in (1, 2):
        lane = [r["measured_cfo_hz"] / 1000 for r in raw if r["receiver"] == rx]
        ylimits[rx] = (min(lane) - 7, max(lane) + 7)
    handles = [
        Line2D(
            [],
            [],
            marker="o",
            color="steelblue",
            markersize=4,
            label="Unassociated GLRT + empirical polynomial; colour = graph track",
        ),
        Line2D(
            [],
            [],
            marker="x",
            color="#777777",
            linestyle="none",
            label="Unassociated GLRT outside retained polynomials",
        ),
    ]
    summaries = []
    for arm in ("c0", "fitted_c"):
        for method, label in METHODS.items():
            rows = {r["component"]: r for r in fits[f"{arm}/{method}"]["rows"]}
            assert set(rows) == {t["key"] for t in tracks}
            remaining = [t for t in tracks if not rows[t["key"]]["compatible"]]
            remaining_ids = {oid for t in remaining for oid in t["observation_ids"]}
            saved = json.loads((REPORT / f"associations/DSX01-S01/{arm}_{method}.json").read_text())
            assert saved["saved_fit_sha256"] == hashlib.sha256(ENDPOINTS.read_bytes()).hexdigest()
            unassociated = set(saved["unassociated_observation_ids"])
            loose_ids = unassociated - graph_ids
            assert unassociated == remaining_ids | loose_ids
            assert set(by_id) - unassociated == set(saved["associated_observation_ids"])
            assert unassociated <= set(by_id)

            def panel(
                ax,
                rx,
                channel=None,
                *,
                unassociated=unassociated,
                loose_ids=loose_ids,
                remaining=remaining,
            ):
                shown = [
                    r
                    for r in raw
                    if r["receiver"] == rx
                    and (channel is None or r["channel"] == channel)
                    and r["observation_id"] in unassociated
                ]
                loose = [r for r in shown if r["observation_id"] in loose_ids]
                ax.scatter(
                    [r["time_s"] for r in loose],
                    [r["measured_cfo_hz"] / 1000 for r in loose],
                    marker="x",
                    color="#777777",
                    s=12,
                    linewidths=0.7,
                    alpha=0.7,
                )
                selected = [
                    t
                    for t in remaining
                    if t["receiver"] == rx and (channel is None or t["channel"] == channel)
                ]
                labeled = (
                    {
                        t["key"]
                        for t in sorted(
                            selected, key=lambda t: len(t["observation_ids"]), reverse=True
                        )[:5]
                    }
                    if channel is None
                    else {t["key"] for t in selected}
                )
                for t in selected:
                    color = colors[t["key"]]
                    observations = [by_id[oid] for oid in t["observation_ids"]]
                    ax.scatter(
                        [r["time_s"] for r in observations],
                        [r["measured_cfo_hz"] / 1000 for r in observations],
                        color=color,
                        s=12,
                        alpha=0.85,
                        linewidths=0,
                        zorder=3,
                    )
                    native = {}
                    for oid, time, value in zip(
                        t["observation_ids"], t["times"], t["values"], strict=True
                    ):
                        assert abs(time - by_id[oid]["time_s"]) < 1e-8
                        alias = (value - by_id[oid]["measured_cfo_hz"]) / PERIOD
                        assert abs(alias - round(alias)) < 1e-7
                        native[oid] = round(alias)
                    # Draw the saved empirical polynomial, never an orbit or a
                    # line joining measured CFOs. Break at native alias changes
                    # and gaps greater than 5 s, rather than bridging branches.
                    for piece in t["pieces"]:
                        ordered = sorted(
                            piece["observation_ids"], key=lambda oid: by_id[oid]["time_s"]
                        )
                        for left, right in zip(ordered[:-1], ordered[1:], strict=True):
                            start, stop = by_id[left]["time_s"], by_id[right]["time_s"]
                            if stop - start > 5 or native[left] != native[right]:
                                continue
                            grid = np.linspace(start, stop, 8)
                            x = (grid - piece["reference_time_s"]) / piece["time_scale_s"]
                            prediction = np.polynomial.polynomial.polyval(
                                x, piece["coefficients_hz"]
                            )
                            ax.plot(
                                grid,
                                (prediction - native[left] * PERIOD) / 1000,
                                color=color,
                                lw=1.1,
                                zorder=4,
                            )
                    if t["key"] in labeled:
                        middle = observations[len(observations) // 2]
                        short = t["key"].rsplit("-", 1)[-1]
                        text = f"CH{t['channel']} {short}" if channel is None else short
                        ax.annotate(
                            text,
                            (middle["time_s"], middle["measured_cfo_hz"] / 1000),
                            xytext=(3, 5),
                            textcoords="offset points",
                            color=color,
                            fontsize=7,
                            bbox=dict(facecolor="white", alpha=0.8, edgecolor="none", pad=0.5),
                        )
                lane_name = f"RX{rx}" + (f" CH{channel}" if channel else " · all channels")
                ax.set(
                    title=(
                        f"{lane_name} · {len(shown):,} unassociated GLRT · {len(selected)} tracks"
                    ),
                    xlabel="Seconds from scan start",
                    ylabel="Measured GLRT CFO (kHz)",
                    xlim=(0, 300),
                    ylim=ylimits[rx],
                )
                ax.grid(alpha=0.18)
                return dict(
                    receiver=rx,
                    channel=channel,
                    unassociated_glrt=len(shown),
                    unassociated_tracks=len(selected),
                    glrt_without_polynomial=len(loose),
                )

            title = (
                f"DSX01 S01 — {label} — {'fitted c' if arm == 'fitted_c' else 'c = 0'}\n"
                f"{len(unassociated):,} unassociated GLRT / {len(raw):,} total: "
                f"{len(remaining_ids):,} on {len(remaining)} tracks + "
                f"{len(loose_ids)} outside polynomials"
            )
            fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True, layout="constrained")
            panels = [panel(axes[rx - 1], rx) for rx in (1, 2)]
            assert sum(r["unassociated_glrt"] for r in panels) == len(unassociated)
            fig.suptitle(title, fontsize=13)
            fig.legend(handles=handles, loc="outside lower center", fontsize=9)
            fig.savefig(OUTPUT / f"{arm}_{method}.png", dpi=160)
            plt.close(fig)
            fig, axes = plt.subplots(8, 2, figsize=(17, 25), sharex=True, layout="constrained")
            channels = [panel(axes[ch - 1, rx - 1], rx, ch) for ch in range(1, 9) for rx in (1, 2)]
            assert sum(r["unassociated_glrt"] for r in channels) == len(unassociated)
            fig.suptitle(title, fontsize=14)
            fig.legend(handles=handles, loc="outside lower center", fontsize=9)
            fig.savefig(OUTPUT / f"{arm}_{method}_by_channel.png", dpi=145)
            plt.close(fig)
            summaries.append(
                dict(
                    method=method,
                    arm=arm,
                    raw_glrt=len(raw),
                    unassociated_glrt=len(unassociated),
                    unassociated_tracks=len(remaining),
                    glrt_on_unassociated_tracks=len(remaining_ids),
                    glrt_outside_polynomials=len(loose_ids),
                    track_keys=[t["key"] for t in remaining],
                    receiver_panels=panels,
                    channel_panels=channels,
                )
            )
            print(arm, method, len(unassociated), "GLRT;", len(remaining), "tracks", flush=True)
    (OUTPUT / "counts.json").write_text(
        json.dumps(
            dict(
                source_sha256={
                    str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (RAW, PARTITION, ENDPOINTS, Path(__file__))
                },
                frequency_axis=(
                    "original measured CFO; saved polynomial lifted back to each native branch"
                ),
                colors_consistent_across_methods_and_c_arms=True,
                observations_and_assignments_unchanged=True,
                methods=summaries,
            ),
            indent=2,
        )
        + "\n"
    )
    lines = [
        "# DSX01 S01: unassociated GLRT and graph tracks",
        "",
        "Original measured CFO is plotted against scan time. Coloured dots and lines show "
        "unassociated GLRT points and their saved empirical polynomials; grey crosses show "
        "unassociated GLRT outside retained polynomials. Colours identify the same graph track "
        "across all methods. Native alias changes and gaps over 5 seconds are not bridged. "
        "Each method uses its own independently fitted position and the final exact-audited "
        "assignments. No association or fit was changed for these plots.",
        "",
    ]
    for method, label in METHODS.items():
        r = next(r for r in summaries if r["method"] == method and r["arm"] == "fitted_c")
        lines += [
            f"## {label}",
            "",
            f"{r['unassociated_glrt']:,} unassociated GLRT: "
            f"{r['glrt_on_unassociated_tracks']:,} on {r['unassociated_tracks']} tracks + "
            f"{r['glrt_outside_polynomials']} outside polynomials.",
            "",
            f"![{label}, fitted c](fitted_c_{method}.png)",
            "",
            f"[Channel detail](fitted_c_{method}_by_channel.png) · "
            f"[c=0 overview](c0_{method}.png) · [c=0 channel detail](c0_{method}_by_channel.png)",
            "",
        ]
    (OUTPUT / "README.md").write_text("\n".join(lines))


if __name__ == "__main__":
    run()
