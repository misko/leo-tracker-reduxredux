import unittest
import numpy as np
from numpy.testing import assert_allclose,assert_array_equal
from relation import branches,phase_prediction,compare_cfo


class RelationTests(unittest.TestCase):
    def test_positive_seam_and_half_period_guard(self):
        fs=2500000;period=fs/750
        parts=branches(np.arange(6.),(period-20+np.arange(6)*10)%period,fs)
        self.assertEqual(len(parts),1)
        parts=branches(np.arange(3.),np.array([0.,period*.49,period*.49+1]),fs)
        self.assertEqual([len(p) for p in parts],[1,2])
        self.assertEqual(len(branches([0.,1.,9.],[1.,2.,3.],fs)),2)

    def test_first_frame_fit_support_center_derivative_and_alternating_holdout(self):
        fs=2500000;t=np.arange(11.);support=t+.009
        phase=(3300+2*t+.3*t*t)%(fs/750)
        p=phase_prediction(t,phase,support,fs)
        self.assertEqual(p['degree'],2)
        assert_allclose(p['derivative_samples_s'],2+.6*support,atol=2e-12,rtol=0)
        changed=phase.copy();changed[p['held']]+=13
        q=phase_prediction(t,changed,support,fs)
        assert_array_equal(p['x_centered'],q['x_centered'])

    def test_cfo_never_changes_phase_fit_and_held_cfo_does_not_change_training_slope(self):
        fs=2500000;t=np.arange(11.);p=phase_prediction(t,10+t+.1*t*t,t,fs)
        y=np.arange(11.)*100.;rf=np.full(11,11e9)
        a=compare_cfo(y,rf,t,p);y[a['held']]+=9999
        b=compare_cfo(y,rf,t,p)
        self.assertEqual(a['beta'],b['beta']);assert_array_equal(a['descriptive_prediction'],b['descriptive_prediction'])

    def test_arbitrary_quadratic_phase_rate_slope_is_equivalent_to_time_trend(self):
        fs=2500000;t=np.arange(13.);p=phase_prediction(t,100+3*t+.2*t*t,t+.009,fs)
        c=compare_cfo(1000+15*t+np.sin(t),np.full(len(t),11e9),t+.009,p)
        assert_allclose(c['descriptive_prediction'],c['time_only_prediction'],atol=1e-18,rtol=0)

    def test_linear_fallback_cannot_identify_centered_phase_rate_scale(self):
        fs=2500000;t=np.arange(7.);p=phase_prediction(t,100+2*t,t,fs)
        self.assertEqual(p['degree'],1);assert_array_equal(p['x_centered'],np.zeros(7))
        self.assertIsNone(compare_cfo(t,np.full(7,11e9),t,p)['beta'])


if __name__=='__main__':unittest.main()
