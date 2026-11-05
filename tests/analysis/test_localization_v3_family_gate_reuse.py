"""Single-family orbit replay retains every original gate and diagnostic."""

from types import SimpleNamespace

import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import recovery_gates as gates
from leo.analysis.research.retained_track_likelihood import whitening


def problem(monkeypatch, fitted_c, linear):
    rng = np.random.default_rng(2971)
    tracks = [dict(key=f'track-{i}', times=np.linspace(10, 80, n),
                   values=rng.normal(0, 120, n), rf_hz=11.5e9,
                   receiver=i % 2 + 1, channel=i + 1)
              for i, n in enumerate([12, 17, 9, 13, 15])]
    # A failing unchanged family's conditional residual must not disappear.
    residual = np.concatenate([rng.normal(0, 90, 12), np.full(17, 3000.), np.zeros(9)])
    c = dict(conditional_residual_hz=residual, coefficient=np.zeros(12),
             linear_raw_prediction_residual_hz=np.zeros(28), linear_elevation=np.ones(28))
    frequency, elevation = np.zeros(38), np.full(38, 25.)
    scan = SimpleNamespace(tracks=tracks, rx_basis=[np.zeros((len(t['times']), 1))
                                                  for t in tracks],
                           white=[whitening(t['times']) for t in tracks],
                           hardware=lambda t, beta: np.zeros(len(t['times'])))
    p = SimpleNamespace(scan=scan, calculate=lambda x: c,
                        conditional_frequency=lambda x: (frequency, elevation),
                        state=lambda x: dict(beta=np.zeros(8 + fitted_c),
                                             smooth=np.zeros((2, 1))),
                        keep=np.r_[np.ones(12, bool), np.ones(17, bool), np.zeros(9, bool)],
                        rows=[dict(candidate_index=j) for j in [0, 1, 2]],
                        members=[0, 1, 2], slices=[slice(0, 12), slice(12, 29), slice(29, 38)],
                        alias=[0, 0, 0], supported=[0, 1], labels=[0, 1, 2],
                        q=np.ones(38), hardware=np.zeros((38, 8 + fitted_c)),
                        smooth=np.zeros((38, 0)))
    entries = [dict(track_index=i, candidate_index=j, component=tracks[i]['key'])
               for i, j in [(3, 0), (4, 3)]] if linear else []
    p.linear_slices = [slice(0, 13), slice(13, 28)] if linear else []
    monkeypatch.setattr(gates, 'family_frequency', lambda p, x, j, times:
                        (np.sin(times) * 20 + 40 * j, np.full(len(times), 20. - 10 * j)))
    monkeypatch.setattr(gates, 'linear_geometry', lambda p, e:
                        (SimpleNamespace(q=np.ones(len(tracks[e[0]['track_index']]['times']))),))
    monkeypatch.setattr(gates, 'geometry_features', lambda view, x, phase:
                        dict(intercept=np.zeros(len(view.q)), features=np.zeros((len(view.q), 12))))
    return p, entries


@pytest.mark.parametrize('fitted_c', [False, True])
@pytest.mark.parametrize('linear', [False, True])
def test_reuse_matches_full_replay_including_failing_unaffected_gates(
        monkeypatch, fitted_c, linear):
    p, entries = problem(monkeypatch, fitted_c, linear)
    x = np.array([1., -2.])
    base = gates.gate_slacks(p, x, entries)
    before = fingerprint((base, p.calculate(x), p.conditional_frequency(x)))
    for family in [0, 1, 2, 3]:
        p.explicit_phase_family = family
        expected = gates.exact_gate_replay(p, x, entries)
        actual = gates.exact_gate_replay(p, x, entries, base_slacks=base)
        assert fingerprint(actual) == fingerprint(expected)
        assert list(actual['all_gate_slacks']) == list(expected['all_gate_slacks'])
        assert not actual['all_pass']
    assert fingerprint((base, p.calculate(x), p.conditional_frequency(x))) == before


def test_partial_gate_calculation_visits_only_selected_family(monkeypatch):
    p, entries = problem(monkeypatch, True, True)
    expected = gates.gate_slacks(p, np.zeros(2), entries)
    visits = []
    original = gates.noise_slacks

    def count(residual, times):
        visits.append(len(times))
        return original(residual, times)

    monkeypatch.setattr(gates, 'noise_slacks', count)
    actual = gates.gate_slacks(p, np.zeros(2), entries, family=0)
    assert visits == [12, 13]  # profile plus predictive; conditional is a separate helper
    assert actual == {k: v for k, v in expected.items()
                      if k.startswith(('track-0/', 'track-3/')) or k == 'support/0'}


def test_reuse_restores_problem_when_selected_family_gate_fails(monkeypatch):
    p, entries = problem(monkeypatch, False, True)
    x = np.zeros(2)
    base = gates.gate_slacks(p, x, entries)
    calculate, frequency = p.calculate, p.conditional_frequency
    p.explicit_phase_family = 0

    def fail(*args, **kwargs):
        assert kwargs['family'] == 0
        raise RuntimeError('selected-family gate failed')

    monkeypatch.setattr(gates, 'gate_slacks', fail)
    with pytest.raises(RuntimeError, match='selected-family gate failed'):
        gates.exact_gate_replay(p, x, entries, base_slacks=base)
    assert p.calculate is calculate and p.conditional_frequency is frequency
