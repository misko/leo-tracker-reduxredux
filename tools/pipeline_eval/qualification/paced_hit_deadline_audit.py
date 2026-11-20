"""Count positive GLRT support actually delivered before the 20 ms due time."""

from pathlib import Path

from ..__main__ import save_json
from ..variants.negative_rescue import positive
from ..variants.selective_capture import visit_pairs
from . import paced_hit as trial
from .arrival_queue import readgz
from .arrival_queue_results import timing_ms
from .fifth_completion_results import native_data
from .fresh_replay_results import sealed
from .full_v5_check import _sha
from .paced_hit_results import LOCK, POS
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from


def deadline_support(rows, probes):
    emitted = [row for row in rows if row["outcome"] == "emitted"]
    native = dict(visit_pairs(probes))
    if [row["visit"] for row in emitted] != list(native):
        raise ValueError("deadline audit needs the exact actual retained physical visits")
    summary = []
    for primary_hit in (False, True):
        visits = [row for row in emitted if row["primary_hit"] is primary_hit]
        if any(row["emitted_ns"] < row["arrival_ns"] for row in visits):
            raise ValueError("a detector emission preceded the original scheduled time")
        timely = [row for row in visits if row["emitted_ns"] - row["arrival_ns"] <= 20_000_000]
        positive_counts = [sum(map(positive, native[row["visit"]])) for row in timely]
        summary.append(
            dict(
                primary_hit=primary_hit,
                emitted=len(visits),
                timely_visits=len(timely),
                timely_positive_visits=sum(n > 0 for n in positive_counts),
                timely_positive_probes=sum(positive_counts),
                **timing_ms((r["native_wall_ns"] for r in visits), "native_wall"),
            )
        )
    return summary


def run(out):
    prediction = sealed(out, LOCK)
    if prediction["cases"] != [trial.CASE]:
        raise ValueError("deadline audit requires the locked direct matched waveform")
    results = {r["role"]: r for r in rows_from(out / POS)}
    summary = []
    for role in trial.ORDER:
        row = results[role]
        if not row["raw_verified"] or row["native_sha256"] is None:
            raise ValueError("a partial or failed attempt cannot support a live deadline census")
        path = f"native/{role}/{trial.CASE}.json.gz"
        doc = native_data(out / path, row["native_sha256"])
        trace = readgz(out / f"raw/{role}/trace.json.gz")
        summary.extend(
            dict(role=role, **s) for s in deadline_support(trace, doc["source"]["probes"])
        )
    name = "deadline-support.csv"
    csv_file(out / name, summary)
    save_json(
        out / "deadline-support-lock.json",
        dict(
            cases=prediction["cases"],
            files={name: _sha(out / name)},
            prediction_lock_sha256=_sha(out / LOCK),
            exporter_sha256=_sha(Path(__file__)),
        ),
    )


if __name__ == "__main__":
    run(trial.REPORT)
