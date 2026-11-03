import ast
import importlib.util
from pathlib import Path
import unittest
import numpy as np
import run

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE.parent/'cross_band_rx_drift/run.py'


class ConfirmationTests(unittest.TestCase):
    def test_exact_program_equivalence_except_declared_changes(self):
        source = (HERE/'run.py').read_text()
        source = source.replace('"""Unchanged drift screen on the 24 non-screen original scans."""',
                                '"""Training-only cross-source slope transfer, scored on frozen held pairs."""')
        source = source.replace('for index in [i for i in range(32) if i % 4]:', 'for index in range(0,32,4):')
        source = source.replace(", HILL/'cross_band_rx_drift/run.py',\n             HILL/'cross_band_rx_drift/outcome.json'", '')
        source = source.replace('len(gains)==24 and sum(v>0 for v in gains)>=15',
                                'len(gains)==8 and sum(v>0 for v in gains)>=5')
        self.assertEqual(ast.dump(ast.parse(source)), ast.dump(ast.parse(ORIGINAL.read_text())))

    def test_numerical_parity_and_training_only_predictor(self):
        spec = importlib.util.spec_from_file_location('old_drift', ORIGINAL)
        old = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(old)
        donors = [(0,100), (10,110), (20,120), (30,500)]
        self.assertEqual(run.slope_fit(donors), old.slope_fit(donors))
        args = (np.arange(6.), np.arange(6.)+100, np.arange(-2.,35.), run.slope_fit(donors))
        for a,b in zip(run.predict(*args), old.predict(*args)):
            np.testing.assert_array_equal(a,b)


if __name__ == '__main__':
    unittest.main()
