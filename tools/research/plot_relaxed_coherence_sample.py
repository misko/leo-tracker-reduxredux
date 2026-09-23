"""Render the frozen random sample from cached measurements; no fitting."""

import csv
import gzip
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def main():
    out = Path("reports/figures/2026_09_23_relaxed_adaptive_coherence")
    selection = json.loads((out / "random-30-selection.json").read_text())
    selected = set(selection["visit_indices"])
    references = set(selection["reference_visit_indices"])
    rows = sorted(
        (
            r
            for p in (list(out.glob("results-part-*.json")) or [out / "sample-results.json"])
            for r in json.loads(p.read_text())["rows"]
            if r["visit_index"] in selected | references
        ),
        key=lambda r: r["visit_index"],
    )
    (out / "sample-results.json").write_text(
        json.dumps({"selection": selection, "rows": rows}, indent=2) + "\n"
    )
    frames = {}
    paths = sorted(out.glob("frames-part-*.jsonl.gz")) or [out / "sample-frames.jsonl.gz"]
    for path in paths:
        with gzip.open(path, "rt") as source:
            for line in source:
                f = json.loads(line)
                if f["visit_index"] in selected | references:
                    frames[f["visit_index"], f["arm"], f["anchor_index"]] = f
    with gzip.open(out / "sample-frames.jsonl.gz", "wt") as dest:
        for f in frames.values():
            dest.write(json.dumps(f) + "\n")
    table, pairtable = [], []
    for r in rows:
        for s in r["sources"]:
            m = s["metrics"]
            table.append(
                dict(
                    visit=r["visit_index"],
                    reference=r["visit_index"] in references,
                    channel=r["channel"],
                    time_s=r["time_s"],
                    arm=s["arm"],
                    anchor=s["anchor_index"],
                    R120=m["full_120ms"]["weighted_R"],
                    R20=m["median_20ms_R"],
                    complex_coherence=m["full_120ms"]["normalized_complex_coherence"],
                    pilot_support=m["pilot_supported_both_rx"],
                    short_screen=m["screened_short_phase"],
                )
            )
        for p in r["pairs"]:
            pairtable.append(
                dict(
                    visit=r["visit_index"],
                    reference=r["visit_index"] in references,
                    arm=p["arm"],
                    anchors=str(p["anchors"]),
                    R=p["weighted_R"],
                    wrong_time_R=p["wrong_time_control"]["weighted_R"],
                    held_pairs=p["count"],
                    gap_us=p["max_pair_gap_us"],
                    pilot_support=p["both_sources_pilot_supported"],
                    screen=p["screened_DD"],
                )
            )
    for name, data in [("source-metrics.csv", table), ("pair-metrics.csv", pairtable)]:
        with (out / name).open("w") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0]))
            w.writeheader()
            w.writerows(data)
    fig, axs = plt.subplots(1, 2, figsize=(13, 5), constrained_layout=True)
    for arm, color in [(0, "tab:blue"), (1, "tab:orange")]:
        for ref, marker in [(False, "o"), (True, "*")]:
            data = [x for x in table if x["arm"] == arm and x["reference"] == ref]
            axs[0].scatter(
                [x["R120"] for x in data],
                [x["R20"] for x in data],
                c=color,
                marker=marker,
                s=90 if ref else 30,
                alpha=0.75,
                label=f"RX{arm} anchor · " + ("reference five" if ref else "random 30"),
            )
            data = [x for x in pairtable if x["arm"] == arm and x["reference"] == ref]
            axs[1].scatter(
                [x["wrong_time_R"] for x in data],
                [x["R"] for x in data],
                c=color,
                marker=marker,
                s=90 if ref else 45,
            )
            for x in data:
                if not ref and x["screen"]:
                    axs[1].annotate(str(x["visit"]), (x["wrong_time_R"], x["R"]), fontsize=8)
    axs[0].set(
        xlabel="Single-source held R · full 120 ms",
        ylabel="Median single-source held R · 20 ms blocks",
        title="All anchors retained; independent random held frames",
    )
    axs[1].set(
        xlabel="Two-source wrong-time control R",
        ylabel="Two-source simultaneous held R",
        title="Before separate source-rate removal",
    )
    axs[0].legend(fontsize=8)
    for ax in axs:
        ax.plot([0, 1], [0, 1], ":", color=".6")
        ax.set(xlim=(0, 1.03), ylim=(0, 1.03))
        ax.grid(alpha=0.2)
    fig.suptitle("Frozen random 30 adaptive dwells compared with the original five")
    fig.savefig(out / "random30-coherence.png", dpi=160)
    plt.close(fig)
    fig, axs = plt.subplots(
        6, 5, figsize=(19, 17), sharex=True, sharey=True, constrained_layout=True
    )
    for ax, r in zip(axs.flat, [r for r in rows if r["visit_index"] in selected], strict=True):
        for arm, color in [(0, "tab:blue"), (1, "tab:orange")]:
            s = next(s for s in r["sources"] if s["arm"] == arm and s["anchor_index"] == 0)
            f = frames[r["visit_index"], arm, 0]
            t = np.asarray(f["times"])
            held = ~np.asarray(f["train"])
            z = np.asarray(f["product_real"]) + 1j * np.asarray(f["product_imag"])
            phase = np.angle(
                z * np.exp(-2j * np.pi * s["metrics"]["full_120ms"]["rate_hz"] * (t - 0.06))
            )
            ax.scatter(t[held] * 1000, np.degrees(phase[held]), s=10, c=color, alpha=0.7)
        ax.set_title(f"{r['visit_index']} · CH{r['channel']} · {r['time_s']:.1f} s", fontsize=10)
        ax.set(xlim=(0, 120), ylim=(-180, 180), yticks=[-180, 0, 180])
        ax.grid(alpha=0.2)
    fig.suptitle(
        "Random 30: single-source RX1−RX0 phase, primary metadata-ranked anchor only\n"
        "Blue: RX0 anchor; orange: RX1 anchor · held frames · "
        "saved train-only 120 ms rate removed; no new fit"
    )
    fig.supxlabel("Time within dwell (ms)")
    fig.supylabel("Wrapped receiver phase (degrees; conditional phase origin)")
    fig.savefig(out / "random30-phase-gallery.png", dpi=140)
    plt.close(fig)
    pairs = [(r, p) for r in rows if r["visit_index"] in selected for p in r["pairs"]]
    fig, axs = plt.subplots(
        4, 3, figsize=(15, 13), sharex=True, sharey=True, constrained_layout=True
    )
    for ax, (r, p) in zip(axs.flat, pairs, strict=True):
        a, b = [frames[r["visit_index"], p["arm"], i] for i in p["anchors"]]
        ta, tb = np.asarray(a["times"]), np.asarray(b["times"])
        j = np.argmin(abs(ta[:, None] - tb[None, :]), axis=1)
        keep = abs(ta - tb[j]) < 1 / 1500
        held = ~np.asarray(a["train"]) & ~np.asarray(b["train"])[j]
        za = np.asarray(a["product_real"]) + 1j * np.asarray(a["product_imag"])
        zb = np.asarray(b["product_real"]) + 1j * np.asarray(b["product_imag"])
        phase = np.degrees(np.angle(zb[j] * np.conj(za)))
        ax.scatter(
            ta[keep & ~held] * 1000, phase[keep & ~held], s=16, facecolors="none", edgecolors=".6"
        )
        ax.scatter(
            ta[keep & held] * 1000,
            phase[keep & held],
            s=18,
            c="tab:blue" if p["arm"] == 0 else "tab:orange",
        )
        ax.set_title(
            f"{r['visit_index']} · RX{p['arm']} anchor · R={p['weighted_R']:.2f}\n"
            f"wrong-time={p['wrong_time_control']['weighted_R']:.2f}; "
            f"pilot support={p['both_sources_pilot_supported']}",
            fontsize=10,
        )
        ax.set(xlim=(0, 120), ylim=(-180, 180), yticks=[-180, 0, 180])
        ax.grid(alpha=0.2)
    fig.suptitle(
        "All 12 candidate pairs in the random 30 · no separate source-rate removal\n"
        "Filled: both frames held; hollow: includes training · no new fit or phase centering"
    )
    fig.supxlabel("Time within dwell (ms)")
    fig.supylabel("Wrapped source B−A receiver-phase difference (degrees)")
    fig.savefig(out / "random30-double-difference.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
