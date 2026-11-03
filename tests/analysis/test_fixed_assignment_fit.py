"""Fixed labels retain bad observations and the solve matches dense Gaussian LS."""

import importlib
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.research.fixed_assignment_fit import (
    common_candidate_phase_scores,
    fixed_assignment_score,
    improve_fixed_assignments,
)
from leo.analysis.research.shared_orbit_phase_fit import augment_phase_statistics


def fixture(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    matching = importlib.import_module("analyze_dsx01_fixed_site")
    times = np.arange(0.0, 301, 3)
    f = np.stack([50000 - 1500 * times + 0.5 * times**2, 40000 - 1100 * times + 0.1 * times**2])
    h = np.stack([3000 + 0.02 * (times - 150) ** 2, np.zeros_like(times)])
    beta = np.array([100.0, 0, -200, 0, 30, 0, -15, 0])
    groups = []
    for ci, keep in enumerate((times <= 90, times >= 210)):
        t, members = times[keep], []
        q = (10.94 + 0.25 * ci) / 11.5
        for g in (0, 2):
            y = (
                q * (f[0, keep] + h[0, keep] * 0.4)
                + beta[g]
                + beta[g + 4] * (t - 150) / 150
                + (-200 if ci == 0 else 200)
            )
            members.append(
                dict(
                    key=f"{ci}-{g}",
                    receiver=g // 2 + 1,
                    channel=ci + 1,
                    rf_hz=q * 11.5e9,
                    times=t,
                    values=y,
                )
            )
        groups.append((str(ci), members))
    stats = matching.statistics(
        groups, dict(time_s=times, doppler_0=f, elevation_deg=np.full_like(f, 45)), {"1": 0, "2": 0}
    )
    return augment_phase_statistics(stats, times, f, h), times, f, h


def test_fixed_update_matches_independent_dense_point_solve(monkeypatch):
    stats, times, f, h = fixture(monkeypatch)
    labels = np.zeros(2, int)
    fitted = improve_fixed_assignments(
        stats, np.zeros(8), np.zeros(2), np.full(2, 1.2), np.full(2, 5.0), labels
    )
    rows, values = [], []
    for fi, t in enumerate(stats["fragments"]):
        ci, group = stats["ci"][fi], stats["g"][fi]
        indexes = np.searchsorted(times, t["times"])
        g = 0 if group == 0 else 1
        a = np.zeros((len(indexes), 7))
        a[:, g] = 1
        a[:, g + 2] = (t["times"] - 150) / 150
        a[:, 4] = stats["q"][fi] * h[0, indexes]
        a[:, 5 + ci] = 1
        weight = np.sqrt(min(1, 50 / stats["count"][ci]))
        rows.extend(weight * a)
        values.extend(weight * (t["values"] - stats["q"][fi] * f[0, indexes]))
    for i, precision in [
        (2, 2),
        (3, 2),
        (4, 150 / 1.2),
        (5, np.sqrt(50 / 62) * 150 / 1000),
        (6, np.sqrt(50 / 62) * 150 / 1000),
    ]:
        row = np.zeros(7)
        row[i] = precision
        rows.append(row)
        values.append(0)
    expected = np.linalg.lstsq(np.asarray(rows), np.asarray(values), rcond=None)[0]
    actual = np.r_[
        fitted["beta"][[0, 2, 4, 6]], fitted["phases_s"][0], fitted["evidence"]["component_bias_hz"]
    ]
    np.testing.assert_allclose(actual, expected, atol=1e-6)
    assert np.all(np.diff(fitted["score_history"]) < 0)
    assert fitted["evidence"]["points_rejected"] == 0
    np.testing.assert_array_equal(fitted["evidence"]["labels"], labels)


def test_fixed_score_cannot_switch_to_better_candidate_or_cap_bad_members(monkeypatch):
    stats, _, _, _ = fixture(monkeypatch)
    args = (stats, np.zeros(8), np.zeros(2), np.ones(2))
    first, _ = fixed_assignment_score(*args, np.zeros(2, int))
    wrong, _ = fixed_assignment_score(*args, np.ones(2, int))
    assert wrong["score"] > first["score"]
    assert wrong["component_rms_hz"].max() > 450
    assert wrong["points"] == sum(stats["n"])
    assert wrong["points_rejected"] == wrong["labels_changed"] == 0
    np.testing.assert_array_equal(wrong["labels"], np.ones(2, int))


def test_candidate_batch_equals_separate_models_with_one_phase_prior_each(monkeypatch):
    stats, _, _, _ = fixture(monkeypatch)
    phases, sigma = np.array([0.4, -0.2]), np.array([1.0, 1.5])
    values, _ = common_candidate_phase_scores(stats, np.zeros(8), phases, sigma)
    for j in range(2):
        single_phase = np.zeros(2)
        single_phase[j] = phases[j]
        separate, _ = fixed_assignment_score(
            stats, np.zeros(8), single_phase, sigma, np.full(2, j, int)
        )
        assert values[j] == pytest.approx(separate["score"])


def test_line_cannot_enter_a_fixed_family_calibration_indirectly(monkeypatch):
    stats, _, _, _ = fixture(monkeypatch)
    stats["fragment_active"][0] = False
    with pytest.raises(ValueError, match="only measured-curved"):
        improve_fixed_assignments(
            stats, np.zeros(8), np.zeros(2), np.ones(2), np.ones(2), np.zeros(2, int)
        )


@pytest.mark.parametrize("labels", [[-1, 0], [0, 2], [0], [0.0, 0.0]])
def test_fixed_labels_must_bind_existing_candidate_columns(monkeypatch, labels):
    stats, _, _, _ = fixture(monkeypatch)
    with pytest.raises(ValueError, match="candidate"):
        fixed_assignment_score(stats, np.zeros(8), np.zeros(2), np.ones(2), labels)
