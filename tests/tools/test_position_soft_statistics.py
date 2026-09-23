import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np


def m():
    p = Path(__file__).parents[2] / "tools/research/position_soft_statistics.py"
    s = importlib.util.spec_from_file_location("x", p)
    x = importlib.util.module_from_spec(s)
    s.loader.exec_module(x)
    return x


def p(pred, visible=(True, True), y=(0, 0, 1, 1)):
    return SimpleNamespace(
        measured_hz=np.array(y, float),
        training_mask=np.array([1, 1, 0, 0], bool),
        predictions_hz=np.array(pred, float),
        visible=np.array(visible),
    )


def test_heldout_does_not_change_training_posterior():
    x = m()
    a = p([[[0, 0, 0, 0]], [[10, 10, 10, 10]]])
    b = p([[[0, 0, 9, 9]], [[10, 10, 9, 9]]], y=(0, 0, 99, 99))
    assert np.allclose(x.track_statistics(a)["posterior"], x.track_statistics(b)["posterior"])


def test_strong_and_ambiguous():
    x = m()
    strong = x.track_statistics(p([[[0, 0, 0, 0]], [[1000, -1000, 0, 0]]]))
    amb = x.track_statistics(p([[[0, 0, 0, 0]], [[0, 0, 0, 0]]]))
    assert strong["entropy_nats"] < amb["entropy_nats"]


def test_invisible_keeps_null_finite():
    x = m()
    z = x.track_statistics(p([[[0, 0, 0, 0]], [[0, 0, 0, 0]]], (False, False)), True)
    assert (
        z["full_support"] == 2
        and z["visible_support"] == 0
        and z["null_probability"] == 1
        and np.isfinite(z["soft_reserved_mse_hz2"])
    )
