from __future__ import annotations

from math import log, pi

import numpy as np
import pytest

from leo.analysis.adaptive_location_map import (
    RefinementConfig,
    TrackFactor,
    quadrature_points,
    uniform_disk_state,
    update_map,
)


def _state(*, rings=2, sectors=4, nuisance_prior=(1.0,)):
    hypotheses=np.arange(len(nuisance_prior),dtype=float)[:,None]
    return uniform_disk_state(38.5816,-121.4944,250.,hypotheses,("clock",),nuisance_prior,
                              radial_rings=rings,angular_sectors=sectors)


def test_uniform_disk_partition_has_exact_area_and_mass() -> None:
    state=_state(rings=4,sectors=8,nuisance_prior=(.25,.75))
    assert sum(cell.area_km2 for cell in state.cells) == pytest.approx(pi*250**2)
    assert sum(cell.joint_mass.sum() for cell in state.cells) == pytest.approx(1.)
    assert all(cell.area_km2 == pytest.approx(pi*250**2/32) for cell in state.cells)


def test_constant_likelihood_refinement_preserves_probability_and_area() -> None:
    state=_state()
    factor=TrackFactor(("track",),("sat","background"),
                       lambda points,nuisance: np.zeros((len(points),len(nuisance),2)))
    result=update_map(state,factor,RefinementConfig(max_cells=32,min_log_likelihood_range=0.))
    assert result.refined_parent_count == 8
    assert len(result.state.cells) == 32
    assert sum(cell.area_km2 for cell in result.state.cells) == pytest.approx(pi*250**2)
    assert sum(cell.joint_mass.sum() for cell in result.state.cells) == pytest.approx(1.)
    assert result.branch_probabilities == pytest.approx({"sat":.5,"background":.5})


def test_narrow_secondary_island_triggers_refinement_without_mass_pruning() -> None:
    state=_state(rings=1,sectors=4)
    def likelihood(points,nuisance):
        east,north=points.T
        broad=-((east+100)**2+north**2)/(2*80**2)
        narrow=log(.08)-((east-150)**2+(north-10)**2)/(2*8**2)
        spatial=np.logaddexp(broad,narrow)
        return spatial[:,None,None]
    result=update_map(state,TrackFactor(("t",),("marginal",),likelihood),
                      RefinementConfig(max_cells=16,min_cell_mass=1e-8,min_log_likelihood_range=.1))
    assert result.refined_parent_count == 4
    assert len(result.state.cells) == 16
    assert sum(cell.joint_mass.sum() for cell in result.state.cells) == pytest.approx(1.)
    assert all(cell.joint_mass.sum() > 0 for cell in result.state.cells)


def test_satellite_and_background_marginalization_matches_direct_quadrature() -> None:
    state=_state(rings=1,sectors=1,nuisance_prior=(.4,.6))
    values=np.array([log(.2),log(.3),log(.5)])
    def likelihood(points,nuisance):
        return np.broadcast_to(values,(len(points),len(nuisance),3))
    result=update_map(state,TrackFactor(("t",),("sat-a","sat-b","background"),likelihood),
                      RefinementConfig(max_cells=1))
    assert result.log_evidence == pytest.approx(0.)
    assert result.branch_probabilities == pytest.approx({"sat-a":.2,"sat-b":.3,"background":.5})


def test_unavailable_branch_has_zero_probability_without_invalidating_factor() -> None:
    state=_state(rings=1,sectors=1)
    def likelihood(points,nuisance):
        values=np.empty((len(points),len(nuisance),2))
        values[...,0]=-np.inf
        values[...,1]=0.
        return values
    result=update_map(state,TrackFactor(("t",),("invisible-sat","background"),likelihood),
                      RefinementConfig(max_cells=1))
    assert result.branch_probabilities == pytest.approx({"invisible-sat":0.,"background":1.})


