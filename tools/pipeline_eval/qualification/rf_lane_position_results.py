"""Score the frozen exclusive-frequency position replays and render their error distributions."""

import argparse

from .. import whole_iq
from ..__main__ import local_output, save_json
from . import rf_lane_position as trial
from . import screening_figures
from .bracketed_position_results import scientific
from .complete_detector_roster import BINDINGS
from .fresh_replay_results import geographic, sealed
from .full_held_scores import held_references
from .full_v5_check import _sha
from .parallel_position_results import terminal_rows
from .phase_support_results import pack
from .prefix_figures import csv_file
from .recording_to_v5 import digest
from .whole_pressure_trial import rows_from

LABELS = {
    "complete": "Complete frequency assignment",
    "recorded": "Packets received by final arrival",
    "timely": "Packets received within 20 ms",
    "other_lanes": "Only the seven fast frequencies",
    "reference_wide": "Full fast detector",
    "reference_original": "Full original detector",
}


def match_complete(row, panel_row, audit):
    probes = audit["complete_probes_sha256"]["whole"]
    if (
        any(row[k] != panel_row[k] or row[k] != audit[k] for k in BINDINGS)
        or row["id"] != panel_row["id"]
        or row["configured_rf_hz"] != audit["assigned_rf_hz"]
        or row["selected_visits"] != audit["valid_visits"]
        or row["original_visits"] != audit["original_visits"]
        or row["probe_sha256"] != "sha256:" + probes
        or scientific(row["result"]) != scientific(panel_row["result"])
    ):
        raise ValueError("the two complete frequency assignments disagree on input or position")
    return dict(
        visits=row["selected_visits"],
        original_visits=row["original_visits"],
        rf_hz=row["configured_rf_hz"],
        probe_sha256=probes,
        scientific_result_sha256=digest(scientific(row["result"])),
    )


def compare_complete(out, panel):
    own = sealed(out, "prediction-lock.json")
    sealed(panel, "prediction-lock.json")
    by_id = {
        r["id"]: r for r in rows_from(panel / "positions.jsonl.gz") if r["condition"] == "whole"
    }
    complete = {
        r["id"]: r for r in rows_from(out / "positions.jsonl.gz") if r["policy"] == "complete"
    }
    audit = whole_iq.read(panel / "packet-audit.json")
    save_json(
        out / "independent-comparison.json",
        dict(
            measured_prediction_sha256=_sha(out / "prediction-lock.json"),
            panel_prediction_sha256=_sha(panel / "prediction-lock.json"),
            cases={i: match_complete(complete[i], by_id[i], audit[i]) for i in own["cases"]},
        ),
    )


def score(out):
    lock = sealed(out, "prediction-lock.json")
    rows = list(terminal_rows(rows_from(out / "positions.jsonl.gz")))
    cases = lock["cases"]
    if len(rows) != len(cases) * len(LABELS) or {
        (r["id"], r["method"].removeprefix("rf_lane_")) for r in rows
    } != {(i, m) for i in cases for m in LABELS}:
        raise ValueError("each original recording must have every assigned method and control")
    _, refs = held_references(None, cases)
    csv_file(out / "scores.csv", geographic(rows, {r["id"]: r for r in refs}))
    timing = []
    for row in rows:
        if row["policy"] not in trial.POLICIES:
            continue
        measured = row["position_resources"] or {}
        timing.append(
            dict(
                id=row["id"],
                policy=row["policy"],
                status=row["result"]["status"],
                visits=row["selected_visits"],
                positive_probes=row["positive_probes"],
                position_wall_s=measured.get("wall_s"),
                position_cpu_s=measured.get("cpu_s"),
                position_peak_bytes=measured.get("peak_bytes"),
            )
        )
    csv_file(out / "position-timing.csv", timing)
    pack(out / "decisions.jsonl.gz", rows)
    names = (
        "decisions.jsonl.gz",
        "scores.csv",
        "position-timing.csv",
        "support.csv",
        "prediction-lock.json",
        "position-input-lock.json",
    )
    save_json(out / "figure-lock.json", dict(cases=cases, files={n: _sha(out / n) for n in names}))
    charts = []
    for primary, title, modes in (
        (
            "recorded",
            "One frequency on the original detector at recording speed",
            ("recorded", "complete", "reference_wide", "reference_original"),
        ),
        (
            "timely",
            "Position from frequency-routed packets delivered within 20 ms",
            ("timely", "recorded", "other_lanes", "complete"),
        ),
    ):
        charts.append(
            dict(
                id=f"rf-lane-position-{primary}",
                method="rf_lane_" + primary,
                title=title,
                scope="roof",
                cases="sealed",
                seal="figure-lock.json",
                provenance=list(names[1:]),
                caption="The RF assignment is fixed before the first visit. The 20 ms limit "
                "applies to detector packets. Position fitting follows the final arrival.",
                series=[
                    dict(
                        key=key,
                        label=LABELS[m],
                        value="rf_lane_" + m,
                        file=names[0],
                        native_field=BINDINGS[0],
                        match=list(BINDINGS),
                    )
                    for key, m in zip(
                        ("one", "stock", "one_native_factors", "all_visits"), modes, strict=True
                    )
                ],
            )
        )
    save_json(out / "figures.json", dict(version=2, charts=charts))
    screening_figures.generate(out / "charts", evidence=out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=local_output, default=trial.REPORT)
    parser.add_argument("--compare-panel", type=local_output, help="verify independent full fits")
    args = parser.parse_args()
    if args.compare_panel:
        compare_complete(args.out, args.compare_panel)
    else:
        score(args.out)
