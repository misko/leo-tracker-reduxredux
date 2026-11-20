"""Export each plotted frequency-stage dot alongside its supporting capture rows."""

import argparse
import csv
from collections import defaultdict
from pathlib import Path

from .. import figure_books, whole_iq
from ..__main__ import local_output, save_json
from ..scoring import ARMS, distribution
from . import session_geometry_results as results
from . import session_geometry_trial as trial
from .full_v5_check import _sha
from .prefix_figures import csv_file

CHART_LABELS = {
    "fixed": "Fixed orbit",
    "clock": "Clock only",
    "phase": "Phase only",
    "phase-clock": "Phase + clock",
    "center": "Offer centre",
    "median": "Fit median",
    "shuffle": "CFO shuffle",
    "rotated": "Rotated orbit",
}


def export(out):
    score_path = out / "score-lock.json"
    score_lock = whole_iq.read(score_path)
    for filename, digest in score_lock["files"].items():
        whole_iq.checked(out / filename, digest)
    stage_lock = out / "stage-figure-lock.json"
    for filename, digest in whole_iq.read(stage_lock)["files"].items():
        whole_iq.checked(out / filename, digest)
    source = out / f"{results.STAGE}.csv"
    groups = defaultdict(list)
    rows = []
    with source.open(newline="") as stream:
        for row in csv.DictReader(stream):
            rows.append(dict(row, row_kind="capture", captures=1))
            groups[row["site"], row["offer"], row["method"], row["held_visit"]].append(row)
    for values in groups.values():
        medians = {
            metric: distribution(float(r[metric]) for r in values)["p50"]
            for metric in results.FREQUENCIES
        }
        rows.append(
            dict(
                values[0],
                **medians,
                row_kind="visit_median",
                captures=len(values),
                capture=None,
                tracks=None,
                tail_phases_s=None,
            )
        )
    name = f"{results.STAGE}-visit-medians.csv"
    csv_file(out / name, rows)
    descriptor = out / "stage-figure.json"
    specification = whole_iq.read(descriptor)
    save_json(descriptor, dict(specification, csv=name))
    receipt = whole_iq.read(stage_lock)
    for filename in (descriptor.name, name):
        receipt["files"][filename] = _sha(out / filename)
    save_json(stage_lock, receipt)

    charts = []
    for site in ("prague", "simulation"):
        spec_file = out / site / "figures.json"
        spec = whole_iq.read(spec_file)
        for chart in spec["charts"]:
            charts.append(chart["method"])
            for series in chart["series"]:
                label = CHART_LABELS[series["value"]]
                series["label"] = label
                if "forced_label" in series:
                    series["forced_label"] = f"Forced {label.lower()}"
        save_json(spec_file, spec)
    figure_books.generate(out / "charts", ARMS, panel="screening", evidence=out, methods=charts)
    for filename in (stage_lock.name, "charts/manifest.json"):
        score_lock["files"][filename] = _sha(out / filename)
    save_json(score_path, dict(score_lock, presentation_exporter_sha256=_sha(Path(__file__))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=local_output, default=trial.OUT)
    export(parser.parse_args().out)


if __name__ == "__main__":
    main()
