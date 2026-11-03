"""Plot frozen server curves and independently produced ARM track hypotheses."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "evaluation"))
from compare_tracks import read_observations, read_tracks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tracks", type=Path, required=True)
    parser.add_argument("--observations", type=Path,
                        default=HERE / "server-baseline/output/arm-observations.tsv")
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fit-only", action="store_true",
                        help="Draw linear fitted models instead of measured track points")
    args = parser.parse_args()
    baseline = HERE / "server-baseline/output"
    server_obs = read_observations(baseline / "server-observations.tsv")
    arm_obs = read_observations(args.observations)
    server = read_tracks(baseline / "server-tracks.tsv", server_obs).tracks
    arm = read_tracks(args.tracks, arm_obs).tracks
    origin = min(o.start_ns for o in server_obs.values())
    fig, axes = plt.subplots(4, 2, figsize=(15, 12), sharex=True, sharey=True,
                             layout="constrained")
    for channel in range(1, 5):
        for rx in (0, 1):
            ax = axes[channel-1, rx]
            for tracks, color, label, style in [(server, "#222222", "Server reference", "--"),
                                               (arm, "#CA7025", args.label, "-")]:
                first = True
                for track in tracks:
                    if (track.lane.receiver_id, track.lane.channel) != (rx, channel):
                        continue
                    spacing = 11200000000 / track.lane.actual_rf_hz / 4.4e-6
                    if args.fit_only:
                        times = np.linspace((track.start_ns-origin)*1e-9,
                                            (track.end_ns-origin)*1e-9, 200)
                        values = (track.intercept + track.rate *
                                  (times + (origin-track.reference_ns)*1e-9))
                    else:
                        observations = server_obs if tracks is server else arm_obs
                        measured = sorted(((observations[point.candidate_id].center_ns-origin)*1e-9,
                                           point.normalized_dealiased_cfo_hz)
                                          for point in track.points)
                        times = np.array([p[0] for p in measured])
                        values = np.array([p[1] for p in measured])
                    values = ((values+spacing/2) % spacing-spacing/2) / 1000
                    jumps = np.where(np.abs(np.diff(values)) > spacing/2000)[0] + 1
                    values[jumps] = np.nan
                    ax.plot(times, values, color=color, linestyle=style,
                            marker=None if args.fit_only else ".", markersize=2.5,
                            linewidth=1.0, alpha=.8, label=label if first else None)
                    first = False
            ax.set_title(f"Channel {channel} · RX{rx}")
            ax.grid(alpha=.2)
            ax.set_xlim(0, 300)
            if rx == 0:
                ax.set_ylabel("Normalized CFO, alias-folded (kHz)")
    axes[0, 0].legend(loc="upper right", fontsize=8)
    for ax in axes[-1]:
        ax.set_xlabel("Seconds from first projected observation")
    subtitle = ("Linear fit models, not individual measurements" if args.fit_only else
                "Measured GLRT CFO points assigned to tracks, joined in time")
    fig.suptitle("Full saved scan: server and ARM-derived tracks\n" + subtitle +
                 "; alias-wrap discontinuities are omitted.", fontsize=12)
    fig.savefig(args.output, dpi=180, bbox_inches="tight")
    fig.savefig(args.output.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
