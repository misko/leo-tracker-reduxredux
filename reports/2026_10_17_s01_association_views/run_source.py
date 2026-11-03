"""Show every S01 GLRT point, empirical polynomial and satellite-association state."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "reports/2026_10_17_s01_association_views"
RESULT = ROOT / "reports/2026_10_17_cohort_phase_repair/curved_only/association/DSX01-S01/fitted_c"
PARTITION = ROOT / "reports/2026_10_17_robust_curve_reassociation/partition/DSX01-S01/curves.json"
RAW = ROOT / "reports/2026_10_16_dsx01_fast_association_losses/context-observations.jsonl"
PERIOD = 1 / 4.4e-6


def read(path):
    return json.loads(path.read_text())


def run():
    result, tracks = read(RESULT / "association.json"), read(PARTITION)
    raw = [
        r for line in RAW.read_text().splitlines() if (r := json.loads(line))["source_id"] == "S01"
    ]
    byid = {r["observation_id"]: r for r in raw}
    admitted = set(result["associated_observation_ids"])
    rows = {r["component"]: r for r in result["association"]["rows"]}
    all_curve_ids = [oid for t in tracks for oid in t["observation_ids"]]
    assert len(byid) == len(raw) == 4797
    assert len(set(all_curve_ids)) == len(all_curve_ids) == 4486
    assert admitted <= set(all_curve_ids) <= byid.keys()
    assert len(admitted) == result["compatible_points"] == 2291
    assert {
        oid for t in tracks if rows[t["key"]]["compatible"] for oid in t["observation_ids"]
    } == admitted
    ownership = {
        key: index
        for index, g in enumerate(result["consolidated"]["groups"])
        for key in g["members"]
    }
    assert len(ownership) == result["compatible_fragments"] == 102
    assert len(result["consolidated"]["groups"]) == 73
    assert len(tracks) - len(ownership) == 68
    palette = plt.get_cmap("turbo")
    color = {
        t["key"]: palette(
            ((ownership[t["key"]] if t["key"] in ownership else 73 + i) * 0.61803398875) % 1
        )
        for i, t in enumerate(tracks)
    }
    point_track = {oid: t["key"] for t in tracks for oid in t["observation_ids"]}
    for track in tracks:
        for oid, time, value in zip(
            track["observation_ids"], track["times"], track["values"], strict=True
        ):
            r = byid[oid]
            assert (r["receiver"], r["channel"], r["time_s"]) == (
                track["receiver"],
                track["channel"],
                time,
            )
            assert (
                abs(
                    (value - r["measured_cfo_hz"]) / PERIOD
                    - round((value - r["measured_cfo_hz"]) / PERIOD)
                )
                < 1e-8
            )

    def panel(ax, rx, view, channel=None):
        lane_raw = [
            r for r in raw if r["receiver"] == rx and (channel is None or r["channel"] == channel)
        ]
        shown = [
            r
            for r in lane_raw
            if view == "all" or (r["observation_id"] in admitted) == (view == "associated")
        ]
        loose = [r for r in shown if r["observation_id"] not in point_track]
        ax.scatter(
            [r["time_s"] for r in loose],
            [r["measured_cfo_hz"] / 1000 for r in loose],
            color="#777777",
            marker="x",
            s=12,
            linewidths=0.7,
            alpha=0.8,
            zorder=2,
        )
        count = 0
        for track in tracks:
            if track["receiver"] != rx or channel is not None and track["channel"] != channel:
                continue
            matched = track["key"] in ownership
            if view != "all" and matched != (view == "associated"):
                continue
            count += 1
            c = color[track["key"]]
            observations = [byid[oid] for oid in track["observation_ids"]]
            ax.scatter(
                [r["time_s"] for r in observations],
                [r["measured_cfo_hz"] / 1000 for r in observations],
                s=9 if channel is None else 13,
                color=c,
                alpha=0.85,
                linewidths=0,
                zorder=3,
            )
            if channel is not None:
                middle = observations[len(observations) // 2]
                label = track["key"].split("-", 3)[-1].split(":")[0]
                ax.annotate(
                    label,
                    (middle["time_s"], middle["measured_cfo_hz"] / 1000),
                    xytext=(3, 4),
                    textcoords="offset points",
                    fontsize=6,
                    color=c,
                    bbox=dict(facecolor="white", alpha=0.7, edgecolor="none", pad=0.2),
                )
            native = {
                oid: int(round((value - byid[oid]["measured_cfo_hz"]) / PERIOD))
                for oid, value in zip(track["observation_ids"], track["values"], strict=True)
            }
            for piece in track["pieces"]:
                ordered = sorted(piece["observation_ids"], key=lambda oid: byid[oid]["time_s"])
                for left, right in zip(ordered[:-1], ordered[1:], strict=True):
                    start, stop = byid[left]["time_s"], byid[right]["time_s"]
                    if stop - start > 5 or native[left] != native[right]:
                        continue
                    time = np.linspace(start, stop, 10)
                    x = (time - piece["reference_time_s"]) / piece["time_scale_s"]
                    prediction = (
                        np.polynomial.polynomial.polyval(x, piece["coefficients_hz"])
                        - native[left] * PERIOD
                    )
                    ax.plot(time, prediction / 1000, color=c, linewidth=0.9, alpha=0.95, zorder=4)
        lo = min(r["measured_cfo_hz"] for r in lane_raw) / 1000
        hi = max(r["measured_cfo_hz"] for r in lane_raw) / 1000
        ax.set(
            xlim=(0, 300),
            ylim=(lo - 7, hi + 7),
            ylabel="GLRT CFO (kHz)",
            xlabel="Seconds from scan start",
        )
        label = f"RX{rx}" + (f" CH{channel}" if channel is not None else " · all 8 channels")
        ax.set_title(f"{label} · {len(shown):,} GLRT · {count} polynomial fragments", fontsize=10)
        ax.grid(alpha=0.15)
        return dict(
            receiver=rx,
            channel=channel,
            view=view,
            glrt_points=len(shown),
            polynomial_fragments=count,
            points_without_retained_polynomial=len(loose),
        )

    OUTPUT.mkdir(exist_ok=False)
    summary = []
    labels = {
        "all": "All GLRT + polynomial tracks",
        "associated": "Satellite-associated GLRT + polynomial tracks",
        "unassociated": "Unassociated GLRT + polynomial tracks",
    }
    fig, axes = plt.subplots(3, 2, figsize=(16, 13), layout="constrained")
    for row, view in enumerate(labels):
        for rx in (1, 2):
            summary.append(panel(axes[row, rx - 1], rx, view))
            axes[row, rx - 1].text(
                0.01,
                0.98,
                labels[view],
                transform=axes[row, rx - 1].transAxes,
                va="top",
                fontsize=10,
                bbox=dict(facecolor="white", alpha=0.85, edgecolor="none"),
            )
    handles = [
        Line2D(
            [],
            [],
            marker="o",
            color="#2878b5",
            linewidth=1,
            markersize=4,
            label="GLRT dots + empirical polynomial lines; colour identifies a track",
        ),
        Line2D(
            [],
            [],
            marker="x",
            color="#777777",
            linestyle="none",
            label="GLRT without retained polynomial (includes T009 endpoint)",
        ),
    ]
    fig.legend(handles=handles, loc="outside lower center", ncol=1, fontsize=9)
    fig.suptitle(
        "DSX01 S01 · fitted-c · association at supplied GPS\n"
        "4,797 GLRT total · 2,291 associated (47.76%) · 2,506 unassociated\n"
        "102 associated fragments → 73 merged tracks · 68 unassociated polynomial fragments",
        fontsize=14,
    )
    fig.savefig(OUTPUT / "overview.png", dpi=160)
    plt.close(fig)
    for view, title in labels.items():
        fig, axes = plt.subplots(8, 2, figsize=(16, 23), layout="constrained")
        for ch in range(1, 9):
            for rx in (1, 2):
                summary.append(panel(axes[ch - 1, rx - 1], rx, view, ch))
        fig.suptitle(
            f"DSX01 S01 · {title}\n"
            "Latest fitted-c, curved-only phase calibration; colours preserved across views",
            fontsize=15,
        )
        fig.savefig(OUTPUT / f"{view}_by_channel.png", dpi=145)
        plt.close(fig)
    for rx in (1, 2):
        totals = {
            s["view"]: s["glrt_points"]
            for s in summary
            if s["receiver"] == rx and s["channel"] is None
        }
        assert totals["all"] == totals["associated"] + totals["unassociated"]
        for view in labels:
            assert totals[view] == sum(
                s["glrt_points"]
                for s in summary
                if s["receiver"] == rx and s["view"] == view and s["channel"] is not None
            )
    protocol = dict(
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        input_sha256={
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [RESULT / "association.json", RESULT / "fit.json", PARTITION, RAW]
        },
        arm="fitted_c",
        supplied_position_fixed=True,
        not_a_blind_position_result=True,
        every_raw_glrt_point_shown_exactly_once_per_subset=True,
        raw_frequency_branches_unchanged=True,
        lines_are_empirical_polynomials_not_satellite_predictions=True,
        no_lines_across_alias_changes_or_gaps_over_5s=True,
        color_group="associated merged track, otherwise unassociated polynomial fragment",
        no_refitting_or_new_associations=True,
        raw_points=4797,
        associated_points=2291,
        unassociated_points=2506,
        unassociated_polynomial_points=2195,
        points_without_retained_polynomial=311,
        associated_polynomial_fragments=102,
        associated_merged_tracks=73,
        unassociated_polynomial_fragments=68,
    )
    (OUTPUT / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    (OUTPUT / "panel_counts.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(protocol), flush=True)


if __name__ == "__main__":
    run()
