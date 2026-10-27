import copy
import unittest
import replay

class ReuseTests(unittest.TestCase):
    def test_reuse_rejects_changed_native_input_or_forecast(self):
        old=[dict(native=dict(start=1),blocks=['lane1'])]; forecast=[dict(cfo=10)]
        replay.verify_equal(old,copy.deepcopy(old),forecast,copy.deepcopy(forecast))
        changed=copy.deepcopy(old);changed[0]['native']['start']=2
        with self.assertRaises(AssertionError):replay.verify_equal(old,changed,forecast,forecast)
        with self.assertRaises(AssertionError):replay.verify_equal(old,old,forecast,[dict(cfo=11)])

if __name__=='__main__':unittest.main()
