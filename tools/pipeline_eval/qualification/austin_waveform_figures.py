"""Render ordinary stage gallery cards from the sealed Austin waveform outputs."""

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt

from ..__main__ import save_json, write
from . import austin_waveform as wave

KEY = (
    ("exact", "Exact Qin code", "#146453", "o"),
    ("roll17", "17-symbol cyclic roll", "#9c5629", "s"),
    ("shuffled", "Noncyclic symbol order", "#4a6685", "^"),
)


def table(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def panels(axis, rows, cases):
    by_key = {(r["edge"], r["panel"], int(r["start_ms"]), r["template"]): r for r in rows}
    for shift, (method, label, color, mark) in enumerate(KEY, -1):
        for i, case in enumerate(cases):
            row = by_key[(*case, method)]
            if not row["margin"]:
                continue
            face = "white" if row["matches_relative_phase"] == "False" else color
            axis.scatter(
                i + shift * 0.16,
                float(row["margin"]),
                color=color,
                facecolors=face,
                marker=mark,
                s=55,
                label=label if i == 0 else None,
                zorder=3,
            )
    ticks = [
        f"{e.title()}\n{t} ms" if p != "injected" else f"{e.title()}\nPlant" for e, p, t in cases
    ]
    axis.set_xticks(range(len(ticks)), ticks)
    axis.axhline(0.025, color="#756d69", lw=1, ls="--", label="0.025 margin gate")
    axis.grid(axis="y", alpha=0.26)


def native_chart(out, source):
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.5), width_ratios=(1.4, 1), layout="constrained")
    cases = [(edge, "physical", t) for edge in wave.EDGE_HZ for t in wave.WINDOWS_MS]
    plants = [(edge, "injected", 0) for edge in wave.EDGE_HZ]
    source_rows = table(out / source)
    panels(ax[0], source_rows, cases + plants)
    panels(ax[1], source_rows, [(e, "phase-null", t) for e, _, t in cases])
    ax[0].axvline(5.5, color="#aaa4a0", lw=0.8)
    ax[0].set(
        title="Physical excerpt and planted IF controls",
        ylabel="Best native fractional margin",
        ylim=(-0.035, 1.0),
    )
    ax[1].set(title="Matched spectrum, randomized phase", ylim=(-0.004, 0.029))
    ax[0].legend(loc="center", ncols=2, fontsize=8, frameon=False)
    fig.suptitle("Native Qin search on the independent UT Austin waveform", fontsize=14)
    fig.savefig(out / "native-acquisition.png", dpi=180)
    plt.close(fig)


def conditioned_chart(out, source):
    dataset = table(out / source)
    fig, axes = plt.subplots(1, 2, figsize=(10.7, 4.2), layout="constrained", sharey=True)
    for ax, edge in zip(axes, wave.EDGE_HZ, strict=True):
        for name, label, color, marker in KEY:
            rows = [r for r in dataset if r["edge"] == edge and r["template"] == name]
            ax.plot(
                [int(r["frame"]) for r in rows],
                [float(r["score"]) for r in rows],
                marker=marker,
                color=color,
                label=label,
            )
        ax.set(
            title=f"{edge.title()} edge",
            xlabel="Author frame index",
            yscale="log",
            ylim=(0.00055, 0.32),
        )
        ax.grid(axis="y", alpha=0.26)
    axes[0].set_ylabel("Maximum normalized squared coherence")
    axes[1].legend(loc="center right", frameon=False, fontsize=8)
    fig.suptitle("Code-order check conditioned on the authors’ relative frame marks", fontsize=14)
    fig.savefig(out / "conditioned-frames.png", dpi=180)
    plt.close(fig)


def publish(out):
    wave.stock.sealed(out, "score-lock.json")
    native_source = "native-scores.csv"
    native_chart(out, native_source)
    receipt = wave.stock.digest(out / "score-lock.json")
    descriptor(
        out,
        "austin-native-qin",
        "Native Qin search on the independent UT Austin waveform",
        "One 50 ms single-RX archive · 6 physical edge/windows · 42 matched native calls",
        "250 MS/s public IQ → two 10 MS/s edges → stock wide single-RX detector",
        "Hollow markers miss the reference phase after accounting for any cyclic shift. "
        "The 30 ms windows overlap the 20 ms windows. Same-capture edges share evidence.",
        "native-acquisition.png",
        native_source,
        receipt,
    )
    relative = out / "conditioned"
    relative.mkdir(exist_ok=True)
    leaf = "conditioned-frames.csv"
    write(relative / leaf, (out / leaf).read_bytes())
    conditioned_chart(relative, leaf)
    descriptor(
        relative,
        "austin-conditioned-qin",
        "Qin code order at the authors’ relative frame marks",
        "7 complete frames · 2 subbands from one physical receiver · 3 equal searches",
        "Decimated Austin IQ and authored relative phase → single-frame coherence",
        "The exact and two controls use a shared ±3-sample timing search and CFO bank. "
        "The authored times condition this diagnostic.",
        "conditioned-frames.png",
        leaf,
        receipt,
    )


def descriptor(out, ident, title, sample, boundary, note, image, data, receipt):
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id=ident,
            title=title,
            sample=sample,
            boundary=boundary,
            note=note,
            seal="stage-lock.json",
            image=image,
            csv=data,
        ),
    )
    save_json(
        out / "stage-lock.json",
        dict(
            files={n: wave.stock.digest(out / n) for n in (image, data, "stage-figure.json")},
            parent_score_lock_sha256=receipt,
            generator_sha256=wave.stock.digest(Path(__file__)),
        ),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=wave.REPORT)
    publish(p.parse_args().out)


if __name__ == "__main__":
    main()
