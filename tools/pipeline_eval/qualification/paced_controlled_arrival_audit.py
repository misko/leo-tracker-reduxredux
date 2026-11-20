"""Separate measured input-read lateness from post-read arrival release delay."""

from pathlib import Path

from ..__main__ import save_json
from . import equal_pace as previous
from . import paced_controlled as trial
from .arrival_queue import readgz
from .arrival_queue_results import timing_ms
from .fresh_replay_results import sealed
from .full_v5_check import _sha
from .paced_controlled_results import OLD, RAW_LOCK
from .prefix_figures import csv_file

CLOCK_KEYS = ("visit", "arrival_ns", "delivery_clock", "sample_start", "sample_end", "status")
WINDOW_NS = 20_000_000


def components(row):
    due, ready, release = (row[k] for k in ("arrival_ns", "available_ns", "released_ns"))
    if release < max(ready, due):
        raise ValueError("released before the due time or before the input buffer existed")
    return max(0, ready - due), release - max(ready, due)


def summarize(rows):
    delays = [components(row) for row in rows]
    source = [a for a, _ in delays]
    post_ready = [b for _, b in delays]
    total = [a + b for a, b in delays]
    return dict(
        accounted=len(rows),
        ready_late=sum(a > 0 for a in source),
        ready_late_20ms=sum(a > WINDOW_NS for a in source),
        release_late_20ms=sum(t > WINDOW_NS for t in total),
        release_late_20ms_on_time_buffers=sum(not a and b > WINDOW_NS for a, b in delays),
        **timing_ms(source, "buffer_lateness"),
        **timing_ms(post_ready, "after_ready"),
        **timing_ms(total, "total"),
        **timing_ms((b for a, b in delays if a == 0), "on_time_buffer_release"),
    )


def paired_cost(primary, alternate):
    fused = {row["visit"]: row for row in primary if row["outcome"] == "emitted"}
    staggered = {row["visit"]: row for row in alternate if row["outcome"] == "emitted"}
    joint = sorted(fused.keys() & staggered.keys())
    return dict(
        both_emitted=len(joint),
        fused_only=len(fused) - len(joint),
        staggered_only=len(staggered) - len(joint),
        **timing_ms((fused[i]["native_cpu_ns"] for i in joint), "common_fused_cpu"),
        **timing_ms((staggered[i]["native_cpu_ns"] for i in joint), "common_staggered_cpu"),
        **timing_ms(
            (staggered[i]["native_cpu_ns"] - fused[i]["native_cpu_ns"] for i in joint),
            "common_staggered_minus_fused_cpu",
        ),
        **timing_ms(
            (staggered[i]["native_wall_ns"] - fused[i]["native_wall_ns"] for i in joint),
            "common_staggered_minus_fused_wall",
        ),
    )


def audit(out):
    before = sealed(previous.REPORT, "prediction-lock.json", OLD)
    after = sealed(out, RAW_LOCK)
    series = []
    for role in (previous.FOUR, previous.MIXED):
        trace = f"raw/{role}/trace.json.gz"
        series.append(("QNAP-fed", "previous", role, readgz(previous.REPORT / trace)))
    for pair, role in trial.ORDER:
        path = out / f"raw/{pair}/{role}/trace.json.gz"
        series.append(("local predecoded", pair, role, readgz(path)))
    clock = [tuple(row[k] for k in CLOCK_KEYS) for row in series[0][3]]
    rows = []
    for source, pair, role, observations in series:
        for row in observations:
            if tuple(row[k] for k in CLOCK_KEYS) != clock[row["visit"]]:
                raise ValueError("measurements changed the original detector arrival event")
        rows.append(dict(source=source, pair=pair, role=role, **summarize(observations)))
    name = "arrival-decomposition.csv"
    csv_file(out / name, rows)
    records = {(pair, role): trace for _, pair, role, trace in series}
    match = "paired-visit-cost.csv"
    csv_file(
        out / match,
        [
            dict(
                pair=pair,
                **paired_cost(records[pair, previous.FOUR], records[pair, previous.MIXED]),
            )
            for pair in ("previous", "BA", "AB")
        ],
    )
    save_json(
        out / "arrival-decomposition-lock.json",
        dict(
            cases=after["cases"],
            files={n: _sha(out / n) for n in (name, match)},
            predecoded_prediction_lock_sha256=_sha(out / RAW_LOCK),
            qnap_prediction_lock_sha256=OLD,
            qnap_cases=before["cases"],
            analyzer_sha256=_sha(Path(__file__)),
        ),
    )


if __name__ == "__main__":
    audit(trial.REPORT)
