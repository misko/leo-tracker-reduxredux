from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3.position import NormalPosition
from tools.pipeline_eval.variants.algo08_endpoint_readout import measured_readout, readout


@pytest.mark.parametrize("reuse", [False, True])
def test_readout_replays_on_coordinate_mask_phase_and_scale_changes(reuse):
    calls = []
    problem = SimpleNamespace(
        reference=np.array([0.5]), keep=np.array([True, True]), phase_sigma=np.array([2.]),
        fitted_c=False, scale_reference=np.array([0.]), scale_labels=[3],
    )

    def original(point):
        calls.append(np.array(point))
        return dict(sum=float(np.sum(point) + problem.reference.sum() + problem.keep.sum()
                              + problem.scale_reference.sum()))

    problem.calculate = original
    point = np.array([0.5, -2.])
    counts = dict(endpoint_calculations=0, repeated_endpoint_calls=0, context_rebuilds=0,
                  other_coordinate_calls=0, unsupported_context_calls=0, endpoint_cpu_s=0.0)
    restore = readout(problem, point, counts, reuse=reuse)
    assert problem.calculate(point)["sum"] == 1.
    assert problem.calculate(point.copy())["sum"] == 1.
    assert problem.calculate(point + 1)["sum"] == 3.
    assert problem.calculate(point)["sum"] == 1.
    problem.keep[0] = False
    assert problem.calculate(point)["sum"] == 0.
    problem.reference[0] = 2.
    assert problem.calculate(point)["sum"] == 1.5
    problem.scale_reference[0] = 0.5
    assert problem.calculate(point)["sum"] == 2.
    assert counts["context_rebuilds"] == 3
    assert counts["other_coordinate_calls"] == 1
    assert counts["repeated_endpoint_calls"] == 2
    assert len(calls) == (5 if reuse else 7)
    restore()
    assert problem.calculate is original


def test_writable_design_and_repeat_optimizer_invalidate_readout(monkeypatch):
    problem = NormalPosition.__new__(NormalPosition)
    problem.hardware = np.array([[2.0, 3.0]])
    problem.smooth = np.array([[0.5, 1.5]])
    calls = []

    def calculate(model, point):
        calls.append(np.asarray(point).copy())
        return float(model.hardware.sum() + model.smooth.sum() + np.sum(point))

    monkeypatch.setattr(NormalPosition, "calculate", calculate)
    monkeypatch.setattr(NormalPosition, "residual", calculate)

    def stock(residual, point):
        assert "calculate" not in vars(residual.__self__)
        return {"parameters": point}

    port = SimpleNamespace(bounded_secant=stock)
    original_point, next_point = np.zeros(2), np.ones(2)
    with measured_readout(port, reuse=True) as counts:
        port.bounded_secant(problem.residual, original_point)
        assert problem.calculate(original_point) == 7.
        assert problem.calculate(original_point) == 7.
        problem.hardware[0, 0] = 3.
        assert problem.calculate(original_point) == 8.
        problem.smooth[0, 1] = 2.
        assert problem.calculate(original_point) == 8.5
        port.bounded_secant(problem.residual, next_point)
        assert problem.calculate(next_point) == 10.5
        assert problem.calculate(next_point) == 10.5
        assert counts["context_rebuilds"] == 2
        assert counts["repeated_endpoint_calls"] == 2
    assert "calculate" not in vars(problem)
    assert port.bounded_secant is stock
    assert len(calls) == 4
