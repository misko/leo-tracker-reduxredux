from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_differential_frame_phase import unique_frame_intersections, project_channel_phase, heldout_phase_frequency


def test_frame_matching_never_counts_one_transmitter_frame_twice():
    first = {'frame': np.array([0]*10+[1]*10+[2]*10)}
    second = {'frame': np.array([0]*6+[1]*10+[2]*10+[3]*4)}
    segments = [np.arange(a, b) for a, b in [(0, 6), (6, 10), (10, 16), (16, 20), (20, 26), (26, 30)]]
    selected = unique_frame_intersections(first, second, segments)
    assert len(selected) == 3
    for source in [first, second]:
        labels = [source['frame'][s[0]] for s in selected]
        assert len(labels) == len(set(labels))
    assert sum(map(len, selected)) == 18


def test_training_channel_projection_does_not_learn_heldout_channel():
    rng = np.random.default_rng(819)
    channel = rng.normal(size=8)+1j*rng.normal(size=8)
    gain = np.exp(1j*np.arange(15)*.3); c = gain[:, None]*channel
    cov = np.broadcast_to(np.eye(8), (15, 8, 8))
    a = project_channel_phase(c, cov, 10)
    c[10:] = rng.normal(size=(5, 8))+1j*rng.normal(size=(5, 8))
    b = project_channel_phase(c, cov, 10)
    np.testing.assert_allclose(a['gain'][:10], b['gain'][:10])
    assert a['training_rank_one_energy_fraction'] == pytest.approx(1.)


def test_shared_random_phase_cancels_in_differential_heldout_prediction():
    rng = np.random.default_rng(772)
    t = np.arange(15)/750; common = np.exp(1j*rng.uniform(-np.pi, np.pi, len(t)))
    a = common*np.exp(2j*np.pi*12*t); b = common*np.exp(-2j*np.pi*8*t)
    result = heldout_phase_frequency(t, a*b.conj(), np.ones(len(t)), 10, controls=128, seed=91)
    assert result['continuity_score'] > .999
    assert result['candidate_for_independent_replication']
    assert result['harmonics'][0]['residual_frequency_hz'] == pytest.approx(20.)
    single = heldout_phase_frequency(t, a, np.ones(len(t)), 10, controls=128, seed=91)
    assert single['continuity_score'] < .85


def test_independent_phase_resets_do_not_imply_continuity():
    rng = np.random.default_rng(300)
    t = np.arange(15)/750; z = np.exp(1j*rng.uniform(-np.pi, np.pi, len(t)))
    result = heldout_phase_frequency(t, z, np.ones(len(t)), 10, controls=128, seed=22)
    assert not result['candidate_for_independent_replication']


def test_zero_gain_is_rejected_instead_of_creating_a_phase():
    with pytest.raises(ValueError):
        heldout_phase_frequency(np.arange(15), np.zeros(15), np.ones(15), 10)
