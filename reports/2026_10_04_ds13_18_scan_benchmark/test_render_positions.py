import unittest
from pathlib import Path
from render_positions import validate,scan_label


class PositionPlotTests(unittest.TestCase):
    def document(self,point):
        return dict(arms={arm:dict(records=[dict(point_km=point,objective=1.,success=False)]) for arm in ('fitted-c','zero-c')})

    def test_failed_fit_is_retained_not_mislabeled(self):
        result=validate(self.document([0.,0.]))
        self.assertFalse(result['arms']['fitted-c']['records'][0]['success'])

    def test_outside_disk_rejected(self):
        with self.assertRaisesRegex(ValueError,'out-of-disk'):
            validate(self.document([2.,2.]))

    def test_nested_fisher_scan_label(self):
        self.assertEqual(scan_label(Path('/inputs/N11/seed-timing-v6/position-fisher-v2/selection/a/summary.json')),'N11')
        self.assertEqual(scan_label(Path('/inputs/N02/seed-timing-v6/position-direct-v1/a/summary.json')),'N02')
