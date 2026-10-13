import numpy as np
import pytest

from leo.analysis.glrt_bias_initialization import bias_shape_seed
from leo.analysis.sparse_glrt_likelihood import FrequencyEvidence


def test_source_bias_start_keeps_receiver_offsets_and_recovers_large_bias_without_labels():
    time = np.tile(np.linspace(0, 300, 80), 4)
    group = np.repeat(np.arange(4), 80)
    pred = np.column_stack(
        (60000 * np.sin(time / 90), -45000 * np.cos(time / 70), 110000 + 1000 * time)
    )
    timing = np.column_stack(
        (800 * np.sin(time / 30), 1000 * np.cos(time / 25), np.ones(len(time)))
    )
    identity = (np.arange(320) % 80 >= 40).astype(int)
    calibration = np.array([-80000.0, -104000.0, -54000.0, -16000.0])[group]
    phases = np.array([0.5, -0.5, 0])
    biases = np.array([6000.0, -6000.0, 0])
    frequency = (pred + timing * phases + biases)[np.arange(320), identity] + calibration
    data = FrequencyEvidence(
        tuple(map(str, range(320))),
        frequency[:, None],
        np.ones((320, 1)),
        np.full(320, 0.95),
        group,
        time,
    )
    tracks = [np.arange(g * 80 + h * 40, g * 80 + (h + 1) * 40) for g in range(4) for h in range(2)]
    seed, proposals = bias_shape_seed(
        data, pred, np.ones_like(pred), tracks, calibration, timing=timing
    )
    assert set(seed["active"]) == {0, 1}
    np.testing.assert_allclose(seed["satellite_bias_hz"], biases, atol=30)
    np.testing.assert_allclose(seed["satellite_phase_s"], phases, atol=0.05)
    assert all(abs(p["bias_hz"]) > 2500 for p in proposals)
    with pytest.raises(ValueError, match="calibration"):
        bias_shape_seed(data, pred, np.ones_like(pred), tracks, [0], timing=timing)
