"""Synthetic checks for the position grid and integrated timing score."""

import math

import numpy as np
from scipy.integrate import quad

import grid


def fixture():
    n = 12
    t = np.linspace(-1, 1, grid.cold.SAMPLES)
    basis, _ = np.linalg.qr(np.stack([t**i for i in range(4)], axis=1))
    east, north, timing = (basis[:, i] * np.sqrt(len(t)) * scale
                           for i, scale in zip((1, 2, 3), (440.0, 550.0, 800.0), strict=True))
    group = np.arange(n) % 4
    rf = (np.arange(n) // 4) * 0.18 - 0.80
    xy = (grid.HALF_WIDTH_KM * 2 / 21, -grid.HALF_WIDTH_KM * 2 / 21)
    true_c = 6400.0
    raw = np.empty((n, 2, len(t), 4))
    for i in range(n):
        raw[i, :, :, 1] = np.roll(east, i)
        raw[i, :, :, 2] = np.roll(north, i)
        raw[i, :, :, 3] = np.roll(timing, i) + 250
        raw[i, 0, :, 0] = raw[i, 0, :, 1:] @ np.r_[xy, 0.35] + rf[i] * true_c
        raw[i, 1, :, 0] = raw[i, 0, :, 0] + 9000 + 2000 * np.roll(east, i) / 440
    mean, cov = grid.cold.tile_stats(raw)
    d = dict(raw=raw, mean=mean, cov=cov, group=group, rf=rf)
    return d, xy, true_c


def run_checks():
    data, xy, true_c = fixture()
    model = grid.Mixture(data, np.zeros(4), fitted=True)
    calibration = np.r_[np.zeros(4), true_c / 200_000]
    _, _, component, _ = model.components(model.position_terms(xy), calibration)
    row = data["raw"][0, 0]
    residual = row[:, 0] - row[:, 1:3] @ xy - data["rf"][0] * true_c
    residual -= grid.cold.PERIOD * np.rint(residual.mean() / grid.cold.PERIOD)

    def integrand(tau):
        error = residual - tau * row[:, 3]
        level = error.mean()
        energy = (np.mean((error - level)**2) / grid.cold.SHAPE_SD**2
                  + (level / grid.cold.LEVEL_SD)**2 + (tau / grid.cold.PHASE_SD_S)**2)
        return math.exp(-energy / 2) / (math.sqrt(2 * math.pi) * grid.cold.PHASE_SD_S)

    quadrature, _ = quad(integrand, -20, 20, epsabs=1e-12)
    integration_error = abs(math.log(quadrature) - (component[0, 0] - model.candidate_log_prior))
    assert integration_error < 1e-10

    coarse, leaves, _ = grid.search(model)
    best_coarse = max(coarse, key=lambda cell: cell.score)
    best = max(leaves, key=lambda cell: cell.score)
    assert len(coarse) == 49 and len(leaves) == 113
    assert len({cell.xy for cell in leaves}) == len(leaves)
    assert math.isclose(sum(cell.width**2 for cell in leaves), 625)
    assert all(abs(c) + cell.width/2 <= grid.HALF_WIDTH_KM + 1e-9 for cell in leaves for c in cell.xy)
    assert best.score > best_coarse.score
    assert math.dist(best.xy, xy) < 1e-9

    zero_model = grid.Mixture(data, np.zeros(4), fitted=False)
    zero = zero_model.fit(xy, 1.0, 0)
    assert best.score > zero.score
    return dict(phase_quadrature_log_error=integration_error, synthetic_position_error_km=math.dist(best.xy, xy),
                synthetic_coarse_error_km=math.dist(best_coarse.xy, xy), covered_area_km2=625,
                synthetic_fitted_over_c0_score=best.score - zero.score, coarse_cells=49, final_cells=113)


def test_grid():
    run_checks()


if __name__ == "__main__":
    print(run_checks())
