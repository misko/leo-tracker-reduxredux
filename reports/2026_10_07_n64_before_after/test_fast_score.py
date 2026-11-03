import unittest
import numpy as np
from leo.contracts.regional_position import PositionScore
from leo.analysis.regional_position_score import singleton_likelihood,ALIAS_HZ
from fast_score import likelihood

class ScoreParity(unittest.TestCase):
    def test_full_terms_match_oracle_over_supported_noise_and_visibility(self):
        rng=np.random.default_rng(7719)
        for sigma in (125.,200.,1000.,2000.):
            for count in (2,8,34,100):
                score=PositionScore('V16',sigma,1.6,.5,3.,1.)
                measured=rng.normal(size=101)*1e6
                offsets=rng.normal(size=(101,count))*sigma*10
                offsets[:3]=np.array([0.,ALIAS_HZ/2,-ALIAS_HZ/2])[:,None]
                visible=rng.random((101,count))>.3;visible[0]=False
                prediction=measured[:,None]+offsets
                old=singleton_likelihood(measured,prediction,visible,score)
                new=likelihood(measured,prediction,visible,score)
                self.assertAlmostEqual(old.nll,new.nll,places=10)
                for name in ('responsibilities','clutter_probability','prediction_gradient','residual_hz'):
                    np.testing.assert_allclose(getattr(old,name),getattr(new,name),atol=1e-12,rtol=1e-11)

    def test_invalid_arrays_and_satellite_counts_fail(self):
        score=PositionScore('V16',125.,1.6,.5,3.,1.)
        with self.assertRaises(ValueError):likelihood(np.zeros(3),np.zeros((3,1)),np.ones((3,1),bool),score)
        with self.assertRaises(ValueError):likelihood(np.zeros(3),np.zeros((3,2)),np.ones((3,2),int),score)

if __name__=='__main__':unittest.main(verbosity=2)
