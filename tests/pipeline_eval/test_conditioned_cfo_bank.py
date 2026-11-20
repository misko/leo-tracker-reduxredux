from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.starlink import acquisition
from tools.pipeline_eval.variants import conditioned_cfo_bank


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    path = tmp_path_factory.mktemp("conditioned-cfo") / "moments.so"
    conditioned_cfo_bank.compile_bank(path)
    return path


@pytest.mark.parametrize("epoch,edge", [(0, "upper"), (13332, "lower")])
@pytest.mark.parametrize("regular", [True, False])
def test_moment_scores_enclose_original_grid_and_repair_winner(library, epoch, edge, regular):
    rate = conditioned_cfo_bank.RATE
    rng = np.random.default_rng(427)
    iq = rng.integers(-32768, 32768, (2, 200_000))
    values = iq[0] + 1j * iq[1]
    template = acquisition.qin_edge_pilot_frame(rate, edge).astype(np.complex128)
    cfo = tuple(-48383.4512 + np.arange(41) * 100)
    if not regular:
        cfo = (*cfo[:-1], cfo[-1] - 61)
    bank = conditioned_cfo_bank.ConditionedBank(library, acquisition)
    bank.reset(audit=True)
    proposed = bank.score(values, template, rate, epoch, cfo)
    evidence = bank.receipts[-1]
    assert evidence["fallback"] is None
    assert evidence["same_winner"]
    assert evidence["max_grid_error"] < evidence["error_bound"]
    assert evidence["repaired_score_error"] < 1e-12
    assert len(proposed) == len(cfo)


def test_exact_midpoint_uses_original_oracle(library):
    rate = conditioned_cfo_bank.RATE
    template = acquisition.qin_edge_pilot_frame(rate, "lower").astype(np.complex128)
    values = np.zeros(200_000, dtype=np.complex128)
    for start in conditioned_cfo_bank.FRAME_BASE:
        values[start:start + len(template)] = template
    bank = conditioned_cfo_bank.ConditionedBank(library, acquisition)
    args = (values, template, rate, 0, (-50.0, 50.0))
    assert bank.score(*args) == bank.original(*args)
    assert bank.receipts[-1]["fallback"] == "overlapping_score_intervals"


@pytest.mark.parametrize("frequencies,rerun", [((0.0, 0.0), False), ((0.0, -0.0), True),
                                              ((0.0, 100.0), True)])
def test_rank_ties_keep_each_emitted_hypothesis(library, frequencies, rerun):
    bank = conditioned_cfo_bank.ConditionedBank(library, acquisition)
    seen = []

    def acquire():
        direct = bank._direct_only
        seen.append(direct)
        bank.receipts.append(dict(fallback="acquisition_rank_tie" if direct else None))
        candidates = tuple(SimpleNamespace(
            verify_minus_control_margin=0.02, verify_score=0.07,
            refined_epoch_sample=3, absolute_cfo_hz=f,
        ) for f in frequencies)
        return SimpleNamespace(candidates=candidates, direct=direct)

    actual = bank.guarded_acquisition(acquire)()
    assert actual.direct is rerun
    assert seen == ([False, True] if rerun else [False])
    assert bank.equivalent_ties == (0 if rerun else 1)
    assert not bank._direct_only


def test_tie_enclosure_is_strict():
    scores = np.array([0.25, 0.5])
    assert conditioned_cfo_bank.unique_winner(scores, 0.125) is None
    assert conditioned_cfo_bank.unique_winner(scores, 0.12499) == 1
