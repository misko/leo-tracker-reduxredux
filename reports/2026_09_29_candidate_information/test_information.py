import unittest

import numpy as np
from information import compare, profile_information


class InformationTests(unittest.TestCase):
    def test_projection_matches_direct_design(self):
        rng = np.random.default_rng(27)
        blocks = []
        for i in range(6):
            a = rng.normal(size=(20, 4))
            z = rng.normal(size=20)
            a -= a.mean(axis=0)
            z -= z.mean()
            blocks.append(dict(a=a, z=z, group=i // 2))
        result = compare(blocks)
        a = np.vstack([b["a"] for b in blocks])
        z = np.zeros((120, 3))
        for i, b in enumerate(blocks):
            z[i * 20 : (i + 1) * 20, b["group"]] = b["z"]
        design = np.column_stack([a, z])
        expected, _ = profile_information(design.T @ design)
        np.testing.assert_allclose(result["shared"]["information"], expected, atol=1e-10)
        self.assertTrue(
            np.all(
                np.asarray(result["track"]["retention"])
                <= np.asarray(result["shared"]["retention"]) + 1e-10
            )
        )

    def test_slope_can_remove_position_direction(self):
        t = np.arange(10.0) - 4.5
        quadratic = t * t - np.mean(t * t)
        blocks = [dict(a=np.column_stack([t, quadratic, np.zeros(10)]), z=t, group=0)]
        result = compare(blocks)
        np.testing.assert_allclose(result["shared"]["retention"], [0, 1], atol=1e-10)


if __name__ == "__main__":
    unittest.main()
