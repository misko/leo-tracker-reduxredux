"""Create protocol-aware 10 MS/s versus 2.5 MS/s TLE comparison figures."""

import argparse
import gzip
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np


def distribution(values):
    data = np.asarray(list(values), dtype=float)
    if data.size == 0 or not np.all(np.isfinite(data)):
        raise ValueError("comparison distribution must be finite and non-empty")
    q1, median, q3 = np.percentile(data, [25, 50, 75])
    return {
        "count": int(data.size),
        "minimum": float(np.min(data)),
        "q1": float(q1),
        "median": float(median),
        "q3": float(q3),
        "maximum": float(np.max(data)),
    }


def load_10msps(root):
    records = sorted(
        (
            json.loads(gzip.decompress(path.read_bytes()))
            for path in root.glob("scan-hop-*.json.gz")
        ),
        key=lambda record: record["capture_start_utc"],
    )
    tracks = [track for record in records for track in record["screen"]["tracks"]]
    if len(records) != 47 or len(tracks) != 647:
        raise ValueError("unexpected 10 MS/s cohort")
    training = []
    heldout = []
    gaps = []
    candidate_counts = []
    concerns = Counter()
    session_rows = []
    for record in records:
        session_tracks = record["screen"]["tracks"]
        session_heldout = []
        session_passes = 0
        session_rank1 = 0
        for track in session_tracks:
            top = track["fields"]["0"]["top_training"]
            leader = top[0]
            training.append(leader["training_rms_hz"])
            heldout.append(leader["heldout_rms_hz"])
            gaps.append(top[1]["training_rms_hz"] - leader["training_rms_hz"])
            candidate_counts.append(track["fields"]["0"]["candidate_count"])
            session_heldout.append(leader["heldout_rms_hz"])
            issues = track["publication_concerns"]
            concerns.update(issues)
            session_passes += not issues
            session_rank1 += track["fields"]["0"]["winner_heldout_rank"] == 1
        session_rows.append(
            {
                "session_id": record["session_id"],
                "capture_start_utc": record["capture_start_utc"],
                "track_count": len(session_tracks),
                "pass_count": session_passes,
                "rank1_fraction": session_rank1 / len(session_tracks),
                "median_heldout_rms_hz": float(np.median(session_heldout)),
                "q1_heldout_rms_hz": float(np.percentile(session_heldout, 25)),
                "q3_heldout_rms_hz": float(np.percentile(session_heldout, 75)),
            }
        )
    return {
        "recording_count": len(records),
        "track_count": len(tracks),
        "training_rms_hz": distribution(training),
        "heldout_rms_hz": distribution(heldout),
        "training_winner_gap_hz": distribution(gaps),
        "candidate_count": distribution(candidate_counts),
        "median_track_span_s": float(np.median([track["span_s"] for track in tracks])),
        "heldout_rank1_count": len(tracks) - concerns["leader changes on heldout"],
        "protocol_pass_count": sum(not track["publication_concerns"] for track in tracks),
        "radio_null_beaten_count": len(tracks) - concerns["radio drift fits as well or better"],
        "concerns": dict(concerns),
        "session_rows": session_rows,
    }


def load_2p5msps(path):
    episodes = json.loads(path.read_text())["single_channel_results"]
    if len(episodes) != 24:
        raise ValueError("unexpected 2.5 MS/s comparison cohort")
    return {
        "recording_count": 1,
        "track_count": len(episodes),
        "training_rms_hz": distribution(
            episode["training_winner"]["training_rms_hz"] for episode in episodes
        ),
        "heldout_rms_hz": distribution(
            episode["training_winner"]["heldout_rms_hz"] for episode in episodes
        ),
        "training_winner_gap_hz": distribution(
            episode["training_runner"]["winner_to_runner_rms_gap_hz"] for episode in episodes
        ),
        "candidate_count": distribution(
            episode["eligible_causal_tle_count"] for episode in episodes
        ),
        "median_track_span_s": float(np.median([episode["duration_s"] for episode in episodes])),
        "heldout_rank1_count": sum(
            episode["training_winner"]["heldout_rank"] == 1 for episode in episodes
        ),
        "protocol_pass_count": sum(episode["screen_passes"] for episode in episodes),
        "radio_null_beaten_count": sum(
            episode["tle_beats_cubic_radio_null_on_heldout"] for episode in episodes
        ),
    }


def median_iqr(ax, positions, stats, labels, title):
    for x, item, color in zip(positions, stats, ["#2166ac", "#d95f02"], strict=True):
        ax.errorbar(
            x,
            item["median"],
            yerr=[[item["median"] - item["q1"]], [item["q3"] - item["median"]]],
            fmt="o",
            color=color,
            capsize=6,
            markersize=8,
        )
    ax.set_xticks(positions, labels)
    ax.set_yscale("log")
    ax.set_ylabel("Hz, median and IQR (log scale)")
    ax.set_title(title, loc="left")
    ax.grid(axis="y", alpha=0.2)
    ax.spines[["top", "right"]].set_visible(False)