def test_shared_nuisance_hypothesis_is_conditioned_once_across_tracks() -> None:
    state=_state(rings=1,sectors=1,nuisance_prior=(.5,.5))
    def first(points,nuisance):
        per_hypothesis=np.where(nuisance[:,0] == 0,log(.9),log(.1))
        return np.broadcast_to(per_hypothesis,(len(points),len(nuisance)))[:,:,None]
    def second(points,nuisance):
        per_hypothesis=np.where(nuisance[:,0] == 0,log(.8),log(.2))
        return np.broadcast_to(per_hypothesis,(len(points),len(nuisance)))[:,:,None]
    one=update_map(state,TrackFactor(("a",),("sat",),first),RefinementConfig(max_cells=1))
    two=update_map(one.state,TrackFactor(("b",),("sat",),second),RefinementConfig(max_cells=1))
    np.testing.assert_allclose(two.state.cells[0].joint_mass,[.72/.74,.02/.74])


def test_provenance_rejects_duplicate_observations_and_branch_identifiers() -> None:
    with pytest.raises(ValueError,match="branch IDs"):
        TrackFactor(("t",),("sat","sat"),lambda p,n: np.zeros((len(p),len(n),2)))
    state=_state(rings=1,sectors=1)
    factor=TrackFactor(("t",),("background",),lambda p,n: np.zeros((len(p),len(n),1)))
    updated=update_map(state,factor,RefinementConfig(max_cells=1)).state
    with pytest.raises(ValueError,match="already consumed"):
        update_map(updated,factor,RefinementConfig(max_cells=1))


def test_quadrature_points_stay_inside_cell() -> None:
    cell=_state(rings=1,sectors=1).cells[0]
    points,weights=quadrature_points(cell,4)
    assert np.all(np.linalg.norm(points,axis=1) < 250.)
    assert weights.sum() == pytest.approx(1.)


def test_likelihood_port_calls_are_vectorized_and_point_bounded() -> None:
    state=_state(rings=4,sectors=8)
    call_sizes=[]
    def likelihood(points,nuisance):
        call_sizes.append(len(points))
        east=points[:,0]
        return (-east**2/1000.)[:,None,None]
    update_map(state,TrackFactor(("t",),("sat",),likelihood),
               RefinementConfig(max_cells=128,quadrature_order=3,min_log_likelihood_range=0.,
                                max_points_per_call=36))
    assert len(call_sizes) > 1
    assert max(call_sizes) <= 36
    assert all(size % 9 == 0 for size in call_sizes)


def test_late_refinement_replays_anticorrelated_track_and_is_order_invariant() -> None:
    initial=_state(rings=1,sectors=1)
    def east_peak(points,nuisance):
        return (points[:,0]/20.)[:,None,None]
    def west_peak(points,nuisance):
        return (-points[:,0]/20.)[:,None,None]
    east=TrackFactor(("east",),("sat",),east_peak)
    west=TrackFactor(("west",),("sat",),west_peak)
    coarse=update_map(initial,east,RefinementConfig(max_cells=1)).state
    late=update_map(coarse,west,RefinementConfig(max_cells=4,min_log_likelihood_range=0.)).state
    early=update_map(initial,east,RefinementConfig(max_cells=4,min_log_likelihood_range=0.)).state
    early_then_west=update_map(early,west,RefinementConfig(max_cells=4)).state
    west_first=update_map(initial,west,RefinementConfig(max_cells=4,min_log_likelihood_range=0.)).state
    reversed_order=update_map(west_first,east,RefinementConfig(max_cells=4)).state
    expected=np.full(4,.25)
    np.testing.assert_allclose([cell.joint_mass[0] for cell in late.cells],expected,atol=1e-12)
    np.testing.assert_allclose(
        [cell.joint_mass[0] for cell in early_then_west.cells],expected,atol=1e-12
    )
    np.testing.assert_allclose(
        [cell.joint_mass[0] for cell in reversed_order.cells],expected,atol=1e-12
    )


def test_spatially_constant_nuisance_discrimination_does_not_trigger_refinement() -> None:
    state=_state(rings=1,sectors=1,nuisance_prior=(.5,.5))
    def likelihood(points,nuisance):
        by_hypothesis=np.array([0.,-100.])
        return np.broadcast_to(by_hypothesis,(len(points),2))[:,:,None]
    result=update_map(state,TrackFactor(("t",),("sat",),likelihood),
                      RefinementConfig(max_cells=16,min_log_likelihood_range=.1))
    assert result.refined_parent_count == 0
    assert len(result.state.cells) == 1
