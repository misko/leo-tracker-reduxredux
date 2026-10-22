import numpy as np
import pytest

from ds23_new_family_prediction import wrapped_curve_score,joint_prediction,orbit_terms
from leo.analysis.research.retained_track_likelihood import PERIOD


def test_unknown_curve_density_is_invariant_to_a_whole_fragment_alias():
    t=np.linspace(0.,12.,17);values=30000-200*t+30*np.sin(t)
    baseline=wrapped_curve_score(t,values,np.full(len(t),150.))
    for alias in [-3,-1,1,4]:
        assert wrapped_curve_score(t,values+alias*PERIOD,np.full(len(t),150.))==pytest.approx(baseline,abs=1e-7)


def test_old_and_new_prediction_keep_shared_calibration_covariance():
    old_raw=np.array([.3,-.1]);new_raw=np.array([.2,.7]);old=np.array([[1.,.2],[1.,-.3]])
    new=np.array([[1.,.4],[1.,.6]]);modes=np.array([[.2],[.5]]);gram=np.array([[3.,.2],[.2,2.]])
    sigma=np.full(4,.3);groups=np.array([0,0,1,1]);result=joint_prediction(old_raw,old,new_raw,new,modes,gram,sigma,groups)
    design=np.vstack((np.column_stack((old,np.zeros((2,1)))),np.column_stack((new,modes))))
    covariance=np.zeros((3,3));covariance[:2,:2]=np.linalg.inv(gram);covariance[2,2]=1.
    total=np.diag(sigma**2)+design@covariance@design.T+300**2*(groups[:,None]==groups[None,:])
    y=np.r_[old_raw,new_raw];score=y@np.linalg.solve(total,y)+np.linalg.slogdet(total)[1]+len(y)*np.log(2*np.pi)
    assert result['objective']==pytest.approx(score,abs=1e-7)


def test_paired_geometry_retains_each_timestamp_against_independent_grid_api():
    from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
    grid=np.arange(-20.,321.);rate=.0011;radius=7078.
    position=np.column_stack((radius*np.cos(rate*grid),radius*np.sin(rate*grid),np.zeros(len(grid))))
    velocity=np.column_stack((-radius*rate*np.sin(rate*grid),radius*rate*np.cos(rate*grid),np.zeros(len(grid))))
    bank=dict(time_s=grid,position_km=position[None,:,:],velocity_km_s=velocity[None,:,:])
    times=np.array([10.,33.5,100.,170.,250.]);phase=.2
    f,e,derivative=orbit_terms(bank,times,phase,1.,2.)
    expected,elevation=phase_frequency_grid(bank,times,1.,2.,phase_seconds=phase)
    plus=phase_frequency_grid(bank,times,1.,2.,phase_seconds=phase+.01)[0]
    minus=phase_frequency_grid(bank,times,1.,2.,phase_seconds=phase-.01)[0]
    np.testing.assert_allclose(f,expected[0],atol=1e-7)
    np.testing.assert_allclose(e,elevation[0],atol=1e-10)
    np.testing.assert_allclose(derivative,(plus[0]-minus[0])/.02,atol=1e-6)
    assert np.ptp(f)>1000 and np.ptp(derivative)>1


def test_confirmation_sampling_is_reproducible_scan_disjoint_and_does_not_rank_errors():
    from confirm_ds23_new_family_prediction import sample_cases
    population=[f'DS23-{i:04d}' for i in range(1,414)]
    a=sample_cases(population)
    assert a==sample_cases(list(reversed(population)))
    assert len(a)==20 and not (set(a)&{'DS23-0227','DS23-0400'})
