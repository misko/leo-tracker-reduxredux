import numpy as np
from plot_tight_glrt_tracks import (
    contiguous_segments,
    tight_association_mask,
)


def test_tight_gate_requires_posterior_margin_and_small_residual():
    posterior = np.array(
        [
            [0.92, 0.01],
            [0.89, 0.01],
            [0.92, 0.06],
            [0.92, 0.01],
        ]
    )
    residual = np.array([[50.0, 0.0], [50.0, 0.0], [50.0, 0.0], [151.0, 0.0]])
    np.testing.assert_array_equal(
        tight_association_mask(posterior, residual, 0),
        [True, False, False, False],
    )


def test_segments_split_on_receiver_and_large_time_gap():
    times = np.array([0.0, 1.0, 2.0, 6.1, 7.0, 1.5, 2.5])
    receiver = np.array([0, 0, 0, 0, 0, 1, 1])
    segments = contiguous_segments(times, receiver, np.ones(len(times), dtype=bool))
    assert [(rx, rows.tolist()) for rx, rows in segments] == [
        (0, [0, 1, 2]),
        (0, [3, 4]),
        (1, [5, 6]),
    ]


def test_segmentation_ignores_rows_outside_gate():
    times = np.array([0.0, 1.0, 2.0, 3.0])
    receiver = np.zeros(4, dtype=int)
    segments = contiguous_segments(times, receiver, [True, False, True, True])
    assert len(segments) == 1
    assert segments[0][1].tolist() == [0, 2, 3]
