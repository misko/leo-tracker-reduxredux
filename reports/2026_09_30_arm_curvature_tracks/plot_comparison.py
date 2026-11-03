"""Measured-point views of frozen server and physically executed ARM results."""
import hashlib
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "2026_09_30_arm_fast_tracks/server-baseline/output"
sys.path.insert(0, str(BASE.parent.parent / "evaluation"))
from compare_tracks import read_observations, read_tracks


def main():
    paths = [BASE / "server-observations.tsv", BASE / "server-tracks.tsv",
             BASE / "arm-observations.tsv", HERE / "physical-arm-a250.tsv"]
    observations = [read_observations(paths[0]), read_observations(paths[2])]
    tracks = [read_tracks(paths[1], observations[0]).tracks,
              read_tracks(paths[3], observations[1]).tracks]
    assert len(tracks[0]) == 63 and len(tracks[1]) == 55
    origin = min(o.start_ns for o in observations[0].values())
    out = HERE / "plots"
    out.mkdir(exist_ok=True)
    labels = ["Server: 63 segments", "ARM curvature prototype: 55 hypotheses"]
    colors = ["#1764a0", "#d76a10"]

    def draw(ax, lane, sides):
        for side in sides:
            selected = [t for t in tracks[side]
                        if (t.lane.channel, t.lane.receiver_id) == lane]
            for index, track in enumerate(selected):
                points = sorted(((observations[side][p.candidate_id].center_ns-origin)*1e-9,
                                 p.normalized_dealiased_cfo_hz) for p in track.points)
                times, values = np.array(points).T
                spacing = 11.2e9 / track.lane.actual_rf_hz / 4.4e-6
                values = ((values + spacing/2) % spacing - spacing/2) / 1000
                # Split lines without dropping the observations at alias boundaries.
                cuts = np.flatnonzero((np.abs(np.diff(values)) > spacing/2000)
                                      | (np.diff(times) > 4.0)) + 1
                for inds in np.split(np.arange(len(times)), cuts):
                    ax.plot(times[inds], values[inds], color=colors[side], lw=.75,
                            alpha=.65, linestyle="--" if side == 0 else "-")
                ax.scatter(times, values, s=3, color=colors[side], alpha=.7,
                           label=labels[side] if index == 0 else None)
        ax.set(xlim=(0, 300), ylim=(-130, 130),
               title=f"Channel {lane[0]} · RX{lane[1]}",
               ylabel="Normalized CFO (kHz)")
        ax.grid(alpha=.2)

    for name, sides in [("server", [0]), ("arm", [1]), ("overlay", [0, 1])]:
        fig, axes = plt.subplots(4, 2, figsize=(16, 12), sharex=True, sharey=True,
                                 layout="constrained")
        for channel in range(1, 5):
            for rx in (0, 1):
                draw(axes[channel-1, rx], (channel, rx), sides)
        axes[0, 0].legend(loc="upper right", fontsize=8)
        for ax in axes[-1]:
            ax.set_xlabel("Seconds from first projected observation")
        fig.suptitle("300-second DS9 scan · " + " vs ".join(labels[s] for s in sides)
                     + "\nMeasured CFO points joined within tracks; alias-folded at 11.2 GHz; no fitted straight lines.")
        fig.savefig(out / f"{name}.png", dpi=160)
        fig.savefig(out / f"{name}.pdf")
        plt.close(fig)

    fig, axes = plt.subplots(8, 2, figsize=(16, 23), sharex=True, sharey=True,
                             layout="constrained")
    for row, lane in enumerate((ch, rx) for ch in range(1, 5) for rx in (0, 1)):
        for side in (0, 1):
            draw(axes[row, side], lane, [side])
            axes[row, side].set_title(f"{labels[side]} · Channel {lane[0]} · RX{lane[1]}")
    for ax in axes[-1]:
        ax.set_xlabel("Seconds from first projected observation")
    fig.suptitle("Server versus physical ARM output · same 300-second recording\n"
                 "Actual assigned GLRT CFO measurements; each side uses its own detections.")
    fig.savefig(out / "side-by-side.png", dpi=150)
    fig.savefig(out / "side-by-side.pdf")
    plt.close(fig)
    receipt = {"scan": "scan-fw-f363c7f29141d0b1", "counts": [len(t) for t in tracks],
               "inputs": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
               "arm_execution": "Physical PLUTO+; frozen curvature v8, acceleration bound 250 Hz/s^2",
               "display": "Measured points, common time/frequency axes, alias folded; connections break at alias wrap or gaps above four seconds."}
    (out / "provenance.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
