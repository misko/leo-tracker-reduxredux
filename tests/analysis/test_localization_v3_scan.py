import numpy as np
import pytest

from leo.analysis.localization_v3.scan import ScanLikelihood, group, perturb
from leo.analysis.research.retained_track_likelihood import PERIOD
from leo.sky.propagation import parse_element_sets
from tests.operations.test_causal_tle_catalogue import at_day


def example():
    curved_times = np.arange(41.)
    linear_times = np.arange(60., 81.)
    tracks = [dict(key='curved', receiver=1, channel=1, rf_hz=11.5e9,
                   times=curved_times, values=100000-700*curved_times+4*curved_times**2),
              dict(key='linear', receiver=1, channel=2, rf_hz=11.5e9,
                   times=linear_times, values=50000-500*linear_times),
              dict(key='other_rx', receiver=2, channel=2, rf_hz=11.5e9,
                   times=linear_times, values=50000-500*linear_times)]
    t = np.arange(-17., 319.)
    p = np.column_stack((np.full(len(t), 6878.), 7*t, np.zeros(len(t))))[None]
    v = np.broadcast_to([0., 7., 0.], p.shape).copy()
    bank = dict(time_s=t, position_km=p, velocity_km_s=v, norad=np.array([44714]),
                phase_sigma_s=np.ones(1))
    scan = ScanLikelihood(tracks, bank, {}, origin_utc_ns=0, regional_center=[0., 0.],
                          noise=dict(constant_radio_sigma_hz=150.))
    f = np.concatenate((tracks[0]['values'], tracks[1]['values']))[None]
    base = f, np.ones_like(f)*30., np.zeros_like(f)
    state = dict(beta=np.zeros(8), phases=np.zeros(1), extra={},
                 smooth=np.zeros((2, scan.rx_basis[0].shape[1])))
    return scan, tracks, bank, state, base


def test_linear_tracks_receive_only_independently_supported_calibration():
    scan, _, _, state, base = example()
    _, rows, _, _ = scan.association(state, base, [0., 0.], 'shared_phase', all_tracks=True)
    assert [(r['component'], r['compatible']) for r in rows] == [
        ('curved', True), ('linear', True), ('other_rx', False)]
    assert scan.curved == [0]


def test_below_horizon_and_structured_residuals_are_rejected():
    scan, _, _, state, base = example()
    below = base[0], -base[1], base[2]
    _, rows, _, _ = scan.association(state, below, [0., 0.], 'shared_phase')
    assert not rows[0]['compatible']
    track = scan.tracks[0]
    ramp = 20*(track['times']-track['times'].mean())
    result = scan.curve(0, track['values'], track['values']-ramp, 'shared_phase')
    assert result['rms'][0] < 450
    assert not result['passing'][0]


def test_alias_and_input_ownership_preserved():
    scan, tracks, bank, state, base = example()
    scan.tracks[0]['values'] += PERIOD
    _, rows, nominated, _ = scan.association(state, base, [0., 0.], 'shared_phase')
    assert rows[0]['compatible']
    assert nominated[0]['terms']['alias'][0] == -1
    assert not np.array_equal(scan.tracks[0]['values'], tracks[0]['values'])
    bank['position_km'][:] = 0
    assert scan.sky['position_km'].any()


@pytest.mark.parametrize('receiver,channel,expected', [(1, 1, 0), (1, 8, 1),
                                                      (2, 1, 2), (2, 8, 3)])
def test_receiver_band_drift_and_rf_coefficient(receiver, channel, expected):
    scan, _, _, _, _ = example()
    track = dict(receiver=receiver, channel=channel, times=np.array([0., 150., 300.]),
                  rf_hz=12e9)
    beta = np.arange(1., 10.)
    assert group(track) == expected
    np.testing.assert_array_equal(scan.hardware(track, beta[:8]),
        beta[expected]+beta[expected+4]*np.array([-1., 0., 1.]))
    np.testing.assert_array_equal(scan.hardware(track, beta),
        scan.hardware(track, beta[:8])+4.5)


def test_orbit_perturbation_preserves_split_epoch_and_mean_argument():
    satellite = parse_element_sets(at_day(232)).satellites[0]
    changed = perturb(satellite, 'e_cos_omega', 2e-5)
    assert (changed.jdsatepoch, changed.jdsatepochF) == (
        satellite.jdsatepoch, satellite.jdsatepochF)
    assert changed.ecco != satellite.ecco
    assert (changed.mo+changed.argpo) % (2*np.pi) == pytest.approx(
        (satellite.mo+satellite.argpo) % (2*np.pi), abs=1e-15)
