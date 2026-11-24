"""Join the immutable field component prediction to the later survey labels."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from statistics import median

from public_field_component import DATA, HERE, checked


PREDICTION_SHA = "0522090eec01ecd8cd366d4153ee54fc63bf3d2849d2f430f91d9b8b6ab28a16"
TRUTH_SHA = "f5856336fc6ff308fa3b676db7fab4978fd92476aa2de855271da45b071120b0"


def review(prediction_path, truth_path):
    prediction = json.loads(checked(prediction_path, PREDICTION_SHA))
    truth = json.loads(checked(truth_path, TRUTH_SHA))["cases"]
    matched = [row for row in truth if row["id"] in prediction["offers"]]
    if (len(matched) != 2 or {row["condition"] for row in matched} != {"present", "missing"}
            or len({(row["pair"], row["site_group"]) for row in matched}) != 1):
        raise ValueError("Both original offers must share one independently joined survey label")
    summary = {}
    for row in matched:
        tiles = prediction["offers"][row["id"]]
        if (row["true_region"] in tiles) != (row["condition"] == "present"):
            raise ValueError("The independently joined containing-region label is inconsistent")
        summaries = {tile: median(t["best_centered_rf_rms_hz"] for t in results["tracks"])
                     for tile, results in tiles.items()}
        summary[row["condition"]] = dict(query=row["id"], original_difficulty=row["difficulty"],
                                         containing_tile=row["true_region"], median_minimum_rf_rms_hz=summaries)
    return dict(source="archived StarLoc station GNSS label joined after prediction", prediction_sha256=PREDICTION_SHA,
                survey_label_source_sha256=TRUTH_SHA, site_group=matched[0]["site_group"], offers=summary,
                stable_native_projection=prediction["native_projection_counts"],
                review_sha256=sha256(Path(__file__).read_bytes()).hexdigest())


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--prediction", type=Path, default=HERE / "measurements/public-field-component-prediction.json")
    cli.add_argument("--truth", type=Path, default=DATA / "field_private/truth.json")
    args = cli.parse_args()
    print(json.dumps(review(args.prediction, args.truth), sort_keys=True, indent=2, allow_nan=False))
