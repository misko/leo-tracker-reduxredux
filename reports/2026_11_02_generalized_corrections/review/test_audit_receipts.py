import copy
import importlib.util
from pathlib import Path
import unittest

import numpy as np

from audit_receipts import projection_pass

path = Path(__file__).resolve().parent.parent / "identifiability/guard.py"
spec = importlib.util.spec_from_file_location("receipt_guard_fixture", path)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class AuditReceiptTests(unittest.TestCase):
    def fixture(self):
        family = np.repeat([1, 2, 3], 12)
        t = np.tile(np.linspace(-1, 1, 12), 3)
        u = np.column_stack((np.ones(len(t)), t))
        s = 800 * (t*t - np.mean(t*t))
        result = guard.evaluate_arrays(s, s*0, s, u, u, family)
        result.update(target_fitted_hardware_used=False,
                      saved_phase_references_used=False, GPS_used=False)
        return result

    def test_valid_continuous_support_reconstructs_pass(self):
        self.assertTrue(projection_pass(self.fixture()))

    def test_changed_threshold_is_rejected(self):
        value = self.fixture()
        value["policy"]["minimum_projected_RF_gain"] = -100
        with self.assertRaisesRegex(ValueError, "policy"):
            projection_pass(value)

    def test_missing_family_counterfactual_is_rejected(self):
        value = self.fixture()
        value["leave_one_family_out"].pop()
        with self.assertRaisesRegex(ValueError, "counterfactual"):
            projection_pass(value)

    def test_contrast_arithmetic_corruption_is_rejected(self):
        value = self.fixture()
        value["full"]["projected_RF_gain"] += 2
        with self.assertRaisesRegex(ValueError, "arithmetic"):
            projection_pass(value)


if __name__ == "__main__":
    unittest.main()
