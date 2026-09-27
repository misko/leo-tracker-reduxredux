import importlib.util
import numpy as np
from run_stationary_joint import SparseJoint, Stationary, REPORTS


def test_sparse_joint_gradient_and_scan_local_timing():
    path=REPORTS/'2026_09_27_ds6_full_stationary/test_model.py'
    spec=importlib.util.spec_from_file_location('joint_synthetic_fixture',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    models=[Stationary(module.synthetic()) for _ in range(2)]
    joint=SparseJoint(models);x=np.array([.6,-.8,.3,-.2])
    value,gradient=joint.value_gradient(x)
    numeric=[]
    for i in range(4):
        plus=x.copy();minus=x.copy();plus[i]+=1e-3;minus[i]-=1e-3
        numeric.append((joint.value_gradient(plus)[0]-joint.value_gradient(minus)[0])/.002)
    np.testing.assert_allclose(gradient,numeric,atol=1e-5,rtol=1e-5)
    for model in models:
        for t in model.base.tracks:t['y']+=np.where(t['mask'],0.,1e6)
    other,g=joint.value_gradient(x)
    assert other==value
    np.testing.assert_array_equal(g,gradient)
