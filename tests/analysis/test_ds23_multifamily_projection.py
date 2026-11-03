from types import SimpleNamespace

import numpy as np
import pytest

import probe_ds23_multifamily_projection as driver


def test_projection_finds_nearest_original_gate_feasible_position_and_stable_prediction(monkeypatch):
    def make(scan, node, keep, arm, reference, powers, means, model, events):
        p = SimpleNamespace(reference=np.asarray(reference), labels=[0],
            lower=np.array([-12.5, -12.5]), upper=np.array([12.5, 12.5]))
        p.calculate = lambda x: dict(negative_twice_elbo=10.)
        def state(x):
            p.calculate(x)
            return dict(phases=np.zeros(1))
        p.state = state
        return p

    def attach(p, entries, powers):
        curved = p.calculate
        def calculate(x):
            c = curved(x)
            c['negative_twice_elbo'] += 5.
            return c
        p.calculate = calculate

    def summary(p, x, entries):
        assert p.calculate(x)['negative_twice_elbo'] == 15.
        assert p.calculate(x)['negative_twice_elbo'] == 15.
        return dict(endpoint_east_north_km=x)

    monkeypatch.setattr(driver, 'make_event_problem', make)
    monkeypatch.setattr(driver, 'attach_event_predictive', attach)
    monkeypatch.setattr(driver, 'summary', summary)
    monkeypatch.setattr(driver, 'gate_slacks', lambda p, x, e: {'original_gate': .4-x[0]})
    result = driver.project(None, None, np.ones(1, bool), 'c0',
        dict(endpoint_east_north_km=[1., 0.], phase_reference=[0.]),
        np.ones(1), np.zeros(1), {}, [{}])
    x = np.asarray(result['endpoint_east_north_km'])
    assert x[0] == pytest.approx(.39, abs=3e-5)
    assert x[1] == pytest.approx(0., abs=.001)
    assert result['displacement_from_RF_candidate_km'] == pytest.approx(.61, abs=3e-5)
    assert result['minimum_gate_slack'] >= .01
    assert result['final_phase_change_s'] == 0.
