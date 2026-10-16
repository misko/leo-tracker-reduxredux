from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.shared_scan_model import SharedScanObjective
from leo.application.shared_orbit_replay import orbit_lanes, selected_model
from tests.analysis import test_shared_scan_model as fixtures

actual_case, family = fixtures.actual_case, fixtures.family


def test_lanes_preserve_every_observation_and_full_shared_calibration(family, monkeypatch):
    raw, v, n, shift = family
    model = SharedScanObjective(raw, shift)
    fit = dict(vector=v, nuisance=np.r_[n, np.full(model.observation_parameter_count, .2)])
    # Dense rendering support is separate from the original likelihood bank.
    import leo.application.shared_orbit_replay as module
    monkeypatch.setattr(module, 'predict_orbits', lambda bank, obs, *a, **k:
                        (np.zeros((len(obs.times_s), len(bank.numbers))),
                         np.ones((len(obs.times_s), len(bank.numbers)), bool), None, None))
    lanes, info = orbit_lanes(model, fit, model.bank)
    points = {p.peak_id: p for lane in lanes for p in lane.peaks}
    obs = raw.observations
    assert len(points) == len(obs.window_ids)
    correction = raw.correction(v, n)
    terms = model.evaluate_joint(v, fit['nuisance'])[3]
    for i, key in enumerate(obs.window_ids):
        assert points[key].frequency_hz == pytest.approx(obs.measured_hz[i] - correction[i])
        j = terms.responsibilities[i].argmax()
        expected = str(model.bank.numbers[j]) if terms.responsibilities[i, j] > terms.clutter_probability[i] else None
        assert points[key].satellite_id == expected
    assert info['replayed_likelihood_nll'] == terms.nll
    assert info['associated'] + info['unassociated'] == len(points)


def test_selected_b_reconstruction_keeps_frozen_contrast_and_rejects_changed_fit(family, monkeypatch):
    import leo.application.shared_orbit_replay as module
    raw, v, n, shift = family
    monkeypatch.setattr(module, 'objective', lambda *a: SimpleNamespace())
    monkeypatch.setattr(module, 'donor_state', lambda *a: (raw, shift, v, n, 0))
    monkeypatch.setattr(module, 'audit_endpoint', lambda *a: dict(
        accepted=True, objective=123., likelihood_nll=100.))
    fit = dict(vector=v.tolist(), nuisance=n.tolist())
    terminal = dict(selection=dict(source='B-all', call='shared-all-B-all', objective=123., NLL=100.), selected_fit=fit)
    stages = {'source-selection': {'B_index': 2}, 'B-2': {'result': {'audit': {'accepted': True}, 'fit': {}}},
              'shared-all-B-all': {'result': {'fit': fit.copy(), 'audit': {'accepted': True}, 'options': {}}}}
    model, _, _ = selected_model({'all': None}, None, None, None, terminal, stages)
    np.testing.assert_array_equal(model.original.baseline, raw.baseline)
    terminal['selected_fit'] = dict(vector=[])
    with pytest.raises(ValueError, match='endpoint differs'):
        selected_model({'all': None}, None, None, None, terminal, stages)
