import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('inventory', Path(__file__).with_name('inventory.py'))
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)


class InventoryTest(unittest.TestCase):
    def test_baseline_spacing_and_nonbaseline_unknown(self):
        document = {'diagnostics': {'retained_basins': [{'east_km': 1, 'north_km': 2, 'spacing_km': 5}],
                                   'b7': {'regional_failures': {'baseline': [{'stage': 'calibration', 'basin': 'point:1:2', 'reason': 'failed'}],
                                                               'sep50': [{'stage': 'calibration', 'basin': 'point:3:4', 'reason': 'failed'}]}}}}
        failures = inventory.summarize(document)['calibration_failures']
        self.assertEqual(failures[0]['baseline_spacing_km'], 5)
        self.assertIsNone(failures[1]['baseline_spacing_km'])

    def test_no_reference_or_position_fields(self):
        result = inventory.summarize({'reference_latitude_deg': 12, 'methods': {'V16': {'error_km': 99}}})
        self.assertNotIn('reference_latitude_deg', result)
        self.assertNotIn('methods', result)


if __name__ == '__main__':
    unittest.main()
