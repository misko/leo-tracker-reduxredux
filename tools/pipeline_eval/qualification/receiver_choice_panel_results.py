"""Seal and score the direct full inputs of the lower-edge receiver study."""

import argparse
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import local_output, save_json
from . import acquisition_index, screening_figures
from . import diagnostic_whole_results as diagnostic
from . import fresh_replay_results as paired
from . import receiver_choice_panel as study
from . import whole_center_union_results as union
from .exact_wide_iq_results import timing_rows
from .full_held_scores import held_references
from .full_v5_check import _sha
from .new_waveforms_results import original_audit
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

METHODS = {"control": study.STOCK, "candidate": study.METHOD}


def figures(out, groups, rows, evidence):
    charts = []
    for group, ids in groups.items():
        title = (
            "Four versus five acquisition centers on two new lower-edge recordings"
            if group == "all"
            else f"Four versus five acquisition centers on {ids[0]}"
        )
        chart = paired.chart(out, group, title, ids, rows, evidence, group != "ds26")
        chart["id"] = f"receiver-choice-fresh-{group}"
        for series in chart["series"]:
            acquisition_index.endpoint_rows(out, chart, series)
        charts.append(chart)
    save_json(out / "figures.json", dict(version=2, charts=charts))
    screening_figures.generate(out / "charts", evidence=out)


def score(out):
    compact = paired.sealed(out, "prediction-lock.json")
    original_audit(out)
    plan = whole_iq.read(out / "source-lock.json")
    rows = rows_from(out / paired.POSITIONS)
    cases = compact["cases"]
    if sorted((r["id"], r["method"]) for r in rows) != sorted(
        (ident, method) for ident in cases for method in METHODS.values()
    ):
        raise ValueError("terminal predictions do not cover the frozen recording and method pairs")
    (ds26,) = [ident for ident in cases if ident.startswith("DS26-")]
    (ds29,) = [ident for ident in cases if ident.startswith("DS29-")]
    _, archived = held_references(None, [ds26])
    authority = {ds26: archived[0], ds29: paired.references(out, plan["cases"][ds29])}
    scores = paired.geographic(rows, authority)
    groups = dict(all=cases, ds26=[ds26], ds29=[ds29])
    csv_file(out / "scores.csv", scores)
    save_json(out / "summary.json", paired.distribution_rows(scores, groups))
    ablation, _ = union.paired_scores(scores)
    csv_file(out / "calibration.csv", ablation)
    resources = whole_iq.read(out / "resources.json")
    calls = [row for row in rows_from(out / paired.VISITS) if row["status"] == "processed"]
    csv_file(out / "deadlines.csv", timing_rows(resources, calls))
    save_json(out / "visit-coverage.json", diagnostic.visit_coverage(calls))
    evidence = (
        "prediction-lock.json",
        "raw-prediction-lock.json",
        "reference-prediction-lock.json",
        "reference-binding-audit.json",
        *paired.ROOF_REFERENCES.values(),
        "scores.csv",
        "summary.json",
        "calibration.csv",
        "deadlines.csv",
        "visit-coverage.json",
    )
    figures(out, groups, rows, evidence)
    files = (*evidence, "figures.json", *(f"{g}-figure-lock.json" for g in groups))
    save_json(
        out / "score-lock.json",
        dict(cases=cases, files={name: _sha(out / name) for name in files}),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("raw-seal", "seal", "score"))
    parser.add_argument("--work", type=local_output, default=study.WORK)
    parser.add_argument("--out", type=local_output, default=study.REPORT)
    args = parser.parse_args()
    with study.context(), patch.object(paired, "METHODS", METHODS):
        if args.action == "raw-seal":
            paired.raw_seal(args.work, args.out)
        elif args.action == "seal":
            paired.seal(args.work, args.out)
        else:
            score(args.out)
