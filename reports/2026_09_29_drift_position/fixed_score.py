"""Score declared drift allocations at identical published training-fit points."""

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(HERE.parent / "2026_09_29_unassociated_trend"))
import ds7_fast_baseline_adapter as baseline  # noqa: E402
from correction import correct_document  # noqa: E402
from trend_mixture import TrendMixturePosition  # noqa: E402


def read(path):
    return json.loads(path.read_text())


def main(key):
    plan = read(HERE / "fixed-plan.json")
    unit = next(u for u in plan["units"] if u["unit_id"] == key)
    docs = baseline.load_documents({"config": plan["config"], "inputs": unit["group"]["inputs"]})
    assert [d["session_id"] for d in docs] == unit["group"]["session_ids"]
    source = {s["session_id"]: s for s in read(ROOT / plan["coherence"])["scans"]}
    old = read(ROOT / unit["baseline_held"])
    arms = {}
    for arm in plan["arms"]:
        corrected, receipts = [], []
        for doc in docs:
            changed, receipt = correct_document(doc, source[doc["session_id"]], arm)
            corrected.append(changed)
            receipts.extend({**r, "session_id": doc["session_id"]} for r in receipt)
            for a, b in zip(doc["tracks"], changed["tracks"], strict=True):
                np.testing.assert_array_equal(a["mask"], b["mask"])
                np.testing.assert_array_equal(a["times_s"], b["times_s"])
        model = TrendMixturePosition(corrected, plan["config"], baseline.Stationary, 0.2)
        result = model.evaluate(np.asarray(unit["x"]), gradient=True, held=True)
        if arm == "none":
            assert abs(result["score"] - old["training_log_score"]) < 1e-7
            np.testing.assert_allclose(
                result["gradient"], old["full_training_gradient"], rtol=0, atol=1e-7
            )
        assert len(result["rows"]) == len(old["rows"])
        for row, previous in zip(result["rows"], old["rows"], strict=True):
            assert (row["session_id"], row["track_id"]) == (
                previous["session_id"],
                previous["track_id"],
            )
            if arm == "none":
                assert abs(row["held_log_score"] - previous["held_log_score"]) < 1e-7
                np.testing.assert_allclose(
                    row["weights_given_signal"], previous["weights_given_signal"], rtol=0, atol=1e-7
                )
        arms[arm] = {
            "training_log_score": result["score"],
            "gradient": result["gradient"].tolist(),
            "held_log_score": sum(r["held_log_score"] for r in result["rows"]),
            "rows": result["rows"],
            "corrections": receipts,
        }
    output = dict(unit_id=key, x=unit["x"], audit_passed=True, arms=arms)
    with (HERE / "fixed-runs" / key / "result.json").open("x") as f:
        json.dump(output, f, indent=2, allow_nan=False)
    print(key, "baseline replay passed; three allocations scored", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
