"""Unblind after recording the prediction digest and export the actual published position PNGs."""
import csv
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path
import sys

from PIL import Image
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from tools.pipeline_eval.scoring import distance_km


def score(work, expected, out):
    prediction = (work / "outputs/blind/predictions.json").read_bytes()
    secret = (work / "scorer/answers.json").read_bytes()
    panel = json.loads(prediction)
    if hashlib.sha256(prediction).hexdigest() != expected or hashlib.sha256(secret).hexdigest() != panel["commitment"]:
        raise ValueError("Prediction or scoring authority changed")
    labels = json.loads(secret)["answers"]
    assert set(labels) == {r["offer"] for r in panel["rows"]}
    rows = []
    store = FastStandardAnalysisStore(work / "outputs/blind")
    for result in panel["rows"]:
        truth = labels[result["offer"]]
        assert truth["recording"] == result["recording"]
        site = truth["truth"]
        center = result["region"]["center"]
        half = result["region"]["width_km"] / 2
        def offset(ll):
            return ((ll[0] - center[0]) * 111.,
                    (ll[1] - center[1]) * 111.32 * math.cos(math.radians(center[0])))
        assert (max(map(abs, offset(site))) <= half) == (truth["condition"] == "containing")
        name = "north" if site[0] > 0 else "south"
        row = dict(site=name, condition=truth["condition"], prior_center_error_km=distance_km(center, site),
                   state=result["decision"], pngs=result["png_count"], run_id=result["run_id"])
        for arm, estimate in result["arms"].items():
            ll = estimate["latlon"]
            row[arm + "_km"] = distance_km(ll, site)
            row[arm + "_rf_rms_hz"] = estimate.get("rf_rms_hz")
            row[arm + "_edge_distance_km"] = None if ll is None else half - max(map(abs, offset(ll)))
        if result["decision"] == "complete":
            img = store.artifact(result["run_id"], "position")
            Image.open(BytesIO(img)).verify()
            (out / (name + "-" + truth["condition"] + ".png")).write_bytes(img)
        rows.append(row)
    with (out / "blind-scores.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: (r["site"], r["condition"])))
    (out / "predictions.json").write_bytes(prediction)
    (out / "scoring-key.json").write_bytes(secret)


if __name__ == "__main__":
    score(Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]))
