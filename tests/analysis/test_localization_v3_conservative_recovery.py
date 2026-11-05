from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import conservative_recovery as policy


def test_rejection_uses_union_of_both_arms_and_identical_monotone_masks(monkeypatch):
    calls = []
    rows = [dict(component='a'), dict(component='b'), dict(component='c')]
    p = SimpleNamespace(rows=rows, slices=[slice(0, 4), slice(4, 8), slice(8, 12)])

    def fitting(scan, node, keep, arm, **budget):
        calls.append((keep.copy(), arm, budget))
        return p, dict(fit=dict(parameters=arm))

    def gates(p, arm):
        bad = {'a'} if arm == 'c0' else {'b'}
        active = [r for r, sl in zip(rows, p.slices, strict=True) if calls[-1][0][sl].any()]
        return dict(tracks=[dict(r, compatible=r['component'] not in bad) for r in active])

    monkeypatch.setattr(policy, 'causal_fit', fitting)
    monkeypatch.setattr(policy, 'retained_metrics', gates)
    original = np.ones(12, bool)
    _, keep, pair, history, stable = policy.fit_and_gate(None, None, original, 'test')
    assert stable and len(history) == 2 and set(pair) == {'c0', 'fitted_c'}
    assert history[0]['rejected_components'] == ['a', 'b']
    np.testing.assert_array_equal(keep, np.r_[np.zeros(8, bool), np.ones(4, bool)])
    assert original.all()
    for a, b in zip(calls[::2], calls[1::2], strict=True):
        np.testing.assert_array_equal(a[0], b[0])
        assert a[2] == b[2] == dict(rounds=5, iterations=48)


def test_all_rejected_returns_unstable_without_fitting_an_empty_mask(monkeypatch):
    p = SimpleNamespace(rows=[dict(component='a')], slices=[slice(0, 4)])
    monkeypatch.setattr(policy, 'causal_fit', lambda *a, **k:
                        (p, dict(fit=dict(parameters=np.zeros(2)))))
    monkeypatch.setattr(policy, 'retained_metrics', lambda *a:
                        dict(tracks=[dict(component='a', compatible=False)]))
    _, keep, _, history, stable = policy.fit_and_gate(None, None, np.ones(4, bool), 'test')
    assert not stable and keep.all() and len(history) == 1


def test_masked_bad_prefix_is_neither_gated_nor_counted():
    times = np.arange(24.)
    values = np.r_[np.full(12, 1e7), np.zeros(12)]
    track = dict(key='a', times=times, values=values, rf_hz=11.5e9, receiver=1, channel=1,
                 observation_ids=[f'o{i}' for i in range(24)])
    scan = SimpleNamespace(tracks=[track], hardware=lambda *a: np.zeros(24),
                           rx_basis=[np.zeros((24, 1))])
    p = SimpleNamespace(scan=scan, rows=[dict(candidate_index=0, candidate_norad=1)],
        members=[0], slices=[slice(0, 24)], alias=[0], supported=[],
        keep=np.r_[np.zeros(12, bool), np.ones(12, bool)],
        state=lambda x:dict(beta=np.zeros(8), smooth=np.zeros((2, 1))),
        calculate=lambda x:dict(conditional_residual_hz=values),
        conditional_frequency=lambda x:(np.zeros(24), np.ones(24)*30))
    metrics = policy.retained_metrics(p, np.zeros(2))
    assert metrics['accepted_points'] == 12
    row = metrics['tracks'][0]
    assert row['compatible'] and row['observation_ids'] == track['observation_ids'][12:]
    result = policy.coverage([row], [track], set(track['observation_ids']))
    assert result['associated_original_percent'] == 50.
    with pytest.raises(ValueError, match='multiple accepted owners'):
        policy.coverage([row, row], [track], set(track['observation_ids']))
    p.supported = [0]
    p.orbital_owner_gate_families = set()
    assert policy.retained_metrics(p, np.zeros(2))['accepted_points'] == 12
    p.orbital_owner_gate_families = {0}
    assert policy.retained_metrics(p, np.zeros(2))['accepted_points'] == 0


def test_salvage_supports_are_whole_prefix_or_suffix_with_minimum_twelve_points():
    supports = policy.selected_supports(20)
    assert (0, 20) in supports and (0, 12) in supports and (8, 20) in supports
    assert all(b-a >= 12 and (a == 0 or b == 20) for a, b in supports)


def test_salvage_can_replace_a_failed_nominee_using_full_catalogue_evidence(monkeypatch):
    t = np.arange(31.)
    y = 5*t*t
    position = np.zeros((2, len(t), 3))
    position[1, :, 0] = 1
    tracks = [dict(key=str(k), times=t, values=y, rf_hz=11.5e9, receiver=1)
              for k in range(2)]
    scan = SimpleNamespace(tracks=tracks, norads=np.array([101, 202]),
        sky=dict(time_s=t, position_km=position, velocity_km_s=position.copy()),
        rx_basis=[np.zeros((len(t), 1)) for _ in tracks],
        hardware=lambda *a: np.zeros(len(t)),
        search_region=SimpleNamespace(latlon=lambda x:(0., 0.)))
    node = dict(seed=dict(rows=[dict(candidate_index=0, candidate_norad=101) for _ in tracks]),
                aliases=[0, 0])
    p = SimpleNamespace(members=[0, 1], slices=[slice(0, 31), slice(31, 62)],
        rows=node['seed']['rows'], point_noise=np.full(62, 75.),
        state=lambda x:dict(beta=np.zeros(8), smooth=np.zeros((2, 1))))
    monkeypatch.setattr(policy, 'repaired_fit', lambda *a, **kw:
                        (p, dict(parameters=np.zeros(2)), [], []))
    monkeypatch.setattr(policy, 'prepare_phase_geometry', lambda *a: None)
    predicted = np.stack([y+1000*np.sin(t/4), y])
    monkeypatch.setattr(policy, 'phase_linear_frequency', lambda *a:
                        (predicted, np.ones((2, len(t)))*30, np.zeros((2, len(t)))))

    def exact(bank, times, labels, phase, latitude, longitude):
        j = int(bank['position_km'][0, 0, 0])
        return np.tile(predicted[j], len(phase)), np.full(len(times), 30.)

    monkeypatch.setattr(policy, 'paired_phase_frequency', exact)
    keep = np.r_[np.zeros(31, bool), np.ones(31, bool)]
    repaired, retained, diagnostics = policy.salvage(scan, node, keep)
    assert diagnostics[0]['selected']['norad'] == 202
    assert diagnostics[0]['selected']['points'] == 31
    assert diagnostics[0]['candidate_count'] == 2
    assert retained.all() and not keep[:31].any()
    assert repaired['seed']['rows'][0]['candidate_norad'] == 202
    assert node['seed']['rows'][0]['candidate_norad'] == 101
