from types import SimpleNamespace
import numpy as np
import probe_ds23_joint_relative_feasible as m


def test_constraints_include_new_satellite_phases_and_exact_relative_residuals(monkeypatch):
    monkeypatch.setattr(m,'gate_slacks',lambda *_:{'original':.5})
    t=np.linspace(0,20,20);r=np.tile([10.,-10.,-10.,10.],5)
    p=SimpleNamespace(joint_all_labels=[0,2],relative_include=True,
        state=lambda _:dict(phases=np.array([1.,0.,16.])),exact_relative=lambda _:(r,np.ones(20)*20,None),
        calculate=lambda _:dict(coefficient=np.array([0.,0.,2.])),relative_mapping=np.arange(3),
        relative_problem=SimpleNamespace(labels=[0,2],supported=[],slices=[slice(0,20)],times=t))
    result=m.slacks(p,[0,0],[],300.)
    assert result['original']==.5 and result['phase/1']<0
    assert result['relative/0/rms']==1-10/450
    assert result['relative/0/bias']==.8
    assert result['relative/0/elevation']==2


def test_invalid_phase_uses_finite_tangent_slacks_while_phase_gate_stays_negative(monkeypatch):
    monkeypatch.setattr(m,'gate_slacks',lambda *_:{'original':.5})
    t=np.arange(20);r=np.tile([2.,-2.,-2.,2.],5)
    p=SimpleNamespace(joint_all_labels=[0],relative_include=True,
        state=lambda _:dict(phases=np.array([16.])),exact_relative=lambda _:(None,None,None),
        calculate=lambda _:dict(coefficient=np.zeros(2),relative_residual_hz=r,relative_elevation=np.ones(20)),
        relative_mapping=np.arange(2),relative_problem=SimpleNamespace(labels=[0],supported=[],slices=[slice(0,20)],times=t))
    result=m.slacks(p,[0,0],[],300.)
    assert np.isfinite(list(result.values())).all() and result['phase/0']<0
