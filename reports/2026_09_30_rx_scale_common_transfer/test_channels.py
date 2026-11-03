import copy
import unittest
import numpy as np
from channels import channels


def cases():
    t=np.arange(24.)
    a=dict(times=t.tolist(),mask=(t%3!=2).tolist(),residual=np.sin(t).tolist())
    b=dict(a,residual=(-np.sin(t)).tolist())
    return a,b


class ChannelsTest(unittest.TestCase):
    def test_shared_signal_changes_common_not_difference(self):
        a,b=cases();before=channels(a,b)
        ramp=np.arange(24.)*10
        a['residual']=(np.asarray(a['residual'])+ramp).tolist()
        b['residual']=(np.asarray(b['residual'])+ramp).tolist()
        after=channels(a,b)
        np.testing.assert_allclose(after['held']['difference'],before['held']['difference'],atol=1e-12)
        self.assertAlmostEqual(after['feature'],before['feature'])
        self.assertGreater(np.max(abs(np.asarray(after['held']['common']))),50)
        np.testing.assert_array_equal(before['held']['common'],np.zeros(8))

    def test_held_values_do_not_change_any_center_or_feature(self):
        a,b=cases();before=channels(a,b)
        changed=copy.deepcopy(a);changed['residual'][2::3]=[1e8]*8
        after=channels(changed,b)
        self.assertEqual(before['centers'],after['centers'])
        self.assertEqual(before['feature'],after['feature'])


if __name__=='__main__':
    unittest.main()
