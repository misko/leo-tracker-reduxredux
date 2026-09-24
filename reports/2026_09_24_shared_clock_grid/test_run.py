import importlib.util
from pathlib import Path
import numpy as np
P=Path(__file__).with_name("run.py"); S=importlib.util.spec_from_file_location("clock_test",P); R=importlib.util.module_from_spec(S); S.loader.exec_module(R)
def test_curved_profile_recovers_known_shift():
 tau=np.arange(-5,5.1,.25); loss=(tau-1.75)**2; assert tau[R.select_tau(loss,tau)]==1.75
def test_linear_cfo_degenerate_profile_prefers_zero():
 tau=np.arange(-5,5.1,.25); assert tau[R.select_tau(np.ones(len(tau)),tau)]==0
def test_held_perturbation_cannot_change_tau():
 tau=np.array([-1.,0.,1.]); train=np.array([.3,.1,.2]); held=np.array([0.,0.,0.]); a=R.select_tau(train,tau); held[:]=1e9; assert R.select_tau(train,tau)==a
def test_signed_tie_follows_absolute_then_signed_order():
 tau=np.array([-2.,-1.,1.,2.]); loss=np.array([0.,0.,0.,0.]); assert tau[R.select_tau(loss,tau)]==-1
