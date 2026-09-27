import copy
import unittest
from score_results import gate


def fixture():
    return {d:{'normal':{'pooled_gain':.1,'equal_recording_gain':.2,'recordings_improving':3},
               'reversed':{'pooled_gain':-.1}} for d in ('X_to_Y','Y_to_X')}


class Tests(unittest.TestCase):
    def test_all_conditions(self):self.assertTrue(gate(fixture())['advance'])
    def test_each_condition_is_required(self):
        for d in ('X_to_Y','Y_to_X'):
            for field,value in [('pooled_gain',0),('equal_recording_gain',0),('recordings_improving',2)]:
                v=fixture();v[d]['normal'][field]=value
                self.assertFalse(gate(v)['advance'])
            v=fixture();v[d]['reversed']['pooled_gain']=.1
            self.assertFalse(gate(v)['advance'])


if __name__=='__main__':unittest.main()
