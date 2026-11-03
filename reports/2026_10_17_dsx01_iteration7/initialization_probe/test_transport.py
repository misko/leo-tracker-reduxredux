from types import SimpleNamespace

import numpy as np
import pytest
from transport import calibration_arrays_equal, map_total_timing, seed_from_context


def test_timing_reorders_adds_and_drops_without_changing_overlap():
    mapped, common, relative = map_total_timing([11, 22, 33], [0., 3., 6.], [33, 44, 11], 3.)
    np.testing.assert_array_equal(mapped, [6., 3., 0.])
    assert common == 3.
    np.testing.assert_allclose(relative.sum(), 0., atol=1e-14)
    mapped, common, relative = map_total_timing([11, 22, 33], [0., 3., 6.], [33, 44], 3.)
    np.testing.assert_array_equal(mapped, [6., 3.])
    assert common == 4.5
    np.testing.assert_array_equal(common + relative, mapped)


@pytest.mark.parametrize("numbers,total,target,common", [
    ([1, 1], [0., 0.], [2], 0.), ([1, 2], [0., 0.], [2, 2], 0.),
    ([1, 2], [0., 1.], [2], 0.), ([1], [float('nan')], [2], 0.),
    ([1.1], [0.], [2], 0.), ([0], [0.], [2], 0.),
])
def test_bad_identity_or_gauge_is_rejected(numbers, total, target, common):
    with pytest.raises(ValueError):
        map_total_timing(numbers, total, target, common)


def test_no_timing_clipping():
    mapped, _, _ = map_total_timing([1, 2], [-30., 30.], [2, 3], 0.)
    np.testing.assert_array_equal(mapped, [30., 0.])


def test_calibration_frame_difference_is_rejected():
    before = SimpleNamespace(design=np.eye(2), clock_design=np.ones((2, 1)),
                             clock_count=1, group_count=0)
    after = SimpleNamespace(**vars(before))
    calibration_arrays_equal(before, after)
    after.design = before.design + 1e-6
    with pytest.raises(ValueError, match="calibration frame"):
        calibration_arrays_equal(before, after)


def toy_contexts():
    receiver = np.array([0, 0, 1, 1, 0, 0, 1, 1])
    channel = np.array([1, 5, 1, 5, 2, 6, 2, 6])
    band = np.column_stack([(receiver == r) & (channel >= 5) for r in (0, 1)])
    obs = SimpleNamespace(window_ids=tuple(map(str, range(8))), times_s=np.arange(8.),
        measured_hz=np.arange(8.) * 2, rf_hz=np.arange(8.) + 10e9, receiver=receiver,
        channel=channel, margin=np.ones(8))
    design = np.column_stack([np.ones(8), np.arange(8.), receiver,
                             receiver * np.arange(8.), np.arange(8.) * .1])
    clock = np.arange(8.)[:, None] ** 2

    def raw(offsets):
        r = SimpleNamespace(design=design.copy(), clock_design=clock.copy(), clock_count=1,
                            group_count=0, baseline=band @ np.array(offsets))
        r.correction = lambda v, n: r.baseline + r.design @ v[2:7] + r.clock_design @ n
        return r

    source = SimpleNamespace(size=9, original=raw([100., 200.]), clock_count=1,
        base_nuisance_count=1, initial_nuisance=np.zeros(2),
        basis=np.array([[1.], [-1.]]) / np.sqrt(2))
    target_basis = np.column_stack([np.array([1., -1., 0.]) / np.sqrt(2),
                                    np.array([1., 1., -2.]) / np.sqrt(6)])
    target = SimpleNamespace(size=10, original=raw([-50., -60.]), clock_count=1,
        base_nuisance_count=1, original_nuisance_count=3, initial_nuisance=np.zeros(5),
        basis=target_basis, band_receivers=(0, 1), band_design=band,
        original_offsets_hz=np.array([-50., -60.]), score=SimpleNamespace(detection_budget=1.6),
        frozen_model=SimpleNamespace(hyperparameters=lambda tail: (None, None, np.full(3, 1.6/3))))
    a = SimpleNamespace(model=source, observations=obs, prior="same",
                        bank=SimpleNamespace(numbers=np.array([10, 20])))
    b = SimpleNamespace(model=target, observations=obs, prior="same",
                        bank=SimpleNamespace(numbers=np.array([20, 30, 40])))
    v = np.array([2., 3., 4., 5., 6., 7., 8., 1., np.sqrt(2)])
    return a, b, v, np.array([9., .75])


def test_complete_calibration_c0_and_neutral_q_transport():
    a, b, v, n = toy_contexts()
    for arm in ("fitted-c", "zero-c"):
        tv, tn, receipt = seed_from_context(a, v, n, b, arm=arm)
        np.testing.assert_allclose(tv[7] + b.model.basis @ tv[8:], [0., 1., 1.], atol=1e-12)
        assert tn[0] == 9.
        np.testing.assert_array_equal(tn[1:3], 0.)
        np.testing.assert_array_equal(tn[3:], [100., 200.])
        assert receipt['maximum_correction_error_hz'] < 1e-10
        assert receipt['overlap_candidates'] == 1
        assert receipt['dropped_source_candidates'] == [10]
        assert tv[6] == (8. if arm == "fitted-c" else 0.)
    assert v[6] == 8.
    np.testing.assert_array_equal(n, [9., .75])


def test_transport_rejects_different_observation_metadata():
    a, b, v, n = toy_contexts()
    b.observations = SimpleNamespace(**vars(a.observations))
    b.observations.rf_hz = a.observations.rf_hz + 1.
    with pytest.raises(ValueError, match="rf_hz"):
        seed_from_context(a, v, n, b, arm="fitted-c")
