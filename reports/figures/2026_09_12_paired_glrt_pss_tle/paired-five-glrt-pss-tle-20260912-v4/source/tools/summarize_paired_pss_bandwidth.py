"""Summarize frozen paired PSS replay, including ambiguous and absent tracks."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

LANES = ("native25", "derived2p5", "recorded2p5")
LABELS = ("25 MS/s recorded", "2.5 MS/s from same ADC", "2.5 MS/s separate radio")
COLORS = ("#157f91", "#c76524", "#7d58a0")


def timing_diagnostics(modes: list[dict], rate: float) -> dict:
    """All local peaks; no rejection based on residual or strong-peak gate."""
    ws = [w for m in modes for w in m["windows"]]
    if len(ws) < 8:
        return {}
    times = np.array([w["fractional_global_device_sample"] / rate for w in ws])
    order = np.argsort(times)
    times = times[order]
    phase = np.array([w["frame_phase_samples"] / rate for w in ws])[order]
    phase = np.unwrap(phase * 750 * 2 * np.pi) / (750 * 2 * np.pi)
    x = times - np.mean(times)
    training = np.arange(len(x)) % 2 == 0
    coef = np.polyfit(x[training], phase[training], 2)
    residual = phase - np.polyval(coef, x)
    held = residual[~training]
    return dict(
        frame_count=len(ws),
        strong_fraction=sum(w["peak_to_local_median"] >= 5 for w in ws) / len(ws),
        median_local_peak_ratio=float(np.median([w["peak_to_local_median"] for w in ws])),
        heldout_rms_ns=float(np.sqrt(np.mean(held**2)) * 1e9),
        heldout_mad_ns=float(np.median(abs(held - np.median(held))) * 1.4826e9),
        apparent_stretch_ppm=float(coef[1] * 1e6),
        apparent_stretch_rate_ppm_s=float(2 * coef[0] * 1e6),
        time_s=times.tolist(),
        phase_s=phase.tolist(),
        residual_s=residual.tolist(),
    )


def summarize(out: Path, baseline: Path | None = None) -> None:
    selected = json.loads((out / "selection.json").read_text())["selected"]
    fig, axes = plt.subplots(5, 3, figsize=(15, 15), constrained_layout=True)
    records = []
    for row, c in enumerate(selected):
        folder = out / c["capture_id"]
        tracks = json.loads((folder / "tracks.json").read_text())
        for col, lane in enumerate(LANES):
            docs = [json.loads(p.read_text()) for p in sorted(folder.glob(f"{lane}-*.json"))]
            all_modes = [m for d in docs for m in d["result"]["modes"]]
            by_id = {m["mode_id"]: m for m in all_modes}
            available = tracks.get(lane, [])
            # Report most-supported track, breaking ties by template strength.
            ranked = sorted(
                available,
                key=lambda t: (
                    len(t["mode_ids"]),
                    np.median([by_id[i]["candidate"]["robust_z"] for i in t["mode_ids"]]),
                ),
                reverse=True,
            )
            chosen = [by_id[i] for i in ranked[0]["mode_ids"]] if ranked else []
            rate = docs[0]["projection"]["output_sample_rate_hz"]
            diag = timing_diagnostics(chosen, rate)
            rec = dict(
                capture_id=c["capture_id"],
                lane=lane,
                independent_track_count=len(available),
                searched_blocks=len(docs),
                blocks_with_qualified_modes=sum(bool(d["result"]["modes"]) for d in docs),
                selected_track=ranked[0] if ranked else None,
                selected_mode_ids=[m["mode_id"] for m in chosen],
                median_epoch_z=float(np.median([m["candidate"]["robust_z"] for m in chosen]))
                if chosen
                else None,
                median_epoch_peak_ratio=float(
                    np.median([m["candidate"]["peak_to_median"] for m in chosen])
                )
                if chosen
                else None,
                **diag,
            )
            records.append(rec)
            ax = axes[row, col]
            if diag:
                t = np.array(diag["time_s"])
                phase = np.array(diag["phase_s"])
                ax.scatter(
                    t - t.min(),
                    (phase - np.median(phase)) * 1e6,
                    s=2,
                    alpha=0.35,
                    color=COLORS[col],
                    rasterized=True,
                )
                ax.set_title(
                    f"{len(chosen)}/9 blocks; strong frames {diag['strong_fraction']:.0%}\n"
                    f"alternate-frame RMS {diag['heldout_rms_ns']:.0f} ns",
                    fontsize=10,
                )
            else:
                ax.text(0.5, 0.5, "No associated PSS track", ha="center", transform=ax.transAxes)
            ax.grid(alpha=0.2)
            if col == 0:
                ax.set_ylabel(
                    f"{c['capture_id'][4:19]}\n{c['capture_id'][-6:]} · phase − median (µs)"
                )
            if row == 4:
                ax.set_xlabel(f"{LABELS[col]}\nseconds into selected interval")
    fig.suptitle(
        "PSS timing in five dwells selected by strong GLRT at both rates\n"
        "Independent CFO/timing search; all local peaks in the selected candidate track are shown",
        fontsize=14,
    )
    fig.savefig(out / "pss-timing-comparison.png", dpi=150)
    plt.close(fig)
    (out / "summary.json").write_text(json.dumps(records, indent=2, allow_nan=False) + "\n")
    fields = [
        "capture_id",
        "lane",
        "independent_track_count",
        "blocks_with_qualified_modes",
        "median_epoch_z",
        "median_epoch_peak_ratio",
        "frame_count",
        "strong_fraction",
        "median_local_peak_ratio",
        "heldout_rms_ns",
        "heldout_mad_ns",
        "apparent_stretch_ppm",
        "apparent_stretch_rate_ppm_s",
    ]
    with (out / "summary.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    for r in records:
        print({k: r.get(k) for k in fields})

    compact, panels = plt.subplots(1, 2, figsize=(12, 4), constrained_layout=True)
    positions = np.arange(len(selected))
    for col, lane in enumerate(LANES):
        subset = [r for r in records if r["lane"] == lane]
        x = positions + (col - 1) * 0.25
        panels[0].bar(
            x,
            [r.get("heldout_rms_ns", np.nan) for r in subset],
            width=0.23,
            label=LABELS[col],
            color=COLORS[col],
        )
        panels[1].bar(
            x,
            [100 * r.get("strong_fraction", np.nan) for r in subset],
            width=0.23,
            color=COLORS[col],
        )
    for panel in panels:
        panel.set_xticks(positions, [c["capture_id"][-6:] for c in selected])
        panel.set_xlabel("Dwell ID suffix")
        panel.grid(axis="y", alpha=0.2)
        panel.set_axisbelow(True)
    panels[0].set_ylabel("Alternate-frame timing residual RMS (ns)")
    panels[1].set_ylabel("Frames with local peak / median ≥ 5 (%)")
    panels[0].legend(fontsize=8)
    compact.suptitle("Five GLRT-strong paired dwells: wider bandwidth improves PSS tracking")
    compact.savefig(out / "pss-bandwidth-summary.png", dpi=150)
    plt.close(compact)

    if baseline is not None:
        previous = json.loads((baseline / "summary.json").read_text())
        compare, panels = plt.subplots(5, 2, figsize=(12, 14), constrained_layout=True)
        changes = []
        for row, c in enumerate(selected):
            before = next(
                r
                for r in previous
                if r["capture_id"] == c["capture_id"] and r["lane"] == "native25"
            )
            after = next(
                r for r in records if r["capture_id"] == c["capture_id"] and r["lane"] == "native25"
            )
            changes.append(
                dict(
                    capture_id=c["capture_id"],
                    before_rms_ns=before.get("heldout_rms_ns"),
                    after_rms_ns=after.get("heldout_rms_ns"),
                )
            )
            phases = []
            for col, (label, record) in enumerate(
                (("Integer-first selection", before), ("Fractional selection", after))
            ):
                ax = panels[row, col]
                if "phase_s" not in record:
                    ax.text(0.5, 0.5, "No associated track", transform=ax.transAxes, ha="center")
                    continue
                phase = np.array(record["phase_s"])
                phase = (phase - np.median(phase)) * 1e6
                phases.extend(phase.tolist())
                t = np.array(record["time_s"])
                ax.scatter(
                    t - t.min(), phase, s=3, alpha=0.4, color="#8c6a58" if col == 0 else COLORS[0]
                )
                ax.set_title(f"{label}: {record['heldout_rms_ns']:.1f} ns RMS")
                ax.grid(alpha=0.2)
                if col == 0:
                    ax.set_ylabel(f"{c['capture_id'][-6:]}\nframe phase − median (µs)")
                if row == 4:
                    ax.set_xlabel("Seconds into selected interval")
            if phases:
                bottom, top = min(phases), max(phases)
                guard = max(0.2, (top - bottom) * 0.05)
                for ax in panels[row]:
                    ax.set_ylim(bottom - guard, top + guard)
        compare.suptitle(
            "25 MS/s PSS before and after fractional peak selection\n"
            "Same five intervals; all selected-track frame estimates retained"
        )
        compare.savefig(out / "pss-fractional-before-after.png", dpi=150)
        plt.close(compare)
        (out / "before-after.json").write_text(json.dumps(changes, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()
    summarize(args.output, args.baseline)
