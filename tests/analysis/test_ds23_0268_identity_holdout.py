from types import SimpleNamespace

import numpy as np

from ablate_ds23_frequency_event_satellites import removal_mask
from probe_ds23_0268_identity_holdout import calibrated_values
from probe_ds23_0268_selected_identity_split import split_rx1_predictive


def test_event_corrected_identity_probe_preserves_physical_curve():
    times = np.array([0., 1., 2., 3.])
    curve = 20. + times**2
    step = 240. * (times >= 2.)
    smooth = np.array([[2.], [3.], [4.], [5.]])
    track = dict(times=times, receiver=2, rf_hz=23e9,
                 values=curve + 17. + step + 2. * smooth[:, 0] * 6.)
    # The event-aware view must remove the common receiver step as well as
    # the frequency-scaled smooth term before candidate shapes are compared.
    scan = SimpleNamespace(tracks=[track], rx_basis=[smooth],
        hardware=lambda t, beta: beta[0] + beta[1] * (t['times'] >= 2.))
    state = dict(beta=np.array([17., 240.]), smooth=np.array([[99.], [6.]]))
    np.testing.assert_allclose(calibrated_values(SimpleNamespace(scan=scan), state, 0), curve)


def test_family_holdout_excludes_both_curved_and_predictive_evidence():
    rows = [dict(candidate_norad=53923, component='RX1-A'),
            dict(candidate_norad=12345, component='control'),
            dict(candidate_norad=53923, component='RX2-B')]
    original = np.array([1, 1, 1, 0, 1, 1], bool)
    entries = [dict(norad=53923, component='linear-A'),
               dict(norad=12345, component='linear-control')]
    keep, predictive = removal_mask(rows, [slice(0, 2), slice(2, 4), slice(4, 6)],
                                    original, entries, norads=(53923,))
    np.testing.assert_array_equal(keep, [0, 0, 1, 0, 0, 0])
    np.testing.assert_array_equal(original, [1, 1, 1, 0, 1, 1])
    assert predictive == [entries[1]]


def test_receiver_identity_split_preserves_predictive_measurements_and_other_families():
    entries = [dict(norad=n, candidate_index=j, track_index=i, observation_ids=[str(i)])
               for i, (n, j) in enumerate([(53923, 4), (53923, 4), (12345, 9)])]
    tracks = [dict(receiver=1), dict(receiver=2), dict(receiver=1)]
    changed = split_rx1_predictive(entries, tracks, 12)
    assert [(e['norad'], e['candidate_index']) for e in changed] == [(67953, 12), (53923, 4), (12345, 9)]
    assert [e['observation_ids'] for e in changed] == [e['observation_ids'] for e in entries]
    assert entries[0]['norad'] == 53923
