import numpy as np
from ds23_training_gain_rf import restricted_workspace


def test_carrier_timing_rate_objective_cannot_read_held_samples():
    rng=np.random.default_rng(31);samples=rng.normal(size=50000)+1j*rng.normal(size=50000)
    segments=[np.arange(a,a+1500) for a in [1000,8000,15000,22000,29000,36000]]
    changed=samples.copy();used=np.zeros(len(samples),bool);used[np.concatenate(segments)]=True
    changed[~used]+=1000*(rng.normal(size=(~used).sum())+1j*rng.normal(size=(~used).sum()))
    first=restricted_workspace(samples,2500000,'lower',100,segments)
    second=restricted_workspace(changed,2500000,'lower',100,segments)
    for parameters in [[100.,0.,0.],[250.,.2,10.]]:
        a=first.statistics(parameters);b=second.statistics(parameters)
        assert a['score']==b['score']
        np.testing.assert_array_equal(a['normal'],b['normal'])
        np.testing.assert_array_equal(a['rhs'],b['rhs'])
        np.testing.assert_array_equal(first.evaluate([parameters[0]],parameters[1],parameters[2]),
            second.evaluate([parameters[0]],parameters[1],parameters[2]))
