import numpy as np
from audit import retained_mass


def test_retained_mass_and_training_gain_identity():
    from scipy.special import logsumexp
    scores=np.log([.2,.3,.5]);ids=np.array([12,8,4]);selected={12,4}
    np.testing.assert_allclose(retained_mass(scores,ids,selected),.7)
    np.testing.assert_allclose(retained_mass(scores+1e5,ids,selected),.7)
    assert retained_mass(scores,ids,set(ids))==1.
    gain=logsumexp(scores)-logsumexp(scores[np.isin(ids,list(selected))])
    np.testing.assert_allclose(gain,-np.log(retained_mass(scores,ids,selected)))
