from hashlib import sha256

import numpy as np

from tools.pipeline_eval.qualification.association_evidence import inventory
from tools.pipeline_eval.qualification.association_orbit_diagnostic import blocks, elements
from tools.pipeline_eval.qualification.association_v5_phase import PERIOD, radio_residual
from tools.pipeline_eval.variants.robust_em import CORRELATION_S


def test_tle_pair_identity_uses_alpha5_and_hashes_original_pair():
    first = "1 A0001U 25001A   26300.49854360  .00020640  00000-0  75560-3 0  9990"
    second = "2 A0001  42.9894  95.8956 0002076 230.4470 129.6199 15.27660566 46592"
    pair = (first + "\n" + second + "\n").encode()
    ((number, row),) = elements(b"0 STARLINK TEST\n" + pair, 23, "snapshot")
    assert number == 100001
    assert row["sha256"] == sha256(pair).hexdigest()
    assert row["collected_ns"] == 23


def test_selects_longest_disputed_curved_track_by_distinct_native_points():
    trace = {
        "observation": {"tracks": [{"times": [0, 50]}, {"times": [1, 4]}, {"times": [0, 99]}]},
        "banks": [[], [101, 202]],
        "training": [{"owners": [{"track": 0, "orbit": 1}]}],
        "all_associations": [[{"track": 0, "orbit": 0, "loss": 0}]],
        "arcs": [{"index": i, "curved": i < 2} for i in range(3)],
    }
    points = [
        {"graph_track": i, "id": f"{i}:{j}"}
        for i, length in enumerate((2, 3, 7))
        for j in range(length)
    ]
    publication = {"owners": {"c0": {"1:0": 101, "1:1": 101}, "fitted_c": {}}}
    _, selected = inventory(trace, points, publication)
    assert selected["index"] == 1
    assert selected["unique_points"] == 3
    assert selected["joint_pool"] is None


def test_grouped_holdout_keeps_correlated_neighbors_and_intercept_out_of_training():
    t = np.arange(0.0, 1000.0, 0.5)
    train, held, group = blocks(t)
    assert not set(group[train]) & set(group[held])
    assert np.min(abs(t[train, None] - t[held])) > CORRELATION_S
    y = 20 - 2 * PERIOD + np.zeros(len(t))
    y[held] += 70
    scores = radio_residual(y, np.zeros(len(t)), 2, np.zeros(len(t)), train, held)
    assert scores["train_intercept_hz"] == 20
    assert scores["held_rms_after_train_intercept_hz"] == 70
