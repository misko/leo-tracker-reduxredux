import unittest
import numpy as np
import audit_math as a


class FactorialTests(unittest.TestCase):
    def test_additive_vectors_can_have_nonzero_scalar_and_square_interactions(self):
        d=a.factorial([2.,1.],[1.,1.],[1.,1.],[0.,1.])
        np.testing.assert_allclose(d['vector_interaction_km'],[0.,0.],atol=1e-15)
        self.assertAlmostEqual(d['squared_error_interaction_km2'],2.)
        self.assertGreater(abs(d['scalar_error_interaction_km']),.1)
        self.assertLess(d['squared_identity_error'],1e-14)

    def test_general_square_identity_and_order(self):
        v11=np.array([.4,-.9]);v10=np.array([-.1,.7]);v01=np.array([.6,.3]);v00=np.array([.1,-.2])
        d=a.factorial(v11,v10,v01,v00)
        np.testing.assert_allclose(d['vector_interaction_km'],v11-v10-v01+v00)
        self.assertLess(d['squared_identity_error'],1e-14)
        swapped=a.factorial(v11,v01,v10,v00)
        self.assertEqual(d['scalar_error_interaction_km'],swapped['scalar_error_interaction_km'])

    def test_native_observation_interaction_cancels_shared_noise_and_alias(self):
        common=np.array([13.,-19.,22.]);phase=np.array([2.,1.,-3.]);shape=np.array([1.,4.,2.]);coupling=np.array([.2,-.1,.3])
        actual=a.observation_interaction(common+phase+shape+coupling,common+phase,common+shape,common)
        np.testing.assert_allclose(actual,coupling,atol=1e-14)


if __name__=='__main__':unittest.main()
