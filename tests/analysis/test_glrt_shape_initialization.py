import numpy as np
import pytest

from leo.analysis.glrt_shape_initialization import shape_seeds
from leo.analysis.sparse_glrt_likelihood import FrequencyEvidence
from leo.analysis.wrapped_glrt_likelihood import circular


def test_track_shapes_recover_offset_modes_without_supplied_satellite_identity():
    times = np.tile(np.linspace(0, 300, 80), 4)
    groups = np.repeat(np.arange(4), 80)
    predictions = np.column_stack(
        (60000 * np.sin(times / 90), -45000 * np.cos(times / 70), 110000 + 1000 * times)
    )
    identity = (np.arange(320) % 80 >= 40).astype(int)
    offsets = np.array([-80000.0, -104000.0, -54000.0, -16000.0])
    drift = np.array([2.0, 1.5])
    y = predictions[np.arange(320), identity] + offsets[groups] + drift[groups // 2] * (times - 150)
    data = FrequencyEvidence(
        tuple(map(str, range(320))),
        y[:, None],
        np.ones((320, 1)),
        np.full(320, 0.95),
        groups,
        times,
    )
    tracks = [np.arange(g * 80 + h * 40, g * 80 + (h + 1) * 40) for g in range(4) for h in range(2)]
    seeds, proposals = shape_seeds(data, predictions, np.ones_like(predictions), tracks)
    assert proposals
    np.testing.assert_allclose(circular(np.array(seeds[0]["beta"][:4]) - offsets), 0, atol=500)
    np.testing.assert_allclose(np.array(seeds[0]["beta"][4:]) / 150, drift, atol=0.02)
    assert set(seeds[0]["active"]) == {0, 1}
    assert all(x["satellite"] != 2 for x in proposals)


def test_shape_seed_rejects_tracks_that_mix_receiver_band_groups():
    groups = np.repeat(np.arange(4), 8)
    data = FrequencyEvidence(
        tuple(map(str, range(32))),
        np.zeros((32, 1)),
        np.ones((32, 1)),
        np.ones(32),
        groups,
        np.arange(32.0),
    )
    with pytest.raises(ValueError, match="one-lane"):
        shape_seeds(data, np.zeros((32, 3)), np.ones((32, 3)), [np.arange(16)])


def test_shape_initialization_fits_ephemeris_phase_without_satellite_labels():
    times = np.tile(np.linspace(0, 300, 80), 4)
    groups = np.repeat(np.arange(4), 80)
    pred = np.column_stack((60000 * np.sin(times / 90), -45000 * np.cos(times / 70)))
    timing = np.column_stack((800 * np.sin(times / 30), 1000 * np.cos(times / 25)))
    identity = (np.arange(320) % 80 >= 40).astype(int)
    offset = np.array([-80000.0, -104000.0, -54000.0, -16000.0])
    phases = np.array([1.0, -1.0])
    y = (pred + timing * phases)[np.arange(320), identity] + offset[groups]
    data = FrequencyEvidence(
        tuple(map(str, range(320))),
        y[:, None],
        np.ones((320, 1)),
        np.full(320, 0.95),
        groups,
        times,
    )
    tracks = [np.arange(g * 80 + h * 40, g * 80 + (h + 1) * 40) for g in range(4) for h in range(2)]
    seeds, _ = shape_seeds(data, pred, np.ones_like(pred), tracks, timing=timing)
    np.testing.assert_allclose(seeds[0]["satellite_phase_s"], phases, atol=0.05)
    assert set(seeds[0]["active"]) == {0, 1}
    with pytest.raises(ValueError, match="timing"):
        shape_seeds(data, pred, np.ones_like(pred), tracks, timing=np.zeros((1, 2)))
