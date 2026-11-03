import copy
import unittest
from run import choose


class TransferTests(unittest.TestCase):
    def test_target_and_future_isolation(self):
        rows=[dict(dataset=ds,signal=ds,phase=phase,errors=[3,2,1,2,3]) for ds in ['DS7','DS8','DS9'] for phase in ['calibration','evaluation']]
        before=choose(rows,'DS7')
        changed=copy.deepcopy(rows)
        for r in changed:
            if r['dataset']=='DS7' or r['phase']=='evaluation':
                r['errors']=[-1000,0,1000,0,0]
        self.assertEqual(choose(changed,'DS7'),before)
        self.assertEqual(before['strength'],.5)

    def test_equal_dataset_weight_and_ties(self):
        rows=[dict(dataset='DS8',signal='a',phase='calibration',errors=[0,3,3,3,3]) for _ in range(10)]
        rows.append(dict(dataset='DS9',signal='b',phase='calibration',errors=[3,0,0,0,0]))
        result=choose(rows,'DS7')
        self.assertEqual(result['calibration_nmse'],[1.5]*5)
        self.assertEqual(result['strength'],0)
