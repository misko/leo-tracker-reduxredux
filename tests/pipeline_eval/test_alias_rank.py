import numpy as np
import pytest

from tools.pipeline_eval.qualification import differential_pilot_eval as examples
from tools.pipeline_eval.variants import alias_rank, folded_cfo


@pytest.mark.parametrize("edge", ("lower", "upper"))
@pytest.mark.parametrize("condition", ("strong", "one-frame"))
def test_coherent_alias_uses_one_live_frame_and_signed_cfo(edge, condition):
    iq, truth = examples.synthetic(edge, condition)
    candidates = folded_cfo.score_and_phase(iq, edge)
    for lane, (ranks, _, phase) in enumerate(candidates):
        assert ranks[0] == truth["epoch"]
        observed = alias_rank.assess(iq, lane, edge, ranks[0], phase)
        assert observed["confirmed"]
        assert observed["options"][0]["cfo_hz"] == pytest.approx(truth["cfo_hz"], abs=12_000)
        mask = alias_rank.restrict(observed)
        coarse = round(truth["cfo_hz"] / 80_000) + 10
        assert mask & (1 << coarse)


def test_unobservable_input_yields_no_mask_even_in_forced_mode():
    iq = np.zeros((alias_rank.dp.SAMPLES, 2, 2), dtype="<i2")
    assert alias_rank.assess(iq, 0, "upper", 735, 25.5) is None
    assert alias_rank.restrict(None, require_evidence=False) is None


@pytest.mark.parametrize("base", (-alias_rank.PERIOD / 2, 0.0, alias_rank.PERIOD / 2))
def test_all_physical_boundaries_remain_available_on_the_alias_grid(base):
    centers, grid = alias_rank.frequency_grid(base)
    assert np.diff(centers) == pytest.approx([alias_rank.PERIOD] * (len(centers) - 1))
    assert np.max(np.abs(grid)) <= alias_rank.LIMIT
    assert all(np.min(abs(g - center)) <= 36_000 for center, g in zip(centers, grid, strict=True))
