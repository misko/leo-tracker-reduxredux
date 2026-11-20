import json

import pytest

from tools.pipeline_eval.variants import v5_causal_orbit_fit as candidate
from tools.pipeline_eval.variants import v5_secant_fit


def test_serial_layers_keep_one_frozen_fit_and_nest_in_order():
    events = []

    def layer(name):
        def enter(request, result, library):
            events.append(name)
            response = v5_secant_fit.worker(request, result, library, "secant")
            events.append("leave " + name)
            return response

        return enter

    def base(request, result, library, objective):
        events.append("compact fit")
        assert (request, result, library, objective) == ("request", "result", "library", "secant")
        return "both calibration arms"

    pinned_worker = v5_secant_fit.worker
    composed = candidate.compose(tuple(map(layer, candidate.RECEIPTS)), base)
    assert composed("request", "result", "library") == "both calibration arms"
    assert events == [*candidate.RECEIPTS, "compact fit",
                      *("leave " + name for name in reversed(candidate.RECEIPTS))]
    assert v5_secant_fit.worker is pinned_worker


@pytest.mark.parametrize("mode", ["secant", "reference"])
def test_nested_dispatch_restores_original_on_unrecognized_fault(mode):
    pinned_worker = v5_secant_fit.worker

    def pass_through(request, result, library):
        return v5_secant_fit.worker(request, result, library, mode)

    def bad_current(*_):
        raise ValueError("invalid current orbit")

    execute = candidate.compose((pass_through, pass_through), bad_current)
    with pytest.raises(ValueError, match="invalid current orbit" if mode == "secant" else
                       "requires the measured compact secant objective"):
        execute(None, None, None)
    assert v5_secant_fit.worker is pinned_worker


def test_incomplete_guard_receipts_fail_closed(monkeypatch, tmp_path):
    def delegated(request, result, library):
        v5_secant_fit.worker(request, result, library, "secant")

    def receipt(_request, result, _library, _mode):
        result.write_text(json.dumps(dict(metrics=dict(orbit_support={}, previous_orbit={}))))

    for module in (candidate.v5_orbit_domain, candidate.v5_previous_orbit,
                   candidate.v5_cavity_isolation):
        monkeypatch.setattr(module, "worker", delegated)
    monkeypatch.setattr(v5_secant_fit, "worker", receipt)
    with pytest.raises(ValueError, match="lacks a measured guard receipt"):
        candidate.worker(None, tmp_path / "position.json", None)
