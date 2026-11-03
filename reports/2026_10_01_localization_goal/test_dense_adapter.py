from dataclasses import replace
from types import SimpleNamespace

import numpy as np
from dense_adapter import dense_ports
from physics import StateLayout
from test_acquisition_dot import fixture


def test_denser_ports_preserve_raw_track_and_acquisition_config():
    track, bank, config, height, _ = fixture(lambda e, n: .03)
    track = replace(track, observation_ids=tuple(f'point{i}' for i in range(16)),
                    times_s=np.arange(16.), frequencies_hz=np.arange(16.)*20,
                    receiver_indices=np.zeros(16, dtype=int))
    scan = SimpleNamespace(config=config, tracks=[('track', track)], bank=bank,
                           layout=StateLayout(bank.norad_ids))
    coarse = dense_ports(scan, height, 8)[0]
    dense = dense_ports(scan, height, 16)[0]
    assert scan.config.max_points == 8
    assert len(coarse.observation_ids) == 8
    assert dense.observation_ids == track.observation_ids
    assert len(set(dense.observation_ids)) == 16
    state = np.zeros(7)
    pred = dense.predict_selected(state, 0)
    assert pred.mean.shape == (15,)
    assert pred.covariance.shape == (15, 15)
    np.testing.assert_array_equal(dense.score_all(state), dense.score_all(state.copy()))
