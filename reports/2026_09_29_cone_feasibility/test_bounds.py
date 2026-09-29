"""Independent geometry checks for conservative hard-cone exclusions."""

import math
import unittest

import numpy as np
from bounds import candidate_lower_bounds, geographic_envelope


def receiver_and_frame(lat_deg, lon_deg):
    lat, lon = np.radians([lat_deg, lon_deg])
    a, e2 = 6378.137, 6.69437999014e-3
    n = a / np.sqrt(1 - e2 * np.sin(lat) ** 2)
    receiver = np.array(
        [n * np.cos(lat) * np.cos(lon), n * np.cos(lat) * np.sin(lon), n * (1 - e2) * np.sin(lat)]
    )
    frame = np.array(
        [
            [-np.sin(lon), np.cos(lon), 0],
            [-np.sin(lat) * np.cos(lon), -np.sin(lat) * np.sin(lon), np.cos(lat)],
            [np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)],
        ]
    )
    return receiver, frame


def angle(v, axis):
    return np.degrees(np.arctan2(np.linalg.norm(np.cross(v, axis), axis=-1), v @ axis))


class Tests(unittest.TestCase):
    def test_geographic_envelope_contains_receiver_and_rotated_axes(self):
        rng = np.random.default_rng(82718)
        for lat in (-70, -37.85625, 0, 37.85625, 70):
            r0, frame0 = receiver_and_frame(lat, -122.484375)
            bound = geographic_envelope(lat)
            for east, north in np.r_[
                rng.uniform(-12, 12, (100, 2)), [[-12, -12], [-12, 12], [12, -12], [12, 12]]
            ]:
                r, frame = receiver_and_frame(
                    lat + north / 111.195,
                    -122.484375 + east / (111.195 * math.cos(math.radians(lat))),
                )
                self.assertLessEqual(np.linalg.norm(r - r0), bound["receiver_radius_km"])
                for v in (
                    [-math.sin(math.pi / 18), 0, math.cos(math.pi / 18)],
                    [math.sin(math.pi / 18), 0, math.cos(math.pi / 18)],
                ):
                    self.assertLessEqual(
                        angle(np.array(v) @ frame, np.array(v) @ frame0),
                        bound["axis_rotation_deg"] + 1e-12,
                    )

    def test_exact_stationary_candidate_and_whole_training_track(self):
        a = np.radians([[10, 35, 80], [15, 15, 60]])
        rays = np.stack([np.sin(a), np.zeros_like(a), np.cos(a)], axis=-1) * 500
        positions = np.repeat(rays[:, None], 3, axis=1)
        lower = candidate_lower_bounds(positions, [True, True, False], [0, 0, 0], [0, 0, 1], 0, 0)
        np.testing.assert_allclose(lower, [35, 15], atol=2e-8, rtol=0)
        positions[:, :, 2] += 20000
        np.testing.assert_array_equal(
            lower,
            candidate_lower_bounds(positions, [True, True, False], [0, 0, 0], [0, 0, 1], 0, 0),
        )

    def test_random_actual_geometry_never_below_bound(self):
        rng = np.random.default_rng(91828)
        lat, lon = 37.85625, -122.484375
        r0, frame0 = receiver_and_frame(lat, lon)
        axis_enu = np.array([-math.sin(math.pi / 18), 0, math.cos(math.pi / 18)])
        direction = rng.normal(size=(6, 7, 3))
        direction /= np.linalg.norm(direction, axis=-1)[..., None]
        base = r0 + direction * rng.uniform(500, 1200, (6, 7, 1))
        velocity = rng.normal(size=(6, 7, 3)) * 4
        p = base[:, None] + np.linspace(-5, 5, 5)[None, :, None, None] * velocity[:, None]
        mask = np.array([True, False, True, True, False, True, False])
        bound = geographic_envelope(lat)
        lower = candidate_lower_bounds(p, mask, r0, axis_enu @ frame0, **bound)
        self.assertGreaterEqual(np.count_nonzero(lower > 5), 4)
        for _ in range(400):
            east, north = rng.uniform(-12, 12, 2)
            r, frame = receiver_and_frame(
                lat + north / 111.195, lon + east / (111.195 * math.cos(math.radians(lat)))
            )
            seg, weight = int(rng.integers(4)), rng.uniform()
            actual = p[:, seg] * (1 - weight) + p[:, seg + 1] * weight - r
            worst = angle(actual[:, mask], axis_enu @ frame).max(axis=1)
            self.assertTrue(np.all(lower <= worst + 1e-10))

    def test_segment_with_axis_crossing_cannot_be_excluded(self):
        p = np.array([[[[500, 0, 500]], [[-500, 0, 500]]]], dtype=float)
        lower = candidate_lower_bounds(p, [True], [0, 0, 0], [0, 0, 1], 0, 0)
        np.testing.assert_array_equal(lower, [0])
        self.assertGreater(angle(p[0, 0, 0], np.array([0, 0, 1])), 40)
        self.assertGreater(angle(p[0, 1, 0], np.array([0, 0, 1])), 40)

    def test_los_ball_reaching_receiver_gives_no_exclusion(self):
        p = np.array([[[[1.0, 0, 0]], [[1.0, 0, 0]]]])
        for radius in (1, 2):
            np.testing.assert_array_equal(
                candidate_lower_bounds(p, [True], [0, 0, 0], [0, 0, 1], radius, 0), [0]
            )

    def test_enlarging_domain_cannot_strengthen_exclusion(self):
        rng = np.random.default_rng(121)
        p = rng.uniform(200, 700, (3, 4, 5, 3))
        args = (p, np.ones(5, dtype=bool), [0, 0, 0], [0, 0, 1])
        a = candidate_lower_bounds(*args, 0, 0)
        b = candidate_lower_bounds(*args, 18, 0.3)
        c = candidate_lower_bounds(*args, 40, 2)
        self.assertTrue(np.all(a >= b) and np.all(b >= c))

    def test_reject_invalid_domains(self):
        for args in ((90,), (89.99, 12, 12), (0, -1, 12), (float("nan"),)):
            with self.assertRaises(ValueError):
                geographic_envelope(*args)
        p = np.ones((1, 2, 1, 3))
        with self.assertRaises(ValueError):
            candidate_lower_bounds(p, [False], [0, 0, 0], [0, 0, 1], 1, 0)
        with self.assertRaises(ValueError):
            candidate_lower_bounds(p, [True], [0, 0, 0], [0, 0, 2], 1, 0)


if __name__ == "__main__":
    unittest.main()
