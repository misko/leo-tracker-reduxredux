import numpy as np

from leo.analysis.localization_v3 import position
from leo.analysis.localization_v3.hierarchical import hierarchical_bound
from leo.analysis.localization_v3.marginal import absolute_phase_linearization
from reports.ALGO08.v3.cold_finalist_race import Pause, choose, stock_coroutine
from tools.pipeline_eval.variants.compact_cavity_optimizer import bounded_secant


def test_group_rate_profile_bounds_the_released_score_even_before_convergence():
    noise = np.array([40., 80., 100., 200., 600.])
    measured = np.array([1600., -100., 320., -280., 310.])
    design = np.array([[100., 0.], [100., 35.], [100., -20.], [0., -150.], [0., 90.]])
    groups = np.array([0, 0, 0, 1, 1])
    result = hierarchical_bound(measured, design, noise, groups, iterations=1)

    residual = (measured - design @ result["coefficient"]) / noise
    energies = np.bincount(groups, weights=residual**2)
    group_floor = (4 + np.bincount(groups)) @ np.log1p(energies / 4)
    coefficient_cost = result["coefficient"] @ result["coefficient"]
    noise_volume = 2 * np.log(noise / 40).sum()
    score = result["residual"] @ result["residual"] + noise_volume
    assert result["precision_iterations"] == 1
    assert group_floor + coefficient_cost + result["logvolume"] + noise_volume <= score
    assert noise_volume <= score


def test_a_finalist_can_lose_the_prefix_and_win_after_the_phase_reference_moves(monkeypatch):
    linear = 70. * np.array([1., -1., 1., -1.])
    quadratic = 3. * np.array([1., 1., -1., -1.])
    contrast = np.array([1., -1., -1., 1.])
    measured = linear * 15 + quadratic * 15**2
    flat = np.zeros(4)
    noise = np.full(4, 80.)
    groups = np.zeros(4, dtype=int)

    class Assignment:
        """Fixed rows and aliases, with a quadratic Doppler curve in orbit phase."""

        def __init__(self, _scan, node, _sigma, _fitted_c, *, reference):
            nominal, slope, curvature = node["geometry"]
            phase = reference[0]
            derivative = slope + 2 * curvature * phase
            frequency = nominal + slope * phase + curvature * phase**2
            intercept = absolute_phase_linearization(frequency, derivative, phase)
            self.raw = measured - intercept
            self.design = np.column_stack((np.full(4, 1000.), 15 * derivative))
            self.lower, self.upper = np.full(2, -12.5), np.full(2, 12.5)
            self.keep = np.ones(4, dtype=bool)
            self.labels = np.array([0])

        def calculate(self, _point):
            return hierarchical_bound(self.raw, self.design, noise, groups)

        def residual(self, point):
            noise_volume = 2 * np.log(noise / 40).sum()
            return np.r_[self.calculate(point)["residual"], np.sqrt(noise_volume), 0.5]

        def state(self, point):
            return {"phases": self.calculate(point)["coefficient"][1:] * 15}

    geometries = [
        (measured - 300 * contrast, flat, flat),
        (flat, linear, quadratic),
        (measured - 1500 * contrast, flat, flat),
    ]
    nodes = [
        dict(geometry=shape, seed=dict(rows=[dict(candidate_index=0)])) for shape in geometries
    ]
    optimizer = stock_coroutine(bounded_secant)
    prefix = []
    for node in nodes:
        model = Assignment(None, node, 80., False, reference=np.zeros(1))
        pause = Pause(optimizer, model.residual, model.lower, model.upper)
        prefix.append(pause.prefix())
        pause.close()
    assert choose(prefix, 12.5)[:2] == (0, "winner_raced")

    monkeypatch.setattr(position, "NormalPosition", Assignment)
    monkeypatch.setattr(position, "bounded_gauss_newton", bounded_secant)
    fits = [position.refreshed(None, 80., node, "c0", rounds=2) for node in nodes]
    assert fits[1][2][1]["phase_reference"][0] > 10
    assert fits[1][2][0]["fit"]["score"] == prefix[1]["score"]
    assert fits[1][1]["score"] < fits[0][1]["score"] < fits[2][1]["score"]
    for _, result, _ in fits:
        np.testing.assert_array_equal(result["parameters"], np.zeros(2))
