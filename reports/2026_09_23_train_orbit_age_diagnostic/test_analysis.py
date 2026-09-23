import importlib.util
from pathlib import Path

import numpy as np

PATH = Path(__file__).with_name("analyze.py")
SPEC = importlib.util.spec_from_file_location("train_orbit_age_analyze", PATH)
ANALYZE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYZE)


def test_demean_removes_each_stratum_mean_without_pooling_strata():
    values = np.array([1.0, 3.0, 10.0, 14.0, 18.0])
    labels = np.array(
        [
            "first|lane-a|EN",
            "first|lane-a|EN",
            "second|lane-b|WS",
            "second|lane-b|WS",
            "second|lane-b|WS",
        ]
    )
    result = ANALYZE.demean(values, labels)
    for label in set(labels):
        np.testing.assert_allclose(np.mean(result[labels == label]), 0.0, atol=1e-12)
    np.testing.assert_allclose(result, [-1.0, 1.0, -4.0, 0.0, 4.0])
