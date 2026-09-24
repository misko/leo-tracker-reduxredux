import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

P = Path(__file__).with_name("run.py")
RESULTS = Path(__file__).with_name("iteration6b-results.json")
POSTSEAL = Path(__file__).parent / "postseal/iteration6b-postseal.json"
S = importlib.util.spec_from_file_location("i6b", P)
M = importlib.util.module_from_spec(S)
S.loader.exec_module(M)


def test_fixed_model_contract():
    assert M.SCALE_BOUND == 0.002
    assert M.MAXITER == 500
    assert M.SCALE_SIGMA > 0 and M.SESSION_DEVIATION_SIGMA > 0


def test_capped_uses_per_observation_track_labels():
    error = np.array([0.0, 800.0, 400.0])
    track = np.array(["a", "a", "b"])
    weights = {"a": 2, "b": 1}

    assert M.capped(error, track, weights) == pytest.approx((2 * 0.5 + 1 * 0.25) / 3)


def test_rejected_nonconvergence_contract():
    results = json.loads(RESULTS.read_text())
    postseal = json.loads(POSTSEAL.read_text())

    assert results["portability_accepted"] is False
    assert all(group["winner"]["converged"] is False for group in results["groups"])
    assert postseal["inference_portability_accepted"] is False
    assert postseal["status"] == "rejected_nonconverged_descriptive_only"
    assert all(row["converged"] is False for row in postseal["rows"])
