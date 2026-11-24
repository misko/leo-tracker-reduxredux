import importlib
from pathlib import Path

import pytest


@pytest.fixture
def load(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))
    return importlib.import_module("eight_ms_held_fit"), importlib.import_module("eight_ms_held_score")


def test_fixed_8ms_route_refuses_the_wrong_measurement_policy(load):
    worker, _ = load
    with pytest.raises(ValueError, match="unrefined measured 20/8 ms"):
        worker.select({}, {"aperture_samples": [200_000, 120_000]})
    with pytest.raises(ValueError, match="unrefined measured 20/8 ms"):
        worker.select({}, {"aperture_samples": [200_000, 80_000], "fixed_epoch_cfo_refinement": {}})


def test_omitted_admission_requires_both_errors_and_elapsed_to_pass(load):
    _, score = load
    baseline = dict(status="fix", elapsed_s=5., arms={"c0": {"error_km": 1.}, "fitted_c": {"error_km": 2.}})
    assert score.eligible(baseline, dict(baseline, elapsed_s=4.9))
    assert not score.eligible(baseline, baseline)
    assert not score.eligible(baseline, dict(baseline, elapsed_s=4., status="withheld"))
    changed = dict(baseline, elapsed_s=4., arms=baseline["arms"] | {"fitted_c": {"error_km": 2.01}})
    assert not score.eligible(baseline, changed)
