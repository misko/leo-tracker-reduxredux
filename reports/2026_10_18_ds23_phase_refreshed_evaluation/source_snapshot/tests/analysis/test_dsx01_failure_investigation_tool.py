"""Root-cause ablations preserve nuisance priors and actual observation masks."""

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from dsx01_hierarchical_bound import hierarchical_bound  # noqa: E402
from investigate_dsx01_localization_failures import (  # noqa: E402
    DiagnosticNormal,
    covariance_blocks,
    polynomial_fit,
)


def test_deletion_reintegrates_same_full_nuisance_prior_without_deleted_votes(monkeypatch):
    import investigate_dsx01_localization_failures as module

    p = DiagnosticNormal.__new__(DiagnosticNormal)
    p.control, p.ecc_bank, p.whiteners = "baseline", None, []
    p.values = np.array([12., 14., -900., -1000., 15., 16.])
    p.q, p.point_noise = np.ones(6), np.full(6, 40.)
    p.keep = np.array([True, True, False, False, True, True])
    p.noise_groups = np.repeat(np.arange(3), 2)
    p.members = [0, 1, 2]
    p.hardware, p.smooth = np.empty((6, 1)), np.empty((6, 0))
    p.noise_volume = 0.
    features = np.column_stack((np.ones(6) * 100, np.arange(6) * 10))
    monkeypatch.setattr(module.JointMarginal, "calculate", lambda self, x: dict(
        features=features, intercept=np.zeros(6), elevation=np.full(6, 45.)))
    result = p.calculate(np.zeros(2))
    expected = hierarchical_bound(p.values[p.keep], features[p.keep], 40.,
                                  p.noise_groups[p.keep])
    np.testing.assert_allclose(result["coefficient"], expected["coefficient"])
    assert len(result["coefficient"]) == features.shape[1]
    assert result["noise_precision"][1] == 0
    assert len(result["conditional_residual_hz"]) == 6  # held-out predictions retained
    before = result["coefficient"].copy()
    p.values[~p.keep] *= 10000
    np.testing.assert_allclose(p.calculate(np.zeros(2))["coefficient"], before)


def test_colored_covariance_has_exact_whitening_and_volume():
    times = np.array([0., 1., 3., 8.])
    noise = np.array([40., 60., 80., 100.])
    matrices, volume = covariance_blocks(times, noise, [slice(0, 4)], 150., 10.)
    covariance = np.diag(noise**2) + 150**2 * np.exp(-abs(times[:, None] - times) / 10)
    np.testing.assert_allclose(matrices[0] @ covariance @ matrices[0].T, np.eye(4), atol=1e-12)
    np.testing.assert_allclose(volume, np.linalg.slogdet(covariance)[1] - 8 * np.log(40))


def test_polynomial_complexity_penalty_keeps_linear_data_linear_and_detects_curvature():
    times = np.linspace(0, 20, 40)
    noise = np.full(40, 40.)
    line = 200 + times * 300
    assert polynomial_fit(times, line, noise)["degree"] == 1
    curved = line + 12 * (times - 10)**2
    assert polynomial_fit(times, curved, noise)["degree"] == 2


def test_local_identity_moves_preserve_every_fragment_and_do_not_mutate_donors():
    from dsx01_failure_followups import local_candidates
    from run_dsx01_joint_descent import signature

    def node(ids):
        return dict(seed=dict(state={}, rows=[dict(component=k, candidate_index=j,
                                                   candidate_norad=100 + j)
                                              for k, j in ids.items()]), aliases=[0, 1, 0])
    base = node(dict(A=1, B=1, C=2))
    donor = node(dict(A=3, B=3, C=2))
    before = signature(base), signature(donor)
    candidates = local_candidates(base, [donor])
    assert len(candidates) == 3  # coherent family move plus either single fragment
    assert (signature(base), signature(donor)) == before
    assert all({r["component"] for r in c["seed"]["rows"]} == {"A", "B", "C"}
               for c in candidates)


