"""Score sealed dateline endpoints and republish the matched in-range control."""

import gzip
import json

from ..__main__ import save_json
from ..scoring import ARMS, distance_km, distribution, validate_result
from . import cavity_longitude_control as control
from . import cavity_longitude_trial as trial
from . import cavity_payload_trial as original
from .full_receiver_comparison import require_fields, seal
from .phase_support_results import pack
from .prefix_figures import csv_file

REPORT = trial.REPORT
METHOD = "v5_cavity_payload_wrapped"
STOCK = "v5_cavity_payload_small"
MATCH = ("input_sha256", "native_sha256", "catalog_sha256", "tile")
DATELINE_MATCH = (*MATCH, "track_config_sha256", "history_sha256", "screen_center")


def archived_original():
    folder = REPORT.with_name("cavity-payload")
    seal(folder, "prediction-lock.json", ("positions.jsonl.gz", "package.json"))
    with gzip.open(folder / "positions.jsonl.gz", "rt") as stream:
        picked = [
            row for line in stream if (row := json.loads(line))["id"] == "DS29-0082"
            and row["method"] == STOCK and row["detector"] == "ordinary"
        ]
    (row,) = picked
    return row


def candidate_and_controls():
    for name, wanted in trial._read(REPORT / "prediction-lock.json").items():
        if trial._sha(REPORT / name) != wanted:
            raise ValueError("sealed wrapped prediction changed")
    wrapped = {row["id"]: row for row in trial._read(REPORT / "predictions.json")}
    original_control = trial._read(REPORT / "control-predictions.json")
    lock = REPORT / control.LOCK
    history = trial._read(lock)
    require_fields(original_control, dict(lock_sha256=trial._sha(lock)))
    require_fields(history, dict(
        input_lock_sha256=trial._sha(REPORT / "input-lock.json"),
        base_sha256=trial._read(REPORT / "source-lock.json")["parent_archive_sha256"],
    ))
    stock = {row["id"]: row for row in original_control["rows"]}
    stock["DS29-0082"] = archived_original()
    if set(wrapped) != set(stock) or set(wrapped) != {"positive", "far-omitted", "DS29-0082"}:
        raise ValueError("missing dateline or in-range comparison")

    for ident, row in wrapped.items():
        other = stock[ident]
        match = DATELINE_MATCH if ident != "DS29-0082" else MATCH
        if ident == "DS29-0082":
            width = row["tile"].pop("width_km")
            if width != 25:
                raise ValueError("roof offer differs from its declared width")
        require_fields(other, {k: row[k] for k in match})
        for result in (row["result"], other["result"]):
            validate_result(result)
    return wrapped, stock


def figure(spec, rows, cases, proof):
    name = f"{spec['id']}-figure-lock.json"
    pos = f"{spec['id']}-positions.jsonl.gz"
    pack(REPORT / pos, rows)
    save_json(REPORT / name, dict(
        cases=cases, files={path: trial._sha(REPORT / path) for path in (pos, *proof)}
    ))
    transfer = spec["scope"] == "transfer"
    return dict(
        spec, method=METHOD, cases="sealed", seal=name, provenance=list(proof),
        series=[
            dict(
                key="candidate" if transfer else "one",
                file=pos, label="Longitude-safe compact cavity", value=METHOD,
            ),
            dict(
                key="stock", file=pos, label="Original small package",
                value=STOCK, match=list(DATELINE_MATCH if transfer else MATCH),
            ),
        ],
    )


def publish():
    wrapped, stock = candidate_and_controls()
    cases = ["positive", "far-omitted"]
    input_lock = trial._read(REPORT / "input-lock.json")
    labels = REPORT / "synthetic-labels.json"
    if trial._sha(labels) != input_lock["private_labels_sha256"]:
        raise ValueError("synthetic truth differs from its pre-run commitment")
    truth = trial._read(labels)["site"]
    roof_truth = trial.direct.common._frozen_roof()[0]["DS29-0082"]["truth"]
    records = [row for ident in wrapped for row in (wrapped[ident], stock[ident])]
    scores = []
    for row in records:
        ident = row["id"]
        result = row["result"]
        metric = row.get("runtime", {}).get("finish", [])
        reference = roof_truth if ident == "DS29-0082" else truth
        for arm in ARMS:
            endpoint = result["arms"][arm]
            scores.append(dict(
                id=ident,
                method=row["method"],
                arm=arm,
                status=result["status"],
                reason=result.get("reason"),
                error_km=distance_km(endpoint["latlon"], reference),
                rf_rms_hz=endpoint.get("rf_rms_hz"),
                false_publication=ident == "far-omitted" and endpoint["latlon"] is not None,
                wall_s=row["wall_s"],
                monitored_cpu_s=metric[0]["cgroup_cpu_s"] if metric else None,
                monitored_memory_peak_bytes=metric[0]["cgroup_peak"] if metric else None,
            ))
    csv_file(REPORT / "scores.csv", scores)
    parity = {
        ident: original.scientific_result(wrapped[ident]["result"])
        == original.scientific_result(stock[ident]["result"])
        for ident in wrapped
    }
    save_json(REPORT / "summary.json", dict(
        scientific_parity=parity,
        synthetic_published_error_by_arm={
            arm: distribution(
                row["error_km"] for row in scores
                if row["id"] in cases and row["method"] == METHOD and row["arm"] == arm
            )
            for arm in ARMS
        },
    ))
    if not parity["DS29-0082"]:
        raise ValueError("the wrapped release changed the sealed in-range roof result")
    proof = ("prediction-lock.json", control.LOCK, "control-predictions.json", "scores.csv")
    query_file = "dateline-queries.json"
    save_json(REPORT / query_file, dict(queries=[
        dict(
            id=ident, condition=ident, recording="Synthetic dateline", truth=truth,
            bindings={key: wrapped[ident][key] for key in DATELINE_MATCH},
        )
        for ident in cases
    ]))
    save_json(REPORT / "figures.json", dict(version=1, charts=[
        figure(
            dict(
                id="cavity-longitude-dateline",
                scope="transfer",
                title="Synthetic dateline crossing through the full compact cavity",
                caption=(
                    "Paired stored-native fits. Both offers use the same synthetic RF and causal "
                    "history. A publication on the far omitted tile is a localization failure."
                ),
                queries=query_file,
                condition_labels={"positive": "Containing offer", "far-omitted": "Far omitted"},
            ),
            [r for r in records if r["id"] in cases],
            cases,
            (*proof, query_file),
        ),
        figure(
            dict(
                id="cavity-longitude-roof-control",
                scope="roof",
                title="Longitude-safe compact cavity on an ordinary in-range capture",
                caption=(
                    "Fresh wrapped package and sealed original small-package control. "
                    "Both used the same ordinary GLRT factors, causal archive and tile."
                ),
            ),
            [r for r in records if r["id"] == "DS29-0082"],
            ["DS29-0082"],
            proof,
        ),
    ]))
    roof = trial._read(REPORT / "figures.json")
    for series in roof["charts"][1]["series"]:
        series["native_authority"] = "ordinary"
    save_json(REPORT / "figures.json", roof)


if __name__ == "__main__":
    publish()
