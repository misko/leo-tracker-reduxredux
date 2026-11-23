"""The frozen short margin modifies diagonal noise and both volumes directly."""

from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3.predictive_linear import predictive_residual

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from short_margin_variance import scales, set_normal_scales


def test_variance_is_bounded_and_never_changes_anchor_or_order():
    base = np.array([80., 125., 550., 110.])
    ids = ("full", "short", "clipped", "last")
    factors = {"last": 1.1, "short": 2., "full": 1., "clipped": 2.}
    assert scales(base, ids, factors, weighted=False) is base
    candidate = scales(base, ids, factors, weighted=True)
    assert candidate[0].hex() == base[0].hex()
    assert candidate[2] == 600.
    assert (candidate / base)**2 == pytest.approx([1., 2., (600 / 550)**2, 1.1])
    assert base.tolist() == [80., 125., 550., 110.]


def test_unknown_or_nonfinite_precision_is_rejected():
    with pytest.raises(KeyError):
        scales([80.], ["unbound"], {}, weighted=True)
    with pytest.raises(ValueError, match="finite measurement"):
        scales([np.nan], ["short"], {"short": 2.}, weighted=True)


def test_curved_log_volume_uses_new_sigmas_and_kept_mask():
    sigma = np.array([80., 200., 110.])
    model = SimpleNamespace(keep=np.array([True, False, True]), point_power=np.array([.5, .7, 1.]))
    set_normal_scales(model, sigma)
    assert model.point_noise is sigma
    assert model.noise_volume == pytest.approx(2 * np.log(80 * 110 / 40**2))
    assert model.diagonal_logvolume == pytest.approx(np.log(2) + 1.4 * np.log(5) + 2 * np.log(2.75))


def test_predictive_noise_changes_its_gaussian_normalization_and_innovation():
    sigma = np.array([50., 80.])
    candidate = scales(sigma, ["full", "short"], {"full": 1., "short": 2.}, weighted=True)
    raw = np.array([10., -35.])
    kwargs = dict(design=np.empty((2, 0)), curved_gram=np.empty((0, 0)), groups=np.array([0, 1]), bias_sigma=0.)
    before = predictive_residual(raw, sigma=sigma * np.sqrt(2.), **kwargs)
    after = predictive_residual(raw, sigma=candidate * np.sqrt(2.), **kwargs)
    assert after["normalization_constant"] - before["normalization_constant"] == pytest.approx(np.log(2))
    assert after["quadratic"] - before["quadratic"] == pytest.approx(-35**2 / (4 * 80**2))
