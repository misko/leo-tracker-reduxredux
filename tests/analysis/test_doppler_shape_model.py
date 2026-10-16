import numpy as np

from leo.analysis.research.doppler_shape_model import (
    OffsetProjector,
    ShapeSequence,
    fit_shape_position,
    score_trajectory_bank,
)


def test_correlated_noise_projection_matches_full_gls_and_offset_invariance():
    covariance = np.array(
        [[4.0, 1.0, 0.0, 0.0], [1.0, 9.0, 2.0, 0.0], [0.0, 2.0, 16.0, 3.0], [0.0, 0.0, 3.0, 25.0]]
    )
    projector = OffsetProjector(["a", "a", "b", "b"], covariance_hz2=covariance)
    residual = np.array([8.0, 14.0, -3.0, 11.0])
    precision = np.linalg.inv(covariance)
    design = np.array([[1.0, 0.0], [1.0, 0.0], [0.0, 1.0], [0.0, 1.0]])
    offsets = np.linalg.solve(design.T @ precision @ design, design.T @ precision @ residual)
    remainder = residual - design @ offsets
    np.testing.assert_allclose(projector.score(residual), remainder @ precision @ remainder)
    np.testing.assert_allclose(projector.coefficients(residual), offsets)
    np.testing.assert_allclose(
        projector.score(residual + design @ [320.0, -900.0]), projector.score(residual)
    )
    assert projector.shape_dof == 2


def test_heteroscedastic_offsets_are_weighted_and_singletons_have_no_information():
    projector = OffsetProjector(["a", "a", "b"], sigma_hz=[1.0, 2.0, 1.0])
    np.testing.assert_allclose(projector.coefficients([0.0, 10.0, 1200.0]), [2.0, 1200.0])
    np.testing.assert_allclose(projector.score([0.0, 10.0, 1200.0]), 20.0)
    assert projector.shape_dof == 1


def test_shared_receiver_drift_preserves_different_track_slopes():
    times = np.tile(np.arange(5.0), 2)
    projector = OffsetProjector(
        ["a"] * 5 + ["b"] * 5,
        sigma_hz=1.0,
        receiver_ids=["RX0"] * 10,
        times_s=times,
        shared_receiver_drift=True,
    )
    common = 3.0 * times + np.repeat([40.0, -70.0], 5)
    np.testing.assert_allclose(projector.score(common), 0.0, atol=1e-20)
    assert projector.score(common + np.r_[2.0 * times[:5], -2.0 * times[5:]]) > 0
    assert projector.shape_dof == 7


def test_candidate_branch_is_selected_for_entire_sequence():
    sequence = ShapeSequence(
        "s",
        ("a", "b", "c"),
        np.array([0.0, 10.0, 0.0]),
        np.ones(3),
        ("sat1:branch0", "sat2:branch0"),
    )
    result = score_trajectory_bank(sequence, np.array([[0.0, 0.0, 0.0], [10.0, 10.0, 10.0]]))
    # Sample-wise branch picking could fit perfectly, but neither complete track can.
    np.testing.assert_allclose(result["chi2"], 200.0 / 3.0)
    np.testing.assert_allclose(result["runner_up_delta_chi2"], 0.0, atol=1e-12)
    assert len(result["candidate_chi2"]) == 2


def test_projected_information_reports_timing_and_constant_rf_c_rank_loss():
    projector = OffsetProjector(["a"] * 4 + ["b"] * 4, sigma_hz=1.0)
    slope = np.tile([-1.5, -0.5, 0.5, 1.5], 2)
    curvature = np.tile([1.0, -1.0, -1.0, 1.0], 2)
    geo = np.column_stack((slope, curvature))
    direct = projector.information(geo)
    with_c = projector.information(geo, np.repeat([0.1, 0.9], 4)[:, None])
    with_timing = projector.information(geo, np.column_stack((slope, np.ones(8))))
    assert direct["geo_rank"] == with_c["geo_rank"] == 2
    assert with_c["additional_nuisance_rank"] == 0
    assert with_timing["geo_rank"] == 1
    assert with_timing["conditional_covariance_km2"] is None


def test_shape_position_recovers_geometry_while_absolute_offsets_vary():
    times = np.linspace(-1.0, 1.0, 9)
    sequences = tuple(
        ShapeSequence(
            str(i),
            tuple(f"{i}-{j}" for j in range(9)),
            offset + 2.0 * times - 3.0 * times**2,
            np.ones(9),
            ("sat:branch0",),
        )
        for i, offset in enumerate([12000.0, -8000.0])
    )

    def predict(theta):
        return tuple((theta[0] * times + theta[1] * times**2)[None, :] for _ in sequences)

    result = fit_shape_position(
        sequences, predict, [[0.0, 0.0], [4.0, -4.0]], [(-10.0, 10.0), (-10.0, 10.0)]
    )
    assert result["winner"] is not None
    np.testing.assert_allclose(result["winner"]["theta"], [2.0, -3.0], atol=2e-4)
    assert result["shape_dof"] == 16


def test_overlapping_support_and_no_shape_information_are_explicit_errors():
    singleton = ShapeSequence("a", ("a",), np.ones(1), np.ones(1), ("sat",))
    with np.testing.assert_raises_regex(ValueError, "no supported shape"):
        fit_shape_position((singleton,), lambda _: (), [[0]], [(-1.0, 1.0)])
    sequence = ShapeSequence("a", ("a", "b"), np.ones(2), np.ones(2), ("sat",))
    with np.testing.assert_raises_regex(ValueError, "must not overlap"):
        fit_shape_position((sequence, sequence), lambda _: (), [[0]], [(-1.0, 1.0)])
