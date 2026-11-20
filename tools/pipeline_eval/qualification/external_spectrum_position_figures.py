"""Export the sealed Watson offer scores as a portable transfer comparison."""

import argparse
import gzip
import json
from hashlib import sha256
from pathlib import Path

from .. import figure_books
from ..scoring import ARMS, validate_result
from . import scout_stage_figures as stage
from .external_spectrum_source import HOURS
from .external_spectrum_trial import HELD, preserve, serialize

CHART_ID = "watson-spectrum-transfer"
POSITION_ROWS = "transfer-positions.jsonl.gz"
QUERIES = "transfer-queries.json"
LOCK = "transfer-lock.json"
PROVENANCE = ("prediction-lock.json", "stage-figure-lock.json", "scores.json")
CONDITIONS = {"present": "True tile included", "omitted": "True tile omitted"}
SERIES = {
    "spectrum": ("candidate", "Measured spectrum"),
    "time_shuffle": ("stock", "Rotated ridge times"),
    "geometry": ("one", "Visibility only"),
}
BINDINGS = ("input_sha256", "observation_sha256", "catalogue_sha256")
BOUNDARY = "Recorded one-second spectrum power and preceding-night TLE to tile decision"
UNAVAILABLE = "RF-dependent calibration is unidentifiable at one nominal RF center"


def result(row, condition, grid):
    selected = row[condition]
    published = selected["published"]
    attempted = row["ridges"] > 0
    reason = None
    if not published:
        if not attempted:
            reason = "no_qualifying_spectrum_ridge"
        else:
            reason = (
                "visibility_only_diagnostic"
                if row["mode"] == "geometry"
                else "broad_rank_did_not_clear_publication_gate"
            )
    forced = selected["forced"]
    exported = dict(
        status="ok" if published else "withheld",
        boundary=BOUNDARY,
        reason=reason,
        metrics=dict(
            ridges=row["ridges"],
            position_attempted=attempted,
            terminal_position_decision=not attempted,
        ),
        arms=dict(
            c0=dict(
                latlon=grid[row["broad_tile"]] if published else None,
                forced_latlon=grid[forced] if forced is not None else None,
            ),
            fitted_c=dict(
                status="unavailable", reason=UNAVAILABLE, latlon=None, forced_latlon=None
            ),
        ),
    )
    validate_result(exported)
    return exported


def export(report):
    stage.verify(report, "prediction-lock.json")
    stage.verify(report, "stage-figure-lock.json")
    scores = json.loads((report / "scores.json").read_bytes())
    config = json.loads(gzip.decompress((report / "config.json.gz").read_bytes()))
    manifest = json.loads((report / "source.json").read_bytes())
    digests = {row["local"]: row["sha256"] for row in manifest["members"]}
    rows = [r for r in scores["rows"] if r["mode"] in SERIES]
    by_key = {(r["window"], r["mode"]): r for r in rows}
    windows = [f"{day}-{hour:02d}" for day in HELD for hour in HOURS]
    expected = {(window, mode) for window in windows for mode in SERIES}
    if len(by_key) != len(rows) or by_key.keys() != expected:
        raise ValueError("external spectrum scores lack a complete matched holdout")

    queries, predictions = [], []
    for window in windows:
        day, hour = window.split("-")
        observation = digests[f"{day}-Kerberos_{day}_{hour}00.csv"]
        catalogue = digests[f"{day}-starlink.tle"]
        for condition in CONDITIONS:
            case = f"watson-{window}-{condition}"
            offer = dict(
                catalogue_sha256=catalogue,
                observation_sha256=observation,
                clock_offset_s=config["locked_clock_s"],
                duration_s=config["duration_s"],
                points=[config["grid"][index] for index in scores["offers"][condition]],
            )
            bindings = dict(
                catalogue_sha256=catalogue,
                observation_sha256=observation,
                input_sha256=sha256(serialize(offer)).hexdigest(),
            )
            queries.append(
                dict(
                    id=case,
                    condition=condition,
                    recording=f"Watson {day} {hour}:00 UTC",
                    truth=scores["site"],
                    bindings=bindings,
                )
            )
            for mode in SERIES:
                predictions.append(
                    dict(
                        id=case,
                        method=f"watson-{mode}",
                        **bindings,
                        result=result(by_key[window, mode], condition, config["grid"]),
                    )
                )
    preserve(report / QUERIES, serialize(dict(queries=queries)))
    preserve(report / POSITION_ROWS, gzip.compress(b"".join(map(serialize, predictions)), mtime=0))
    files = {
        name: sha256((report / name).read_bytes()).hexdigest()
        for name in (QUERIES, POSITION_ROWS, *PROVENANCE)
    }
    preserve(report / LOCK, serialize(dict(cases=[query["id"] for query in queries], files=files)))

    series = []
    for mode, (key, label) in SERIES.items():
        item = dict(
            key=key,
            label=label,
            value=f"watson-{mode}",
            file=POSITION_ROWS,
            forced_label=f"{label} · forced",
        )
        if key != "candidate":
            item["match"] = BINDINGS
        series.append(item)
    chart = dict(
        id=CHART_ID,
        method="watson-spectrum",
        scope="transfer",
        title="Position decisions at the independent Watson station",
        caption="Four held power-scan windows at one UK station. Each has a matched included and "
        "omitted offer. A forced point ranks only offered tile centers. Fitted RF "
        "calibration is unavailable at one nominal RF center.",
        cases="sealed",
        seal=LOCK,
        queries=QUERIES,
        provenance=PROVENANCE,
        condition_labels=CONDITIONS,
        series=series,
    )
    preserve(report / "figures.json", serialize(dict(version=2, charts=[chart])))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    report = parser.parse_args().report
    export(report)
    figure_books.generate(
        report / "charts", ARMS, methods=[CHART_ID], panel="screening", evidence=report
    )


if __name__ == "__main__":
    main()
