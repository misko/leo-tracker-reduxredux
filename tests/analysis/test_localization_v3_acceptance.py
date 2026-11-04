from types import SimpleNamespace

import numpy as np

from leo.analysis.localization_v3 import acceptance
from leo.analysis.localization_v3.position import NormalPosition
from tests.analysis.test_localization_v3_position import prepared


def test_conditional_gate_rejects_structure_even_with_small_rms():
    times = np.arange(80.)
    residual = np.random.default_rng(901).normal(0., 20., len(times))
    assert acceptance.conditional_gate(residual, times)['compatible']
    ramp = residual + 6*(times-times.mean())
    gate = acceptance.conditional_gate(ramp, times)
    assert gate['rms_hz'] < 450 and not gate['compatible']
    assert gate['diagnostics']['slope_z'] > 3
    assert not acceptance.conditional_gate(residual+100, times)['compatible']


def test_owner_support_is_rechecked_after_conditional_and_alias_gates(monkeypatch):
    times = np.arange(40.)
    noise = np.random.default_rng(902).normal(0., 20., len(times))
    tracks = [dict(times=times, receiver=1, channel=i+1) for i in range(3)]
    rows = [dict(component=str(i), candidate_index=0 if i < 2 else 1,
                 compatible=True, native_square_hz2=1., aliases_changed=int(i == 2),
                 points=len(times)) for i in range(3)]
    monkeypatch.setattr(acceptance, 'nominated_metrics', lambda *a, **k: dict(tracks=rows))
    p = SimpleNamespace(scan=SimpleNamespace(tracks=tracks), members=[0, 1, 2],
                        slices=[slice(40*i, 40*(i+1)) for i in range(3)], supported=[0],
                        calculate=lambda x: dict(conditional_residual_hz=np.r_[
                            noise, noise+20*(times-times.mean()), noise]))
    metrics = acceptance.actual_metrics(p, {}, 'c0', np.zeros(2))
    assert metrics['accepted_points'] == metrics['accepted_tracks'] == 0
    assert metrics['tracks'][0]['conditional_residual_gate']['compatible']
    assert not metrics['tracks'][0]['compatible']  # Other owner failed its gate.
    assert not metrics['tracks'][1]['conditional_residual_gate']['compatible']
    assert metrics['tracks'][2]['conditional_residual_gate']['compatible']
    assert not metrics['tracks'][2]['compatible']  # Alias changed.


def test_frozen_extension_never_uses_an_unsupported_receiver_to_calibrate(monkeypatch):
    scan, node = prepared()
    p = NormalPosition(scan, node, 150., False)
    state = p.state(np.zeros(2))
    before = {k: v.copy() if isinstance(v, np.ndarray) else v for k, v in state.items()}
    monkeypatch.setattr(p, 'state', lambda x: state)
    monkeypatch.setattr(acceptance, 'paired_phase_frequency', lambda *a:
                        (np.zeros(len(scan.times)), np.ones(len(scan.times))*30))
    for i in (1, 2):
        t = scan.tracks[i]
        t['values'] = (scan.hardware(t, state['beta'])
                       + t['rf_hz']/11.5e9*scan.rx_basis[i]@state['smooth'][t['receiver']-1])
    curved = dict(component='curved', candidate_index=0, points=41, compatible=True)
    result = acceptance.extend_associations(p, np.zeros(2),
        dict(tracks=[curved], accepted_points=41))
    assert [r['component'] for r in result['tracks']] == ['curved', 'linear']
    assert result['added_points'] == 21
    for key in ('beta', 'smooth', 'phases'):
        np.testing.assert_array_equal(state[key], before[key])
