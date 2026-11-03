from types import SimpleNamespace

import numpy as np
from marginal_position_adapter import SharedPositionObjective


class Port:
    candidate_count = 1
    observation = np.array([3., -2.])
    config = SimpleNamespace(signal_prior=.8)

    def predict_selected(self, state, index):
        jacobian = np.array([[0., 0., 1., 2., 0., .2],
                             [0., 0., .4, 0., 1., .3]])
        return SimpleNamespace(mean=np.array([state[0], state[1]]), jacobian=jacobian,
                               covariance=np.eye(2), eligible=True)

    def score_selected(self, state, index):
        assert index == 1
        return -7.


def test_joint_normalized_evidence_profile_and_background():
    port = Port()
    position = np.array([.2, -.3])
    marginal = SharedPositionObjective([port, port], 6, [0, 1], 'marginal')
    profile = SharedPositionObjective([port, port], 6, [0, 1], 'profile')
    r = port.observation-position
    h = port.predict_selected(np.zeros(6), 0).jacobian[:, 2:]
    prior = np.diag([1., .25, .25, .25])
    total = 2*np.eye(2)+h@prior@h.T
    expected = .5*(2*np.log(2*np.pi)+np.linalg.slogdet(total)[1]
                   +r@np.linalg.solve(total, r))-np.log(.8)+7.
    np.testing.assert_allclose(marginal(position), expected, rtol=1e-12)
    conditional = prior@h.T@np.linalg.solve(total, r)
    np.testing.assert_allclose(marginal.evaluate(position)[1][2:], conditional, rtol=1e-12)
    determinant = .5*np.linalg.slogdet(np.eye(4)+prior@h.T@h/2)[1]
    np.testing.assert_allclose(marginal(position)-profile(position), determinant, rtol=1e-12)
