import unittest
import tempfile
from pathlib import Path
import numpy as np
from render_position_summary import nuisance_delta,case_path


class PositionSummaryTests(unittest.TestCase):
    def test_warning_fallback_never_hides_clean_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp);clean=case_path(directory,'support',1.)
            warning=Path(str(clean).replace('position-fisher-v2/','position-fisher-v2-calibration-warning/'))
            warning.parent.mkdir(parents=True);warning.touch()
            self.assertEqual(case_path(directory,'support',1.),warning)
            clean.parent.mkdir(parents=True);clean.touch()
            self.assertEqual(case_path(directory,'support',1.),clean)

    def test_common_shift_does_not_appear_as_relative_shift(self):
        roof={'parameters':[0,0,0,0,0,0,1,-1],'coefficient':3.}
        case={'parameters':[1,2,4,5,6,7,3,1],'coefficient':8.}
        delta=nuisance_delta(case,roof)
        np.testing.assert_allclose(delta[:7],[4,6,5,7,5,2,0])
        self.assertAlmostEqual(delta[7],.02)

    def test_full_fraction_reuses_same_source(self):
        self.assertEqual(case_path(Path('/scan'),'rms',1),case_path(Path('/scan'),'glrt',1))

    def test_changed_satellite_dimension_rejected(self):
        with self.assertRaises(ValueError):nuisance_delta({'parameters':[0]*7},{'parameters':[0]*8})