def test_split_keeps_unique_points_and_refuses_linear_calibration_pieces():
    from dsx01_failure_followups import split_track

    times = np.arange(80.)
    track = dict(key="A", times=times, values=times**2 * 20,
                 observation_ids=[str(i) for i in range(80)], indices=list(range(80)))
    scan = SimpleNamespace(tracks=[track], curved=[0], rx_basis=[np.zeros((80, 11))])
    node = dict(seed=dict(rows=[dict(component="A", candidate_index=0, candidate_norad=100)],
                          state={}), aliases=[1])
    divided, _ = split_track(scan, node, 0, 40)
    assert sorted(i for k in divided.curved for i in divided.tracks[k]["observation_ids"]) == (
        sorted(track["observation_ids"]))
    assert scan.curved == [0] and len(scan.tracks) == 1
    scan.tracks[0] = dict(track, values=times * 200)
    with pytest.raises(ValueError, match="active curvature"):
        split_track(scan, node, 0, 40)


def test_independent_band_drift_prior_gives_two_hz_s_and_zero_cross_covariance(monkeypatch):
    import dsx01_failure_prior_controls as module

    p = module.ExtraControl.__new__(module.ExtraControl)
    p.extra, p.clock = "independent_band_drift_2", np.empty((2, 0))
    p.hardware, p.smooth, p.labels, p.members = np.empty((2, 8)), np.empty((2, 0)), [], [0, 1]
    p.values, p.q = np.array([4., 5.]), np.ones(2)
    p.point_noise, p.noise_groups, p.noise_volume = np.full(2, 40.), np.array([0, 1]), 0.
    features = np.zeros((2, 8))
    features[:, 4], features[:, 5] = 10, [-.5, .5]
    monkeypatch.setattr(module.JointMarginal, "calculate", lambda self, x: dict(
        features=features, intercept=np.zeros(2)))
    scale = np.ones(8)
    scale[[4, 6]], scale[[5, 7]] = np.sqrt(2) / 10, 2 * np.sqrt(2)
    covariance = (features * scale) @ (features * scale).T
    np.testing.assert_allclose(covariance, np.eye(2) * 4, atol=1e-14)
    expected = hierarchical_bound(p.values, features * scale, p.point_noise, p.noise_groups)
    result = p.calculate(np.zeros(2))
    np.testing.assert_allclose(features @ result["coefficient"],
                               (features * scale) @ expected["coefficient"])


def test_orbit_covariance_floors_scale_modes_consistently_without_mutating_causal_cache():
    from dsx01_failure_orbit_floors import inflate_modes

    bank = dict(position_km=np.ones((6, 4, 3)), velocity_km_s=np.ones((6, 4, 3)) * 2)
    metadata = {7: dict(radial_sigma_km=.1, cross_sigma_km=.1,
                        mean_motion_sigma_rev_day=.01, inclination_sigma_deg=.001,
                        raan_sigma_deg=.002)}
    result, inflated = inflate_modes(bank, metadata, [7, 9], .5, .2)
    np.testing.assert_allclose(result["position_km"][:3, 0, 0], [5, 2, 2])
    np.testing.assert_allclose(result["position_km"][3:], 1)
    np.testing.assert_allclose(result["velocity_km_s"][:3, 0, 0], [10, 4, 4])
    assert inflated[7]["mean_motion_sigma_rev_day"] == pytest.approx(.05)
    assert inflated[7]["raan_sigma_deg"] == pytest.approx(.004)
    assert metadata[7]["radial_sigma_km"] == .1
    np.testing.assert_allclose(bank["position_km"], 1)
    with pytest.raises(ValueError, match="positive"):
        inflate_modes(bank, metadata, [7, 9], 0, .2)


def test_expanded_rf_pool_retains_incumbent_and_keeps_c_pair_selected_by_c0():
    from report_dsx01_failure_investigation import rf_union

    def pair(c0, fitted):
        return dict(c0=dict(score=c0), fitted_c=dict(score=fitted))

    incumbent = pair(2, 30)
    record = dict(core=dict(arms={a: dict(refreshed=f) for a, f in incumbent.items()}),
                  hypotheses=dict(choices=[]),
                  regional_candidates=dict(choices=[dict(node_id=0, arms={
                      a: dict(fit=f) for a, f in pair(5, 0).items()})]),
                  coordinate=dict(arms={a: dict(fit=f) for a, f in pair(4, 1).items()}))
    name, selected = rf_union(record)
    assert name == "phase-refreshed incumbent" and selected == incumbent
    record["hypotheses"]["choices"].append(dict(id=1, arms={
        a: dict(fit=f) for a, f in pair(1, 100).items()}))
    name, selected = rf_union(record)
    assert name == "hypotheses:1" and selected["fitted_c"]["score"] == 100
