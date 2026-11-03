"""Independent geometry and controlled experiment receipt checks."""
import importlib.util
import json
from pathlib import Path
import unittest

class ResultsTests(unittest.TestCase):
    def test_controlled_pairs_and_constraints(self):
        data=json.loads((Path(__file__).parent/'results.json').read_text())
        self.assertEqual(len(data['results']),8)
        for method in ('T1AT','V16'):
            for radius in (12.5,25.0):
                pair=[r for r in data['results'] if r['method']==method and r['radius_km']==radius]
                self.assertEqual({r['arm'] for r in pair},{'fitted-c','zero-c'})
                self.assertEqual(pair[0]['local_center'],pair[1]['local_center'])
                for row in pair:
                    self.assertLessEqual(row['distance_from_local_center_km'],radius+1e-5)
                    self.assertGreater(row['evaluations'],0)
                    self.assertEqual(row['converged'],row['stationarity']<=.001)
                    if row['arm']=='zero-c': self.assertEqual(row['vector'][6],0)

if __name__=='__main__': unittest.main()
