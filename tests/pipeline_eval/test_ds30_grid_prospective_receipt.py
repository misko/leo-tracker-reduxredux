import gzip
import json
from hashlib import sha256
from pathlib import Path


MEASUREMENTS = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3/measurements"
SEAL = "sha256:1b88b5875c04f7c935a156f1414131ce4d665c48ea3774a8da4f08e2530aed60"
COMBINED = "sha256:b643da0eb77c87ae89aa1b9b285dfde3e8abb3404271608a821458abdb86ff22"
CASES = ["DS30-0010", "DS30-0444", "DS30-0073"]


def transfer(study):
    prediction_body = gzip.decompress((MEASUREMENTS / f"ds30-grid-{study}-next3-prediction.json.gz").read_bytes())
    prediction = json.loads(prediction_body)
    with gzip.open(MEASUREMENTS / f"ds30-grid-{study}-next3-scored.json.gz", "rt") as receipt:
        score = json.load(receipt)
    assert score["prediction"] == "sha256:" + sha256(prediction_body).hexdigest()
    assert prediction["cohort"] == score["cohort"] == "next3"
    assert prediction["pins"]["seal"] == SEAL
    assert prediction["pins"]["combined_export"] == COMBINED
    assert [row["case"] for row in prediction["rows"]] == CASES
    assert all(row["state"] == "bound" for row in prediction["rows"])
    return prediction, score


def test_prospective_transfers_bind_each_score_to_same_three_frozen_products():
    axes, axis_score = transfer("axis")
    curvature, curvature_score = transfer("triage")
    assert axis_score["reference"] == curvature_score["reference"]
    for a, b in zip(axes["rows"], curvature["rows"], strict=True):
        assert (a["pair"], a["candidate"], a["grid_sha256"]) == (b["pair"], b["candidate"], b["grid_file_sha256"])
    assert list(axis_score["outcomes"]) == CASES
    assert all(row["status"] == "matched" for row in axis_score["outcomes"].values())
    assert curvature_score["policy"]["retried"] == CASES
    for arm in ("c0", "fitted_c"):
        assert axis_score["to_installed"][arm]["candidate"]["n"] == 3
        assert curvature_score["rank"][arm]["n"] == 3
