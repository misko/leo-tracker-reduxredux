from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3.scan import ScanLikelihood
from leo.analysis.research import retained_track_likelihood as likelihood


@pytest.fixture
def trial(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    import representative_contrast_bound

    return representative_contrast_bound


@pytest.mark.parametrize("columns", (12, 20, 113))
def test_spread_pairs_have_no_reused_observation(trial, columns):
    i, j = trial.representative_pairs(columns)
    both = set(i) | set(j)
    assert len(both) == 2 * len(i)
    assert {0, columns-1} <= both
    assert len(i) <= trial.PAIR_LIMIT


def test_bound_on_all_alias_branches_and_incumbent(trial):
    rng = np.random.default_rng(3621)
    n = 43
    y = rng.normal(0, 193000, n)
    f = rng.normal(0, 40000, (50, n)) + rng.integers(-4, 5, (50, 1)) * likelihood.PERIOD
    inverse, _ = likelihood.whitening(np.arange(n))
    exact = likelihood.profile(y, f, inverse)
    scatter = trial.centered_lower(y, f, trial.representative_pairs(n))
    np.testing.assert_array_less(scatter / likelihood.NOISE**2, exact["cost"])
    np.testing.assert_array_less(scatter, n * exact["rms"]**2)
    for row, cost in zip(f, exact["cost"], strict=True):
        assert trial.incumbent_upper(y, row, np.diag(inverse)) >= cost
    midpoint = np.full(n, likelihood.PERIOD / 2)
    assert trial.incumbent_upper(midpoint, np.zeros(n), np.diag(inverse)) is None


@pytest.mark.parametrize("order", ("C", "F"))
def test_compaction_keeps_winning_diagnostics_and_all_feasible_counts(trial, order):
    rng = np.random.default_rng(4162)
    n = 51
    times = np.arange(n, dtype=float)
    y = rng.normal(0, 9000, n)
    curves = rng.normal(0, 90000, (151, n))
    curves[23] = y + 42 * np.sin(times) + likelihood.PERIOD
    curves[5] = y + 197 + rng.normal(0, 133, n)
    curves[98] = y + 40 + rng.normal(0, 140, n)
    f = np.array(curves, order=order)
    visible = np.arange(len(f)) % 5 != 0
    scan = SimpleNamespace(white=[likelihood.whitening(times)], tracks=[{"times": times}])
    original = lambda *args: ScanLikelihood.curve(scan, *args)
    expected = original(0, y, f, "receiver_smooth")
    counts = Counter()
    got = trial.checked_curve(original, scan, 0, y, f, "receiver_smooth", visible, counts)
    assert counts["contrast_rows_skipped"] > 0
    assert counts["horizon_rows_skipped"] > 0
    np.testing.assert_array_equal(got["passing"] & visible, expected["passing"] & visible)
    for mask in (visible, expected["passing"] & visible):
        j = np.argmin(np.where(mask, expected["cost"], np.inf))
        assert j == np.argmin(np.where(mask, got["cost"], np.inf))
        for key in ("alias", "rms", "bias", "cost", "innovations", "residual"):
            np.testing.assert_array_equal(got[key][j], expected[key][j])


def test_all_hidden_preserves_row_zero_and_exposes_compacted_rounding(trial):
    times = np.arange(25, dtype=float)
    y = times + 11000 * np.sin(times)
    f = np.asfortranarray(np.arange(9.)[:, None] * y)
    scan = SimpleNamespace(white=[likelihood.whitening(times)], tracks=[{"times": times}])
    original = lambda *args: ScanLikelihood.curve(scan, *args)
    exact = original(0, y, f, "shared_phase")
    terms = trial.checked_curve(original, scan, 0, y, f, "shared_phase", np.zeros(len(f), bool), Counter())
    assert terms["alias"][0] == exact["alias"][0]
    # Compaction maintains the row-zero decision. Some BLAS implementations
    # change an inner-product reduction with the new row width. The release
    # equivalence audit separately requires bytewise rank equality.
    for key in ("rms", "bias", "cost", "innovations", "residual"):
        np.testing.assert_allclose(terms[key][0], exact[key][0], rtol=0, atol=1e-9)


def test_full_rank_equivalence_rejects_diagnostic_rounding(trial, monkeypatch):
    from full_family_amortized_trial import equality

    rank = dict(ordered_nodes_sha256="original", all_norad_alias_sha256="same assignments",
                hypotheses=2, roster=120, tracks=30)
    control = dict(ranks=[rank], attempts=[], arms={}, status="ok")
    contrast = dict(control, ranks=[dict(rank, ordered_nodes_sha256="different diagnostics")])
    check = equality(control, contrast)
    assert not check["ordered_rank"]
    assert all(value for key, value in check.items() if key != "ordered_rank")
