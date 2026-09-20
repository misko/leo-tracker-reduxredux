"""Plot randomized evaluation RMS of fit-ranked TLE leaders from current products."""

import argparse
import csv
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.scanner_tracking import ScannerTrackingStore


def pair(review):
    candidates = sorted(review["candidates"], key=lambda c: c["rank"])
    if len(candidates) < 2:
        return None
    # Freeze fit ranks: never reselect the winner using evaluation data.
    best, runner = candidates[:2]
    return dict(
        best_norad=best["catalog_number"],
        runner_norad=runner["catalog_number"],
        best_rms_hz=best["randomized_evaluation_rms_hz"],
        runner_rms_hz=runner["randomized_evaluation_rms_hz"],
    )


def collect(root, end_ns):
    captures = AdaptiveHopIqStore(root, read_only=True)
    tracking = ScannerTrackingStore(root, read_only=True)
    records = []
    try:
        for published_ns, sid in captures.publication_index():
            if end_ns - 86_400_000_000_000 <= published_ns < end_ns:
                status = tracking.analysis_status(sid)
                records.append(
                    dict(
                        session_id=sid,
                        published_ns=published_ns,
                        status=status.model_dump(mode="json"),
                    )
                )
    finally:
        captures.close()
    return dict(start_ns=end_ns - 86_400_000_000_000, end_ns=end_ns, sessions=records)


def render(snapshot, output):
    rows = []
    for record in snapshot["sessions"]:
        status = record["status"]
        if status["state"] != "complete":
            continue
        product = status["product"]
        if product["tle_residual_partition_policy"] != "deterministic-randomized-observation-v1":
            raise ValueError("non-randomized product in cohort")
        for review in product["track_reviews"]:
            values = pair(review)
            if values is not None:
                rows.append(
                    dict(
                        session_id=record["session_id"],
                        published_ns=record["published_ns"],
                        rate_msps=product["sample_rate_hz"] / 1e6,
                        tracklet_id=review["tracklet_id"],
                        channel=review["channel"],
                        edge=review["edge"],
                        observations=review["observation_count"],
                        evaluation_observations=review["randomized_evaluation_observation_count"],
                        span_s=review["end_s"] - review["start_s"],
                        **values,
                    )
                )
    with (output / "tracks.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    summary = dict(
        window_start=datetime.fromtimestamp(snapshot["start_ns"] / 1e9, UTC).isoformat(),
        window_end=datetime.fromtimestamp(snapshot["end_ns"] / 1e9, UTC).isoformat(),
        sessions=len(snapshot["sessions"]),
        states=dict(Counter(s["status"]["state"] for s in snapshot["sessions"])),
        paired_tracks=len(rows),
        by_rate=[],
    )
    fig, axes = plt.subplots(3, 1, figsize=(15, 11), sharex=True, sharey=True)
    fig2, axes2 = plt.subplots(1, 3, figsize=(16, 5), sharey=True)
    for axis, comparison, rate in zip(axes, axes2, (10, 15, 20), strict=True):
        group = sorted([r for r in rows if r["rate_msps"] == rate], key=lambda r: r["published_ns"])
        best = np.array([r["best_rms_hz"] for r in group])
        runner = np.array([r["runner_rms_hz"] for r in group])
        times = [datetime.fromtimestamp(r["published_ns"] / 1e9, UTC) for r in group]
        axis.vlines(times, best, runner, color="#b5b5b5", linewidth=0.5, alpha=0.35)
        axis.scatter(times, runner, s=13, color="#d95f02", alpha=0.6, label="Fit rank #2")
        axis.scatter(times, best, s=12, color="#2166ac", alpha=0.8, label="Fit rank #1")
        axis.set_title(
            f"{rate} MS/s · {len(group)} tracks · rank #1 wins {sum(best < runner)}/{len(group)}"
        )
        axis.set_ylabel("Randomized held-out RMS (Hz)")
        axis.set_ylim(bottom=0)
        axis.grid(alpha=0.2)
        axis.legend(loc="upper right")
        for values, color, label in (
            (best, "#2166ac", "Fit rank #1"),
            (runner, "#d95f02", "Fit rank #2"),
        ):
            comparison.plot(
                np.sort(values),
                np.arange(1, len(values) + 1) / len(values) * 100,
                color=color,
                label=label,
            )
        comparison.set_title(f"{rate} MS/s")
        comparison.set_xlabel("Randomized held-out RMS (Hz; linear)")
        comparison.grid(alpha=0.2)
        comparison.legend()
        summary["by_rate"].append(
            dict(
                rate_msps=rate,
                tracks=len(group),
                best_wins=int(sum(best < runner)),
                median_best_hz=float(np.median(best)),
                median_runner_hz=float(np.median(runner)),
                median_ratio=float(np.median(runner / best)),
            )
        )
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M", tz=UTC))
    axes[-1].set_xlim(
        datetime.fromtimestamp(snapshot["start_ns"] / 1e9, UTC),
        datetime.fromtimestamp(snapshot["end_ns"] / 1e9, UTC),
    )
    axes[-1].set_xlabel("Session publication time (UTC) · multiple tracks share each timestamp")
    fig.suptitle(
        "Best versus next-best TLE: randomized held-out residual RMS\n"
        "Candidates ranked on fitting observations; evaluation does not refit or reselect"
    )
    fig.tight_layout()
    fig.savefig(output / "heldout-rms-timeline.png", dpi=160)
    axes2[0].set_ylabel("Tracks at or below this RMS (%)")
    fig2.suptitle("Residual distributions · same tracks and randomized evaluation samples")
    fig2.tight_layout()
    fig2.savefig(output / "heldout-rms-distribution.png", dpi=160)
    plt.close("all")
    (output / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--until", required=True, help="ISO UTC end timestamp")
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    end_ns = round(datetime.fromisoformat(args.until).timestamp() * 1e9)
    snapshot = collect(args.bulk_root, end_ns)
    (args.output / "snapshot.json").write_text(json.dumps(snapshot))
    render(snapshot, args.output)