def render_comparison(ten, narrow, output):
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    median_iqr(
        axes[0, 0],
        [1, 2],
        [ten["training_rms_hz"], narrow["training_rms_hz"]],
        ["10 MS/s\n647 tracklets", "2.5 MS/s\n24 episodes"],
        "Training RMS of catalogue leader",
    )
    median_iqr(
        axes[0, 1],
        [1, 2],
        [ten["heldout_rms_hz"], narrow["heldout_rms_hz"]],
        ["10 MS/s\n647 tracklets", "2.5 MS/s\n24 episodes"],
        "Held-out RMS of training-selected leader",
    )
    median_iqr(
        axes[1, 0],
        [1, 2],
        [ten["training_winner_gap_hz"], narrow["training_winner_gap_hz"]],
        ["10 MS/s", "2.5 MS/s"],
        "Training winner-to-runner RMS gap",
    )
    labels = [
        "Leader remains\nheld-out rank 1",
        "Protocol-specific\nscreen pass",
        "TLE beats stated\nradio null",
    ]
    x = np.arange(len(labels))
    width = 0.36
    ten_rates = [
        ten["heldout_rank1_count"] / ten["track_count"],
        ten["protocol_pass_count"] / ten["track_count"],
        ten["radio_null_beaten_count"] / ten["track_count"],
    ]
    narrow_rates = [
        narrow["heldout_rank1_count"] / narrow["track_count"],
        narrow["protocol_pass_count"] / narrow["track_count"],
        narrow["radio_null_beaten_count"] / narrow["track_count"],
    ]
    axes[1, 1].bar(x - width / 2, ten_rates, width, label="10 MS/s", color="#2166ac")
    axes[1, 1].bar(x + width / 2, narrow_rates, width, label="2.5 MS/s", color="#d95f02")
    axes[1, 1].set_xticks(x, labels)
    axes[1, 1].set_ylim(0, 1.08)
    axes[1, 1].set_ylabel("Fraction of tracks/episodes")
    axes[1, 1].set_title("Within-protocol exploratory outcomes", loc="left")
    axes[1, 1].legend()
    axes[1, 1].grid(axis="y", alpha=0.2)
    axes[1, 1].spines[["top", "right"]].set_visible(False)
    for container in axes[1, 1].containers:
        axes[1, 1].bar_label(
            container, labels=[f"{100 * value:.1f}%" for value in container.datavalues], padding=2
        )
    fig.suptitle(
        "10 MS/s RX0 cohort versus the 2.5 MS/s scan\n"
        "Different receivers, track consolidation, and gates: descriptive comparison only"
    )
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(output / "10msps-vs-2p5msps-tle-comparison.png", dpi=140)
    plt.close(fig)


def render_sessions(ten, output):
    rows = ten["session_rows"]
    times = [
        datetime.fromisoformat(row["capture_start_utc"].replace("Z", "+00:00")) for row in rows
    ]
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
    axes[0].plot(times, [row["track_count"] for row in rows], "o-", label="Eligible tracks")
    axes[0].plot(times, [row["pass_count"] for row in rows], "o-", label="Descriptive passes")
    axes[0].set_ylabel("Tracklets")
    axes[0].legend()
    held = np.asarray([row["median_heldout_rms_hz"] for row in rows])
    low = np.asarray([row["q1_heldout_rms_hz"] for row in rows])
    high = np.asarray([row["q3_heldout_rms_hz"] for row in rows])
    axes[1].plot(times, held, "o-", color="#7b3294", label="Session median")
    axes[1].fill_between(times, low, high, color="#c2a5cf", alpha=0.45, label="Track IQR")
    axes[1].set_yscale("log")
    axes[1].set_ylabel("Leader held-out RMS (Hz)")
    axes[1].legend()
    axes[2].plot(times, [row["rank1_fraction"] for row in rows], "o-", color="#008837")
    axes[2].set_ylim(0, 1.05)
    axes[2].set_ylabel("Held-out rank-1 fraction")
    axes[2].set_xlabel("UTC on September 14, 2026")
    axes[2].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    for ax in axes:
        ax.grid(alpha=0.2)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("RX0 10 MS/s catalogue-screen stability by 300-second recording")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(output / "10msps-session-association-summary.png", dpi=140)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ten-msps", type=Path, required=True)
    parser.add_argument("--two-point-five-msps", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output == Path("/mnt/qnap01") or Path("/mnt/qnap01") in output.parents:
        parser.error("QNAP is read-only")
    output.mkdir(parents=True, exist_ok=True)
    ten = load_10msps(args.ten_msps)
    narrow = load_2p5msps(args.two_point_five_msps)
    render_comparison(ten, narrow, output)
    render_sessions(ten, output)
    (output / "summary.json").write_text(
        json.dumps({"ten_msps": ten, "two_point_five_msps": narrow}, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "ten_msps_tracks": ten["track_count"],
                "two_point_five_msps_episodes": narrow["track_count"],
            }
        )
    )


if __name__ == "__main__":
    main()
