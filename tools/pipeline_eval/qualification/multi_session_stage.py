"""Export the plotted stationary-receiver support values from sealed evidence."""

import argparse
import csv
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json
from . import multi_session_results as results
from .full_v5_check import _sha
from .prefix_figures import csv_file

DESCRIPTOR = "stage-figure.json"
STAGE_SEAL = "stage-figure-lock.json"
TABLE = "stationary-support.csv"
IMAGE = "stationary-support.png"
PDF = "stationary-support.pdf"
TRACES = (
    ("Cumulative, all held blocks", "prefix", "held_lead", "all"),
    ("Session alone, all held blocks", "session", "held_lead", "all"),
    ("Early only, later held blocks", "prefix", "later_held_lead", "late"),
)


def plot_rows(scores, sessions):
    by_method = {(row["offer"], row["method"]): row for row in scores}
    if len(by_method) != len(scores):
        raise ValueError("stationary support requires unique offer and method scores")
    early = sum(row["group"] == "early" for row in sessions)
    return [
        dict(
            offer=offer,
            series=series,
            acquisition=step,
            recording=session["id"],
            acquisition_group=session["group"],
            method=f"{prefix}_{step}",
            held_group=scope,
            mean_held_log_score_lead=by_method[offer, f"{prefix}_{step}"][field],
        )
        for offer in results.CONDITIONS
        for series, prefix, field, scope in TRACES
        for step, session in enumerate(sessions, 1)
        if scope == "all" or step <= early
    ]


def export(folder=results.trial.OUT):
    score_lock = folder / "score-lock.json"
    sources = ("scores.csv", IMAGE, PDF, results.DECISION_LOCK)
    hashes = whole_iq.read(score_lock)["files"]
    for name in sources:
        whole_iq.checked(folder / name, hashes[name])
    sessions, _ = results.after_lock(folder)
    with (folder / "scores.csv").open(newline="") as stream:
        rows = plot_rows(list(csv.DictReader(stream)), sessions)
    csv_file(folder / TABLE, rows)
    save_json(
        folder / DESCRIPTOR,
        dict(
            version=1,
            id="stationary-support",
            title="Held geographic support across stationary receiver sessions",
            sample="6 recordings at one surveyed roof · 30 minutes across 11.73 days",
            boundary="Archived GLRT and causal TLEs → held spatial log likelihood",
            note=(
                "Each point compares the selected cell with the best held rival at least "
                "10 km away. The first three acquisitions also predict only the later held "
                "blocks. The dotted line marks the +0.04 publication threshold. "
                "Same-lane differences cancel fixed RF calibration."
            ),
            seal=STAGE_SEAL,
            image=IMAGE,
            pdf=PDF,
            csv=TABLE,
        ),
    )
    receipts = (*sources, score_lock.name, results.trial.LOCK, TABLE, DESCRIPTOR)
    save_json(
        folder / STAGE_SEAL,
        dict(
            files={name: _sha(folder / name) for name in receipts},
            export_source_sha256=_sha(Path(__file__)),
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=local_output, default=results.trial.OUT)
    export(parser.parse_args().report)


if __name__ == "__main__":
    main()
