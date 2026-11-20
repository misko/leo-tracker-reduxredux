"""Score paired paced-retained position fits on the two archived roof captures."""

from pathlib import Path

from .. import whole_iq
from ..__main__ import save_json
from ..scoring import ARMS, distance_km
from . import arrival_queue as pace
from . import arrival_queue_position as positions
from . import screening_figures
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from


def score(report):
    parent = pace.PARENT / "prediction-lock.json"
    lock = whole_iq.read(
        whole_iq.checked(
            parent, whole_iq.read(report / "source-lock.json")["parent_prediction_sha256"]
        )
    )
    full = whole_iq.checked(pace.PARENT / "positions.jsonl.gz", lock["files"]["positions.jsonl.gz"])
    archived = {(r["id"], r["method"]): r for r in rows_from(full)}
    rows, matched, descriptors, files = [], [], [], []
    cohorts = dict(
        control=pace.whole_center_union.BASELINE, candidate=pace.whole_center_union.METHOD
    )
    for mode, existing in cohorts.items():
        path = report / f"positions-{mode}-lock.json"
        result = whole_iq.read(path)
        files.append(path.name)
        for name, digest in result["files"].items():
            whole_iq.checked(report / name, digest)
            files.append(name)
        source = rows_from(report / f"positions-{mode}.jsonl.gz")
        if {r["id"] for r in source} != set(pace.CPUS):
            raise ValueError("paced position rows lack the complete scheduled roster")
        for row in source:
            baseline = archived[row["id"], existing]
            if row["paired_paced_native_sha256"] != baseline["native_sha256"] or any(
                row[k] != baseline[k] for k in ("tile", "catalog_sha256", "original_request_sha256")
            ):
                raise ValueError("original position does not match the recorded paced inputs")
            matched.append((mode, row, baseline))

    _, locations = held_references(None, pace.CPUS)
    truth = {r["id"]: r["truth"] for r in locations}
    complete_data = []
    for mode, actual, baseline in matched:
        ident = actual["id"]
        full = dict(
            baseline,
            paired_paced_native_sha256=baseline["native_sha256"],
            origin="published complete unpaced factors",
            dropped=0,
            resources={},
        )
        for record in (actual, full):
            complete_data.append(record)
            result = record["result"]
            for arm in ARMS:
                point = result["arms"][arm]
                rows.append(
                    dict(
                        id=ident,
                        mode=mode,
                        method=record["method"],
                        arm=arm,
                        status=result["status"],
                        origin=record["origin"],
                        queue_drops=record["dropped"],
                        position_error_km=distance_km(point.get("latlon"), truth[ident]),
                        displacement_from_full_km=distance_km(
                            point.get("latlon"), baseline["result"]["arms"][arm]["latlon"]
                        ),
                        rf_rms_hz=point.get("rf_rms_hz"),
                        frequency_score=result["metrics"].get(f"{arm}_frequency_score"),
                        observations=result["metrics"].get("observations"),
                        tracks=result["metrics"].get("tracks"),
                        position_wall_s=record["resources"].get("wall_s"),
                        position_cpu_s=record["resources"].get("cpu_s"),
                    )
                )
    pack(report / "matched-positions.jsonl.gz", complete_data)
    csv_file(report / "position-scores.csv", rows)
    files.extend(("matched-positions.jsonl.gz", "position-scores.csv", "stage-lock.json"))
    seal = "position-score-lock.json"
    save_json(
        report / seal,
        dict(
            cases=list(pace.CPUS),
            files={name: _sha(report / name) for name in files},
            publisher_sha256=_sha(Path(__file__)),
            parent_position_lock_sha256=_sha(parent),
        ),
    )
    for mode, existing in cohorts.items():
        friendly = "stock wide" if mode == "control" else "fifth center"
        descriptors.append(
            dict(
                id=f"paced-position-{mode}",
                method=positions.METHODS[mode],
                scope="roof",
                cases="sealed",
                seal=seal,
                title=f"Position after actual paced drops · {friendly}",
                caption=(
                    "One active detector and one waiting slot on saved IQ at the original delivery "
                    "pace. Retained native packets are byte-verified. The matched unpaced control "
                    "uses every valid visit. Original v5 references use capture-era factors."
                ),
                provenance=files[0:-3] + ["position-scores.csv", "stage-lock.json"],
                series=[
                    dict(
                        key=key,
                        label=label,
                        file="matched-positions.jsonl.gz",
                        value=method,
                        native_field="paired_capture_sha256",
                        **(
                            {
                                "match": [
                                    "paired_paced_native_sha256",
                                    "tile",
                                    "catalog_sha256",
                                    "original_request_sha256",
                                ]
                            }
                            if key == "stock"
                            else {}
                        ),
                    )
                    for key, label, method in (
                        ("one", "Paced retained visits", positions.METHODS[mode]),
                        ("stock", "Complete unpaced visits", existing),
                    )
                ],
            )
        )
    save_json(report / "figures.json", dict(version=1, charts=descriptors))
    screening_figures.generate(report / "position-charts", evidence=report)


if __name__ == "__main__":
    score(pace.REPORT)
