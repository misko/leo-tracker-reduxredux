import unittest
from types import SimpleNamespace

import numpy as np

from oracle import reference_point
from leo.analysis.regional_position_score import coordinates


class DiagnosticChecks(unittest.TestCase):
    def test_reference_coordinate_conversion_matches_production(self):
        prior = SimpleNamespace(latitude_deg=38.5816, longitude_deg=-121.4944)
        for point in ([0., 0.], [-96., -80.], [220., 25.]):
            lat, lon = coordinates(prior, point)
            np.testing.assert_allclose(reference_point(prior, lat, lon), point, atol=1e-9, rtol=0)


if __name__ == "__main__":
    unittest.main()
