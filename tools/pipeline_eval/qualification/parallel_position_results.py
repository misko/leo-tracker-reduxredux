"""Compare compact positions at the final arrival against all archived v5 options."""

import argparse
import gzip
from hashlib import sha256

from ..__main__ import local_output, save_json
from ..scoring import validate_result
from . import parallel_position as trial
from . import screening_figures
from .complete_detector_roster import BINDINGS
from .fresh_replay_results import geographic, sealed
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

LABELS = {
    "wide": "Fast detector only",
    "original": "Original detector only",
    "replace": "Use the original pair on overlap",
    "fill": "Fill a missed antenna from the original",
    "timely": "Keep only packets within 20 ms",
}


def terminal_rows(rows):
    """Tell the gallery when the measured release rule withheld before fitting."""
    for row in rows:
        result = row["result"]
        if result.get("reason") == "no_passing_probe_by_cutoff":
            if (
                row.get("positive_probes", 0)
                or row["position_resources"] is not None
                or result["metrics"].get("position_attempted") is not False
            ):
                raise ValueError("empty-probe withholding conflicts with the measured input or fit")
            result = dict(result, metrics=dict(result["metrics"], terminal_position_decision=True))
        validate_result(result)
        yield dict(row, result=result)


def score(out, legacy):
    prediction = sealed(out, "prediction-lock.json")
    inputs = sealed(
        out, "position-input-lock.json", prediction["files"]["position-input-lock.json"]
    )
    materializer = gzip.decompress((out / "materializer.py.gz").read_bytes())
    if sha256(materializer).hexdigest() != inputs["program_sha256"]:
        raise ValueError("saved materializer differs from the one that selected the measurements")
    rows = list(terminal_rows(rows_from(out / "positions.jsonl.gz")))
    cohort = "separate" if legacy else "concurrent"
    cases = list(inputs["cases"])
    expected = {(case, policy) for case in cases for policy in trial.POLICIES}
    if (
        cases != prediction["cases"]
        or len(rows) != len(expected)
        or {(r["id"], r["policy"]) for r in rows} != expected
        or any(r["cohort"] != cohort for r in rows)
    ):
        raise ValueError("incomplete or mismatched recording and policy roster")

    pack(out / "decisions.jsonl.gz", rows)
    _, refs = held_references(None, cases)
    csv_file(out / "scores.csv", geographic(rows, {r["id"]: r for r in refs}))
    runtime = []
    for row in rows:
        measured = row["position_resources"] or {}
        runtime.append(
            dict(
                id=row["id"],
                policy=row["policy"],
                status=row["result"]["status"],
                acquisition_cutoff_s=row["cutoff_ns"] / 1e9,
                selected_visits=row["processed_visits"],
                positive_probes=row.get("positive_probes", 0),
                position_service_wall_s=measured.get("wall_s"),
                position_service_cpu_s=measured.get("cpu_s"),
                position_service_peak_bytes=measured.get("peak_bytes"),
            )
        )
    csv_file(out / "timing.csv", runtime)
    names = [
        "decisions.jsonl.gz",
        "positions.jsonl.gz",
        "scores.csv",
        "support.csv",
        "timing.csv",
        "position-input-lock.json",
        "materializer.py.gz",
        "prediction-lock.json",
    ]
    save_json(out / "figure-lock.json", dict(cases=cases, files={n: _sha(out / n) for n in names}))
    boundary = (
        "Detector runs on separate clocks aligned to the recording"
        if legacy
        else "Two detectors running concurrently on the recording clock"
    )
    caption = (
        "The last scheduled arrival closes the position input. The curves count all scheduled "
        "recordings. Position runtime starts after the cutoff."
    )
    charts = []
    for policy in ("replace", "fill", "timely"):
        controls = [("stock", "wide"), ("one_native_factors", "original"), ("one", policy)]
        if policy == "timely":
            controls.append(("all_visits", "replace"))
        series = [
            dict(
                key=key,
                label=LABELS[mode],
                value=f"parallel_{cohort}_{mode}",
                file=names[0],
                native_field=BINDINGS[0],
                match=list(BINDINGS),
            )
            for key, mode in controls
        ]
        charts.append(
            dict(
                id=f"parallel-{cohort}-{policy}",
                scope="roof",
                method=f"parallel_{cohort}_{policy}",
                cases="sealed",
                seal="figure-lock.json",
                title=f"{LABELS[policy]} · {boundary}",
                caption=caption,
                provenance=names[1:],
                series=series,
            )
        )
    save_json(out / "figures.json", dict(version=2, charts=charts))
    screening_figures.generate(out / "charts", methods=[c["id"] for c in charts], evidence=out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--separate-clocks", action="store_true")
    parser.add_argument("--out", type=local_output, help="directory containing a completed run")
    args = parser.parse_args()
    score(
        args.out or (trial.REPORT / "separate-clocks" if args.separate_clocks else trial.REPORT),
        args.separate_clocks,
    )
