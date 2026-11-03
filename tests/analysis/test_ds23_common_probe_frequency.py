from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_common_probe_frequency import part_design,rebase_parameters,CommonProbeFrequency
from ds23_joint_component_refinement import JointComponentWorkspace


def test_frequency_difference_and_information_are_invariant_to_reference_part():
    truth=np.array([23000.,-41000.,75.,-65.]);values=np.array([part_design(k,2)@truth for k in range(3)])
    precision=np.array([[1.,.2],[.2,.8]]);contrast=np.array([1.,-1.,0.,0.]);variances=[];mean_variances=[]
    for reference in range(3):
        rebased=rebase_parameters(truth,2,reference)
        np.testing.assert_allclose([part_design(k,reference)@rebased for k in range(3)],values)
        assert contrast@rebased==contrast@truth
        normal=sum(part_design(k,reference).T@precision@part_design(k,reference) for k in range(3))
        variances.append(contrast@np.linalg.solve(normal,contrast))
        averaged=sum(w*part_design(k,reference) for k,w in enumerate([.2,.3,.5]))
        np.testing.assert_allclose(averaged@rebased,np.array([.2,.3,.5])@values)
        mean_variances.append(averaged@np.linalg.solve(normal,averaged.T))
    np.testing.assert_allclose(variances,np.repeat(variances[0],3),rtol=1e-14)
    np.testing.assert_allclose(mean_variances,np.repeat(np.array(mean_variances[:1]),3,axis=0),rtol=1e-13,atol=1e-13)


def scene():
    rng=np.random.default_rng(210221);n=50000;fs=2.5e6
    fits=[dict(CFO_hz=12000.,offset_samples=.1,modulation_ppm=2.),dict(CFO_hz=-28000.,offset_samples=-.1,modulation_ppm=-2.)]
    p=JointComponentWorkspace(rng.normal(size=n)+1j*rng.normal(size=n),fs,'upper',[120.,900.],fits)
    model=CommonProbeFrequency(p,p.start);truth=np.array([12080.,-28060.,70.,-50.])
    for k,segments in enumerate(model.parts):
        params=p.start.copy();params[[0,3]]=part_design(k)@truth
        (a,_),(b,_)=[p.columns_and_derivatives(v,j) for j,v in enumerate(params.reshape(2,3))]
        for ix in segments:
            coef=(rng.normal(size=17)+1j*rng.normal(size=17))*10
            p.y[ix]+=np.column_stack((a[ix],b[ix],np.ones(len(ix))))@coef
    return model,truth


def test_shared_frequency_gradient_matches_variable_projection_finite_differences():
    model,truth=scene();x=truth+np.array([5.,-7.,2.,-3.]);analytic=model.statistics(x,0)['gradient_score'];finite=[]
    for k in range(4):
        delta=np.zeros(4);delta[k]=.001
        finite.append((model.statistics(x+delta,0,derivatives=False)['score']-model.statistics(x-delta,0,derivatives=False)['score'])/.00002)
    np.testing.assert_allclose(analytic,finite,rtol=2e-4,atol=3e-7)


def test_injected_carrier_difference_is_recovered_despite_independent_channel_phases():
    model,truth=scene();initial=model.statistics(model.start,0,prediction=True)
    fit=model.optimize(0);final=model.statistics(fit['parameters'],0,prediction=True)
    assert fit['component_CFO_difference_hz']==pytest.approx(truth[0]-truth[1],abs=3.)
    assert final['heldout_squared_error']<initial['heldout_squared_error']
    other=CommonProbeFrequency(model.p,model.initial,reference=0)
    changed=other.optimize(0,start=rebase_parameters(fit['parameters'],2,0))
    assert changed['component_CFO_difference_hz']==pytest.approx(fit['component_CFO_difference_hz'],abs=.2)


@pytest.mark.parametrize('part,reference',[(-1,2),(3,0),(0,3)])
def test_unsupported_time_partition_is_rejected(part,reference):
    with pytest.raises(ValueError):part_design(part,reference)
