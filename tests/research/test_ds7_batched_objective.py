import numpy as np

from tools import ds7_baseline_adapter as baseline
from tools.ds7_batched_objective import _points, batched_track_offsets


def _scalar(blocks):
    offsets, audits = [], []
    for block in blocks:
        pairs = [baseline.fit_stationary_offset(row) for row in block]
        offsets.append(np.asarray([pair[0] for pair in pairs]))
        audits.append([pair[1] for pair in pairs])
    return offsets, audits


def _assert_exact(blocks, max_group_rows=1024):
    expected_offsets, expected_audits = _scalar(blocks)
    actual_offsets, actual_audits = batched_track_offsets(blocks, max_group_rows)
    for expected, actual in zip(expected_offsets, actual_offsets, strict=True):
        np.testing.assert_array_equal(actual, expected)
    assert actual_audits == expected_audits


def test_duplicate_quantiles_match_scalar_profiler() -> None:
    blocks = [np.asarray([[4.0, 4.0, 4.0, 4.0], [0.0, 0.0, 1.0, 1.0]])]
    _assert_exact(blocks)


def test_multimodal_roots_match_scalar_profiler() -> None:
    blocks = [
        np.asarray(
            [
                [-1200.0, -1190.0, -1180.0, 900.0, 910.0, 920.0],
                [-700.0, -690.0, 0.0, 10.0, 800.0, 810.0],
            ]
        )
    ]
    expected_offsets, expected_audits = _scalar(blocks)
    assert any(audit["roots"] > 1 for audit in expected_audits[0])
    actual_offsets, actual_audits = batched_track_offsets(blocks, 1)
    np.testing.assert_array_equal(actual_offsets[0], expected_offsets[0])
    assert actual_audits == expected_audits


def test_split_reassembly_preserves_track_and_candidate_order() -> None:
    blocks = [
        np.asarray([[30.0, 31.0, 32.0], [200.0, 205.0, 210.0]]),
        np.asarray([[-50.0, -48.0, -47.0]]),
        np.asarray([[8.0, 9.0, 10.0, 12.0], [90.0, 91.0, 95.0, 99.0]]),
        np.asarray([[500.0, 501.0, 503.0]]),
    ]
    _assert_exact(blocks, max_group_rows=2)


def test_near_boundary_point_comes_from_active_config() -> None:
    points = _points(
        2,
        [0.0, 0.0, 0.0, 0.0],
        {"position_bounds_km": [-12.0, 12.0], "timing_bounds_s": [-5.0, 5.0]},
    )

    np.testing.assert_array_equal(points["near_boundary"], [11.9, -11.9, 4.9, 4.9])
