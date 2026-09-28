import copy
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).parents[2] / "tools"))
from ds7_pooled_receiver_slope import PooledReceiverSlope
from ds7_slope_identifiability import evaluate


class Prediction:
    def __init__(self, document, config):
        self.document = document

    def prediction(self, track, point):
        t = (track["times_s"] - 30) / 10
        columns = np.array([100 * t * t, 80 * t * t * t, 50 * np.sin(t + self.document["phase"])])
        return (point @ columns)[None, :], np.array([True])


def example():
    truth = np.array([0.2, -0.3, 0.4, -0.1, 2.0, -1.0])
    documents = []
    for i in range(2):
        d = {"phase": i * 0.4, "tracks": []}
        model = Prediction(d, {})
        for rx in (0, 1):
            t = np.linspace(0, 60, 24)
            track = {
                "track_id": f"{i}-{rx}",
                "times_s": t,
                "mask": np.arange(24) % 3 != 2,
                "receiver_id": rx,
                "rf_hz": 11_200_000_000.0,
                "catalogue_size": 1,
            }
            track["y"] = (
                model.prediction(track, truth[[0, 1, i + 2]])[0][0] + truth[4 + rx] * t + 500
            )
            d["tracks"].append(track)
        documents.append(d)
    return documents, truth


def test_pooled_gradient_and_training_isolation():
    documents, truth = example()
    model = PooledReceiverSlope(documents, {}, Prediction)
    point = truth + np.array([0.01, 0.02, -0.03, 0.01, 0.02, -0.01])
    result = model.evaluate(point)
    for i in range(6):
        step = np.eye(6)[i] * 1e-4
        numerical = (
            model.evaluate(point + step)["score"] - model.evaluate(point - step)["score"]
        ) / 2e-4
        assert result["gradient"][i] == pytest.approx(numerical, abs=1e-4)
    changed = copy.deepcopy(documents)
    for d in changed:
        for t in d["tracks"]:
            t["y"][~t["mask"]] += 1e5
    other = PooledReceiverSlope(changed, {}, Prediction).evaluate(point)
    assert other["score"] == result["score"]
    assert np.array_equal(other["gradient"], result["gradient"])


def test_zero_slopes_equal_original_document_sum():
    documents, truth = example()
    model = PooledReceiverSlope(documents, {}, Prediction)
    point = truth.copy()
    point[-2:] = 0
    score = sum(
        evaluate(d["tracks"], Prediction(d, {}).prediction, np.r_[point[[0, 1, i + 2]], 0])["score"]
        for i, d in enumerate(documents)
    )
    assert model.evaluate(point)["score"] == pytest.approx(score, abs=1e-10)


def test_identifiable_synthetic_position_and_receiver_slopes_recover():
    documents, truth = example()
    model = PooledReceiverSlope(documents, {}, Prediction)

    def objective(x):
        value = model.evaluate(x)
        return -value["score"], -value["gradient"]

    fit = minimize(
        objective,
        np.zeros(6),
        jac=True,
        method="L-BFGS-B",
        options={"maxiter": 150, "ftol": 1e-14, "gtol": 1e-7},
    )
    assert fit.success
    assert np.max(np.abs(fit.x - truth)) < 1e-4
    documents[0]["tracks"][0]["receiver_id"] = 3
    with pytest.raises(ValueError):
        PooledReceiverSlope(documents, {}, Prediction)
