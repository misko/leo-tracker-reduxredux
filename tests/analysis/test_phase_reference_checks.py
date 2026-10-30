import numpy as np
import pytest
from phase_reference_checks import phase_refresh,reference_domain
from leo.analysis.research.grouped_prediction import identity_consensus


def test_clipped_reference_stagnation_is_not_convergence():
    updated,check=phase_refresh([18.1,-2.],[15.,-2.])
    np.testing.assert_array_equal(updated,[15.,-2.])
    assert check['clipped_reference_change_s']==0
    assert check['phase_change_s']==pytest.approx(3.1)
    assert check['phase_outside_reference_window']
    folds=[]
    for seed in range(3):
        proposals=[]
        for norad,score,delta in [(1,0.,check['phase_change_s']),(2,50.,0.)]:
            v=dict(scores=dict(joint=dict(negative_twice_log_density=score),target=dict(rms_hz=40.)),
                final_phase_change_s=delta,minimum_target_elevation_deg=30.)
            proposals.append(dict(norad=norad,arms=dict(c0=v,fitted_c=v)))
        folds.append(dict(seed=seed,proposals=proposals))
    assert identity_consensus(folds)['status']=='prediction_mismatch'


def test_interior_update_preserves_reference_and_convergence():
    phases=np.array([.1,-.2]);reference=phases+.001
    updated,check=phase_refresh(phases,reference)
    np.testing.assert_array_equal(updated,phases);assert check['phase_change_s']==pytest.approx(.001)
    assert not check['phase_outside_reference_window']
    for a,b in [([],[]),([np.nan],[0.]),([0.],[0.,1.])]:
        with pytest.raises(ValueError):phase_refresh(a,b)


def test_wider_reference_can_converge_only_within_existing_orbit_support():
    updated,check=phase_refresh([18.1],[18.099],limit_s=30.)
    assert check['phase_change_s']==pytest.approx(.001) and not check['phase_outside_reference_window']
    assert reference_domain([-20.,320.],[153.,194.],[0,0],updated)['in_domain']
    assert not reference_domain([-20.,210.],[153.,194.],[0,0],updated)['in_domain']
    assert not reference_domain([0.,10.],[0.,9.],[0,0],[0.])['in_domain']
