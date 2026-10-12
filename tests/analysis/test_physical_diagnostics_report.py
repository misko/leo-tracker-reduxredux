import numpy as np
import pytest

from leo.analysis.sparse_glrt_likelihood import FrequencyEvidence
from leo.analysis.wrapped_glrt_likelihood import WrappedConfig, nuisance_design, wrapped_ratios
from tools.report_wrapped_physical_diagnostics import paired_summary, replay_endpoint


def test_saved_endpoint_replay_detects_density_prior_and_weight_tampering():
    time = np.arange(8, dtype=float)
    data = FrequencyEvidence(
        ids=tuple(map(str, range(8))),
        time_s=time,
        group=np.arange(8) % 2,
        frequency_hz=np.zeros((8, 1)),
        candidate_weight=np.ones((8, 1)),
        signal_probability=np.ones(8),
    )
    rf = np.full(8, 11e9)
    cfg = WrappedConfig(relative_phase_sigma_s=1)
    design, _, _ = nuisance_design(data, rf)
    prediction, opportunity = np.zeros((8, 1)), np.ones((8, 1))
    beta = np.zeros(design.shape[1])
    ratio = wrapped_ratios(data, prediction, opportunity, design, beta, cfg)
    raw = float(np.log(0.2 + ratio[:, 0] * 0.8).sum())
    fit = dict(
        coefficient_enabled=False,
        weights=[0.2, 0.8],
        active=[0],
        beta=beta,
        phase_s=0.0,
        satellite_phase_s=[0.0],
        log_ratio=raw,
        score=raw - cfg.satellite_penalty,
    )
    replay_endpoint(data, rf, prediction, opportunity, fit, cfg)
    for changed in (dict(fit, score=fit["score"] + 1), dict(fit, satellite_phase_s=[2])):
        with pytest.raises(ValueError, match="accounting does not replay"):
            replay_endpoint(data, rf, prediction, opportunity, changed, cfg)
    with pytest.raises(ValueError, match="not normalized"):
        replay_endpoint(data, rf, prediction, opportunity, dict(fit, weights=[0.3, 0.8]), cfg)


def test_physical_probe_comparison_rejects_changed_starts_and_unmatched_locations():
    base = dict(
        input_digest="input",
        orbit_digest="orbit",
        candidate_norad=[20],
        seeds=[0],
        site={},
        phase_receipt={},
        candidate_pool_digest="pool",
        random_seed=0,
        search_plan={},
        config={"iterations": 3, "band_drift_sigma_hz_s": None},
    )
    rows = [
        dict(
            east_m=0.0,
            north_m=0.0,
            distance_m=0.0,
            arms={"zero-c": {"score": 1.0}, "fitted-c": {"score": 2.0}},
        )
    ]
    assert paired_summary(base, base, rows, rows)[0]["reference_gain"] == 0
    with pytest.raises(ValueError, match="starting states"):
        paired_summary(base, dict(base, seeds=[1]), rows, rows)
    with pytest.raises(ValueError, match="locations differ"):
        paired_summary(base, base, rows, [dict(rows[0], east_m=1.0)])
    with pytest.raises(ValueError, match="iteration budgets differ"):
        paired_summary(base, dict(base, config={"iterations": 4}), rows, rows)
    assert (
        paired_summary(
            base, dict(base, config={"iterations": 3, "band_drift_sigma_hz_s": 1.0}), rows, rows
        )[0]["reference_gain"]
        == 0
    )
