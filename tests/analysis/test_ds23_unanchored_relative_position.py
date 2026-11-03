from types import SimpleNamespace
import numpy as np
import pytest
import ds23_unanchored_relative_position as m


def problem(monkeypatch,reference):
    def frequency(bank,times,labels,phases,*xy):
        j=np.asarray(labels);t=np.asarray(times);ph=np.asarray(phases)[j]
        return (j+1)*t*t+2*(j+1)*t*ph,np.ones(len(t))*30
    monkeypatch.setattr(m,'paired_phase_frequency',frequency)
    t=np.linspace(1,10,30);mu=np.array([.2,-.3]);q=12e9/11.5e9
    y=q*(2*t*t+4*t*mu[1]-t*t-2*t*mu[0])
    group=dict(lane=[1,2,12e9],noise_sigma_hz=5.,nomination=dict(first_index=0,second_index=1,difference_alias=0),
        points=[dict(time_s=float(x),first_value_hz=0.,second_value_hz=float(v),probe=k) for k,(x,v) in enumerate(zip(t,y,strict=True))])
    sky=dict(time_s=np.arange(4),position_km=np.zeros((2,4,3)),velocity_km_s=np.zeros((2,4,3)))
    return m.RelativeCurveProblem(sky,[0,1],[group],mu,[1.,2.],reference,lambda x:(0.,0.))


def test_absolute_phase_prior_is_invariant_to_reference_for_affine_phase_geometry(monkeypatch):
    a=problem(monkeypatch,[0.,0.]);b=problem(monkeypatch,[.4,-.7])
    ca,cb=a.calculate([0.,0.]),b.calculate([0.,0.])
    assert abs(ca['negative_twice_elbo']-cb['negative_twice_elbo'])<1e-8
    np.testing.assert_allclose(ca['conditional_residual_hz'],cb['conditional_residual_hz'],atol=1e-9)
    np.testing.assert_allclose(a.phases([0.,0.]),b.phases([0.,0.]),atol=1e-9)


def test_exact_prediction_and_signed_RF_scaling_are_consistent(monkeypatch):
    p=problem(monkeypatch,[.4,-.7]);c=p.calculate([0.,0.]);raw,elevation,phase=p.exact_residual([0.,0.])
    np.testing.assert_allclose(raw,c['conditional_residual_hz'],atol=1e-9)
    assert np.min(elevation)>0 and phase.shape==(2,)
    assert c['features'].shape==(30,3)  # Two satellite phases and one transmitter contrast, no radio coordinates.


def test_duplicate_physical_probe_is_rejected(monkeypatch):
    p=problem(monkeypatch,[0.,0.]);g=p.groups[0]
    sky=dict(time_s=np.arange(4),position_km=np.zeros((2,4,3)),velocity_km_s=np.zeros((2,4,3)))
    with pytest.raises(ValueError,match='physical receiver probe'):
        m.RelativeCurveProblem(sky,[0,1],[g,g],[0.,0.],[1.,1.],[0.,0.],lambda x:(0.,0.))
