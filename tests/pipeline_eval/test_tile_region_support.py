import numpy as np

from tools.pipeline_eval.qualification.tile_region_support_trials import edge_offer
from tools.pipeline_eval.variants import portable_gate, tile_region_empirical
from tools.pipeline_eval.variants import tile_region_support as region


class Cartesian:
    def latlon(self, point):
        return point


class PlantedDoppler:
    """A local range-rate linearization with complementary independent orbit slopes."""

    slopes = np.array([[180, 40], [10, 210], [200, -50], [-80, 250]])

    def evaluate(self, times, east, north):
        t = np.asarray(times)[None, :] / 10
        amplitude = (self.slopes @ [east, north])[:, None]
        f = amplitude * t + 80 * t**2
        return f, np.ones_like(f), np.zeros_like(f)


def make_model(monkeypatch, point, model_type=region.FixedOrbitModel):
    source = PlantedDoppler()
    train, held = np.arange(16), np.arange(16, 24)
    first = source.evaluate(train, *point)[0]
    last = source.evaluate(held, *point)[0]
    rows = [
        (
            j,
            [
                portable_gate.Arc(
                    j + 1, 1.0, j, train, first[j] + j * 8000, held, last[j] + j * 8000
                )
            ],
        )
        for j in range(4)
    ]
    monkeypatch.setattr(region.orbit_projector, "prepare", lambda bank, times: times)
    sky = dict(
        time_s=train, position_km=np.zeros(4), velocity_km_s=np.zeros(4), phase_sigma_s=np.ones(4)
    )
    return model_type(rows, sky, Cartesian(), source)


def test_unrestricted_and_same_ids_exterior_distinguish_just_inside_and_outside(monkeypatch):
    radius, limit = 12.5, 125.0
    for truth, expected_sign in (([11, -4], 1), ([45, -12], -1)):
        model = make_model(monkeypatch, truth)
        free = model.fit([6, 0], [-limit, -limit], [limit, limit])
        inside = model.fit(free.x, [-radius, -radius], [radius, radius])
        outside = region.exterior(model, free.x, radius, limit)
        assert np.allclose(free.x, truth, atol=0.01)
        assert np.max(np.abs(inside.x)) <= radius
        assert np.max(np.abs(outside.x)) >= radius
        a, _ = model.held(inside.x)
        b, _ = model.held(outside.x)
        assert expected_sign * region.stable_held_difference(a - b) > 0
        far = model.fit(free.x, [-limit, -limit], [limit, limit], omitted=0)
        assert np.allclose(far.x, free.x, atol=0.01)


def test_region_mass_can_support_precise_edge_but_not_wide_or_exterior():
    precise = np.diag([0.1, 0.3]) ** 2
    point = np.array([11, 4])
    assert region.tile_mass_lower_bound(point, precise, 12.5) > region.MASS
    assert region.tile_mass_lower_bound(point, precise * 1000, 12.5) < region.MASS
    assert region.tile_mass_lower_bound(np.array([60, 0]), precise, 12.5) == 0
    assert region.stable_held_difference(np.array([10.0, -1, -1, -1])) < 0


def test_edge_control_exact_clearance_at_high_latitude():
    truth = [68.1, -30.5]
    offered = edge_offer(truth, np.random.default_rng(4))
    lat, lon = offered["center"]
    offset = [(truth[1] - lon) * 111.32 * np.cos(np.deg2rad(lat)), (truth[0] - lat) * 111]
    assert np.isclose(offered["width_km"] / 2 - np.max(np.abs(offset)), 1.5)


def test_development_noise_changes_information_without_moving_fits(monkeypatch):
    assert tile_region_empirical.orbit_scale([24**2] * 12) == 40
    assert np.isclose(tile_region_empirical.orbit_scale([60**2] * 4), 60 * np.sqrt(2))
    truth = [11, -4]
    stock = make_model(monkeypatch, truth)
    model = make_model(monkeypatch, truth, model_type=tile_region_empirical.CalibratedOrbitModel)
    args = ([6, 0], [-125, -125], [125, 125])
    original, adjusted = stock.fit(*args), model.fit(*args)
    assert np.allclose(original.x, adjusted.x)
    assert np.allclose(adjusted.jac[:-4], original.jac[:-4] * 150 / 40)
    assert np.array_equal(original.jac[-4:], adjusted.jac[-4:])
    assert np.allclose(stock.held(original.x)[0], model.held(adjusted.x)[0])
