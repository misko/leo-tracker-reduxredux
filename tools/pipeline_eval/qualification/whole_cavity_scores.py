"""Export cavity-arm RF metrics from the verified whole-IQ position receipt."""

import gzip
import json
from pathlib import Path

from ..__main__ import references, save_json
from ..scoring import ARMS, distance_km
from . import whole_cavity
from .full_v5_check import _sha
from .prefix_figures import csv_file


def arm_scores(row, truth):
    result = row["result"]
    scores = []
    for arm in ARMS:
        values = result["arms"][arm]
        scores.append(
            dict(
                id=row["id"],
                arm=arm,
                status=result["status"],
                error_km=distance_km(truth, values["latlon"]),
                conditional_rms_hz=values.get("rf_rms_hz"),
            )
        )
    return scores


def comparison(row):
    control = whole_cavity.control(row["id"])
    archive = whole_cavity.base.sealed(whole_cavity.base.PRIOR, "positions.jsonl.gz")
    checks = {k: row[k] == control[k] for k in ("native_sha256", "catalog_sha256", "tile")}
    a, b = row["result"], control["result"]
    for field in (
        "cavity_offered",
        "initial_arm_fits",
        "initial_branches",
        "kernel_sha256",
        "observations",
        "tracks",
    ):
        checks[field] = a["metrics"].get(field) == b["metrics"].get(field)
    for arm in ARMS:
        checks[arm + "_exact_position_and_rms"] = a["arms"][arm] == b["arms"][arm]
    return dict(
        exact=all(checks.values()),
        checks=checks,
        control_method=control["method"],
        control_archive_sha256=_sha(archive),
    )


def export(report=whole_cavity.REPORT):
    source = report / "source-lock.json"
    receipt = report / "prediction-lock.json"
    lock = json.loads(receipt.read_bytes())
    if json.loads(source.read_bytes()) != whole_cavity.plan() or lock["source_lock_sha256"] != _sha(
        source
    ):
        raise ValueError("whole-cavity experiment differs from its sealed source")
    if lock["cases"] != [whole_cavity.CASE] or any(
        _sha(report / name) != digest for name, digest in lock["files"].items()
    ):
        raise ValueError("whole-cavity prediction differs from its seal")
    row = json.loads(gzip.decompress((report / "positions.jsonl.gz").read_bytes()))
    if row["id"] != whole_cavity.CASE:
        raise ValueError("cavity score row belongs to another recording")
    proof = report / "comparison.json"
    save_json(proof, comparison(row))
    lock["files"][proof.name] = _sha(proof)
    save_json(receipt, lock)
    truth = references("roof16", [row["id"]])[1][0]["truth"]
    scores = arm_scores(row, truth)
    if row["result"]["status"] == "ok" and any(x["conditional_rms_hz"] is None for x in scores):
        raise ValueError("completed cavity outcome is missing per-arm RF RMS")
    path = report / "scores.csv"
    csv_file(path, scores)
    save_json(
        report / "score-lock.json",
        dict(
            files={path.name: _sha(path)},
            exporter_sha256=_sha(Path(__file__)),
            prediction_lock_sha256=_sha(receipt),
        ),
    )


if __name__ == "__main__":
    export()
