"""Checks of the independent generator. Does not read the seed or release any labels."""

from datetime import UTC, datetime
import unittest

import numpy as np
from sgp4.api import Satrec, WGS72

from publish import NS, contains, distance, geography, move, orbit_state, projection, station, timestamp


class GeneratorTests(unittest.TestCase):
    def test_geodetic_square_and_dateline(self):
        center = [59., 179.9901]
        east_twelve = move(center, np.pi/2, 12.)
        east_thirteen = move(center, np.pi/2, 13.)
        diagonal = move(center, np.pi/4, 15.)
        self.assertLess(east_twelve[1], 0.)
        self.assertTrue(contains(center, east_twelve))
        self.assertFalse(contains(center, east_thirteen))
        self.assertTrue(contains(center, diagonal))

    def test_every_offer_shape_has_correct_tile_containment(self):
        rng = np.random.default_rng(8055)
        for group in range(8):
            for layout in ("neighboring", "dispersed"):
                for _ in range(100):
                    truth, offered, absent, selected = geography(group, layout, rng)
                    self.assertEqual([i for i, p in enumerate(offered) if contains(p, truth)], [selected])
                    self.assertTrue(all(distance(p, truth) > 25. for p in absent))
                    self.assertTrue(all(distance(p, truth) > 25.
                                        for i, p in enumerate(offered) if i != selected))

    def test_velocity_matches_rotating_frame_position_derivative(self):
        sat = Satrec.twoline2rv(
            "1 25544U 98067A   19343.69339541  .00001764  00000-0  38792-4 0  9991",
            "2 25544  51.6445 211.2001 0007413  17.6667  85.6398 15.50103472202482",
            WGS72,
        )
        anchor = timestamp(datetime(2019, 12, 9, 17, tzinfo=UTC).isoformat())
        errors, positions, velocities = orbit_state([sat], anchor, np.array([1.9, 2., 2.1]))
        self.assertTrue((errors == 0).all())
        derivative = (positions[0, 2]-positions[0, 0])/.2
        np.testing.assert_allclose(derivative, velocities[0, 1], atol=3e-5, rtol=0.)
        observer, _ = station([34., -118.], 1.2)
        carrier = 11.55e9
        ranges = np.linalg.norm(positions[0]-observer, axis=-1)
        expected = -(carrier/299792.458) * (ranges[2]-ranges[0])/.2
        self.assertAlmostEqual(expected, projection(positions[0, 1], velocities[0, 1],
                                                   observer, carrier), delta=.9)

    def test_exact_retrieval_timestamp_conversion(self):
        self.assertEqual(timestamp("1970-01-02T00:00:01.012345Z"), 86401*NS + 12345000)


if __name__ == "__main__":
    unittest.main()
