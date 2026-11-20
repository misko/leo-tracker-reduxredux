import numpy as np
import pytest

from tools.pipeline_eval.qualification import frame_coherence_eval as study
from tools.pipeline_eval.qualification import frame_coherence_results as results
from tools.pipeline_eval.variants import frame_coherence as fc


def test_correlation_recovers_both_parts_of_wrapped_lag():
    rng = np.random.default_rng(59)
    template = rng.normal(size=fc.FRAME)
    observed = np.roll(template, -7) + 1j * np.roll(template, 10)
    actual = fc.circular_prompt(
        np.fft.fft(observed, n=fc.FFT), np.fft.fft(template, n=fc.FFT).conj()
    )
    assert np.argmax(actual.real) == fc.FRAME - 7
    assert np.argmax(actual.imag) == 10
    for lag in (0, 1, 10, 7012, fc.FRAME - 7, fc.FRAME - 1):
        expected = np.sum(np.roll(observed, -lag) * template)
        assert actual[lag] == pytest.approx(expected, abs=1e-9)


def test_ranked_centers_use_circular_suppression_and_stable_ties():
    surface = np.zeros(fc.FRAME)
    surface[[0, 5, 11, fc.FRAME - 3]] = [10, 10, 9, 9.5]
    assert fc.ranked_centers(surface, 2) == [0, 5]
    assert fc.ranked_centers(surface) == [0, 5, 11]
    assert not fc.ranked_centers(np.zeros(fc.FRAME))


@pytest.mark.parametrize("edge", ("lower", "upper"))
def test_signed_plants_rank_both_receivers_at_the_registered_epoch(edge):
    iq, plant = study.synthetic(edge, "strong")
    assert fc.scout(iq, edge)[0][0][0] == plant["epoch"]
    assert fc.scout(iq, edge)[1][0][0] == plant["epoch"]


def test_exact_pair_offsets_and_distinct_edge_templates():
    receipt = study.template_receipt()
    starts = receipt["first_frame_pair_starts"]
    assert len(starts) == 12
    assert fc.LAG + starts[-1] + fc.FRAME <= fc.SAMPLES
    assert round(12 * fc.LAG / 3) + fc.LAG + fc.FRAME > fc.SAMPLES
    assert set(receipt["exact_three_frame_start_differences"]) == {fc.LAG}
    rows = receipt["rows"]
    assert rows["lower"]["indices"] == tuple(range(528, 536))
    assert rows["upper"]["indices"] == tuple(range(488, 496))
    assert rows["lower"]["template_sha256"] != rows["upper"]["template_sha256"]


def test_fractional_wrap_is_scored_with_distinct_actual_budgets():
    summary = results.timing_hits(
        fc.FRAME - 0.45,
        dict(ordinary=[0, 1300, 1400, 1500], raw=[100, 200, 300, 400, 3]),
    )
    assert summary["ordinary_4_2"]
    assert "ordinary_16_2" not in summary
    assert not summary["raw_4_20"]
    assert not summary["raw_16_2"]
    assert summary["raw_16_20"]
