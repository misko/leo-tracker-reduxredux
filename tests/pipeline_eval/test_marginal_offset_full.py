"""Check prospective publication denominators and the frozen cohort partition."""

import pytest

from tools.pipeline_eval.qualification import marginal_offset_full_results as study
from tools.pipeline_eval.qualification import screening_figures
from tools.pipeline_eval.scoring import ARMS


def row(ident, error):
    return dict(
        id=ident,
        error_km=error,
        forced_error_km=7.0 if error is None else error,
        status="withheld" if error is None else "ok",
        reason="held" if error is None else None,
        final_raw_rms_hz=200.0,
        held_raw_rms_hz=100.0,
        held_marginal_loss_per_point=1.0,
        held_relative_logdet_per_point=0.1,
        held_quadratic_and_phase_prior_per_point=0.9,
        geometry_radius_km=2.0,
    )


def test_common_fix_and_all_attempt_distributions_use_their_own_exact_denominators():
    pairs = [
        (row("both", 2.0), row("both", 1.0)),
        (row("offset", 4.0), row("offset", None)),
        (row("zero", None), row("zero", 9.0)),
        (row("neither", None), row("neither", None)),
    ]
    result = study.compare(pairs)
    assert result["matched_publication_counts"] == dict(
        both=1, offset_only=1, zero_only=1, neither=1
    )
    assert result["common_fix_ids"] == ["both"]
    assert result["common_fix_paired_error_delta_km"]["p50"] == 1.0
    first, second = (result["all_attempts"][k] for k in study.METHODS)
    assert first["all_attempts_fraction_within_km"]["5"] == 0.5
    assert second["all_attempts_fraction_within_km"]["5"] == 0.25
    assert first["all_attempts_error_km"] == {"p50": 4.0, "p95": None, "worst": None}
    assert first["published_error_km"]["p95"] == pytest.approx(3.9)
    assert first["forced_error_km"]["n"] == 4


def test_standard_cards_keep_all_attempts_in_each_frozen_cohort_and_arm():
    charts = screening_figures.charts([study.METHODS[0]], evidence=study.trial.REPORT)
    assert {c.id: len(c.cases) for c in charts} == {
        "marginal_full-roof": 135,
        "marginal_full-unseen": 125,
        "marginal_full-diagnostic": 4,
        "marginal_full-prior-salted": 6,
        "marginal_full-omitted": 9,
    }
    by_name = {c.id: c for c in charts}
    roof = set(by_name["marginal_full-roof"].cases)
    groups = [
        set(by_name[f"marginal_full-{group}"].cases)
        for group in ("unseen", "diagnostic", "prior-salted")
    ]
    assert set.union(*groups) == roof
    assert sum(map(len, groups)) == len(roof)
    for arm in ARMS:
        for c in charts:
            key = "one" if c.scope == "roof" else "candidate"
            assert sum(row.series == key for row in c.page(arm).rows) == len(c.cases)
