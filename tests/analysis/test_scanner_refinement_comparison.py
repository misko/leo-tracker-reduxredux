import numpy as np
import pytest

from leo.analysis.starlink.refinement_comparison import (
    RefinementProbe,
    compare_probe,
    comparison_metrics,
    select_candidate,
)
from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tests.scanner.refinement_fixtures import comparison_fixture


def test_known_shift_errors_and_failure_denominators_are_independent_of_fit():
    evidence = comparison_fixture()
    metrics = comparison_metrics(evidence.rows)
    assert [m.cfo_rms_hz for m in metrics[:4]] == pytest.approx([80, 6, 0.5, 0.2])
    assert [m.delay_rms_ns for m in metrics[4:]] == pytest.approx([20, 20, 20, 2])
    rows = tuple(
        r.model_copy(update={"selected_rank": None})
        if r.profile == "joint512" and r.case == "baseline"
        else r
        for r in evidence.rows
    )
    changed = comparison_metrics(rows)
    assert all(m.common == 0 and m.cfo_rms_hz is None for m in changed)
    assert changed[0].attempted == changed[0].recovered == 1
    assert changed[3].attempted == 1 and changed[3].recovered == 0


def test_alias_is_preserved_as_raw_error_and_counted():
    evidence = comparison_fixture()
    rows = tuple(
        r.model_copy(
            update={
                "candidates": (
                    r.candidates[0].model_copy(
                        update={"cfo_hz": r.candidates[0].cfo_hz + 1 / 4.4e-6}
                    ),
                )
            }
        )
        if r.profile == "local512" and r.case == "frequency"
        else r
        for r in evidence.rows
    )
    metric = comparison_metrics(rows)[2]
    assert metric.cfo_rms_hz == pytest.approx(0.5)
    assert metric.raw_cfo_rms_hz > 227000
    assert metric.alias_changes == 1


def test_selection_uses_score_and_physical_phase_without_a_cfo_oracle():
    c = comparison_fixture().rows[0].candidates[0]
    better = c.model_copy(update={"rank": 1, "exact_score": 0.9, "cfo_hz": 900000})
    assert select_candidate((c, better), 0.0001) == better
    assert (
        select_candidate((better.model_copy(update={"integer_epoch_s": 0.000102}),), 0.0001) is None
    )


@pytest.mark.parametrize("fs", [2500000, 5000000, 10000000])
def test_real_numerical_comparison_reacquires_each_known_shift(fs):
    samples = np.zeros(round(fs * 0.021), dtype=complex)
    template = np.asarray(qin_edge_pilot_frame(fs, "lower"))
    for frame in range(15):
        start = 173 + round(frame * fs / 750)
        count = min(len(template), len(samples) - start)
        if count > 0:
            samples[start : start + count] += template[:count]
    samples *= np.exp(2j * np.pi * 40137.19 * np.arange(len(samples)) / fs)
    rows = compare_probe(RefinementProbe("fixture:0:0", 0, 0, 0, 0, fs, "lower", samples))
    assert len(rows) == 12
    assert all(r.selected is not None for r in rows)
    metrics = comparison_metrics(rows)
    assert metrics[2].raw_cfo_rms_hz < 2
    assert metrics[3].raw_cfo_rms_hz < 2
    assert metrics[7].delay_rms_ns < 30
