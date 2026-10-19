"""Protect measurement denominators and masked-track association accounting."""

from types import SimpleNamespace

import audit_ds23_algo01_coverage as module
import numpy as np
import pytest


def test_secondary_peaks_do_not_inflate_original_winner_coverage():
    tracks = [dict(key="a", observation_ids=["winner", "secondary"])]
    rows = [dict(component="a", compatible=True)]
    result = module.coverage(rows, tracks, {"winner", "unassigned"})
    assert result["associated_original_winners"] == 1
    assert result["associated_original_percent"] == 50
    assert result["associated_additional_peaks"] == 1
    assert result["associated_distinct_measurements"] == 2


def test_masked_suffix_counts_only_its_explicit_measurements_and_rejects_double_ownership():
    tracks = [dict(key="a", observation_ids=["bad-prefix", "suffix"])]
    row = dict(component="a", compatible=True, observation_ids=["suffix"])
    result = module.coverage([row], tracks, {"bad-prefix", "suffix"})
    assert result["associated_original_winners"] == 1
    with pytest.raises(ValueError, match="multiple accepted owners"):
        module.coverage([row, row], tracks, {"suffix"})


def test_rejected_prefix_cannot_fail_or_inflate_a_retained_suffix():
    n = 32
    values = np.r_[np.full(8, 8000.0), np.random.default_rng(123).normal(0, 30, 24)]
    track = dict(
        key="curve",
        times=np.arange(n, dtype=float),
        values=values,
        rf_hz=11.5e9,
        receiver=1,
        channel=2,
        observation_ids=[str(i) for i in range(n)],
    )
    scan = SimpleNamespace(
        tracks=[track], rx_basis=[np.zeros((n, 1))], hardware=lambda t, beta: np.zeros(n)
    )
    p = SimpleNamespace(
        scan=scan,
        rows=[dict(candidate_index=0, candidate_norad=123)],
        members=[0],
        slices=[slice(0, n)],
        alias=[0],
        supported=[],
        keep=np.arange(n) >= 8,
        state=lambda x: dict(beta=np.zeros(8), smooth=np.zeros((2, 1))),
        calculate=lambda x: dict(conditional_residual_hz=values),
        conditional_frequency=lambda x: (np.zeros(n), np.full(n, 30.0)),
    )
    result = module.retained_metrics(p, np.zeros(2))
    assert result["accepted_points"] == 24
    assert result["tracks"][0]["observation_ids"] == [str(i) for i in range(8, n)]
    p.keep[:] = True
    assert module.retained_metrics(p, np.zeros(2))["accepted_points"] == 0
