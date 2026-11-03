from types import SimpleNamespace
import numpy as np

from ds23_disjoint_rf_calibration import exclude_probes


def test_every_RX_and_secondary_peak_from_the_calibration_probe_is_removed():
    tracks = [dict(channel=2, rf_hz=11e9, times=np.array([0., 1., 2., 3., 4.]),
        observation_ids=[f'rx{r}-{k}' for k in range(5)]) for r in [1, 2, 3]]
    tracks[2]['times'] = np.array([0., 1., 2., 3., 4.])
    scan = SimpleNamespace(tracks=tracks)
    base = SimpleNamespace(members=[0, 2], slices=[slice(0, 5), slice(5, 10)])
    original = np.ones(10, bool)
    entries = [dict(track_index=1, observation_ids=tracks[1]['observation_ids'], points=5)]
    changed, predictive, receipt = exclude_probes(scan, base, original, entries,
        [dict(channel=2, rf_hz=11e9, time_s=2.)])
    assert original.all()
    assert changed.sum() == 8
    assert not changed[2] and not changed[7]
    assert predictive[0]['points'] == 4
    assert 'rx2-2' not in predictive[0]['observation_ids']
    assert set(receipt['excluded_probe_graph_ids']) == {'rx1-2', 'rx2-2', 'rx3-2'}


def test_same_time_on_another_channel_is_not_reused_IQ():
    track = dict(channel=3, rf_hz=11e9, times=np.array([0., 1., 2., 3.]), observation_ids=['a','b','c','d'])
    scan = SimpleNamespace(tracks=[track])
    base = SimpleNamespace(members=[0], slices=[slice(0, 4)])
    changed, _, receipt = exclude_probes(scan, base, np.ones(4, bool), [],
        [dict(channel=2, rf_hz=11e9, time_s=2.)])
    assert changed.all() and receipt['excluded_probe_graph_ids'] == []
