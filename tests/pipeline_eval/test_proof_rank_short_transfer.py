from contextlib import nullcontext
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def short(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    import proof_rank_short_transfer

    return proof_rank_short_transfer


def test_fallback_charges_both_rank_attempts_and_one_proof(short):
    def stage(cpu, elapsed):
        return dict(cpu_s=cpu, elapsed_s=elapsed)

    timing = dict(original=dict(scan_setup=stage(.2, .3), rank=stage(2., 3.)),
                  reduced=dict(scan_setup=stage(.1, .2), rank=stage(1., 2.)))
    proof, selection = stage(1., 2.), stage(.3, .4)
    paid = short.costs(timing, proof, selection, "insufficient_finite_finalists")
    assert paid["original"] == pytest.approx(stage(3.2, 5.3))
    assert paid["attempted_reduced"] == pytest.approx(stage(2.4, 4.6))
    assert paid["guard_charged"] == pytest.approx(stage(4.6, 7.9))
    unrun = short.costs({"original": timing["original"]}, proof, selection, "unusable_proof_pool")
    assert unrun["guard_charged"] == pytest.approx(stage(3.5, 5.7))


@pytest.mark.parametrize("finalists,change,warning,guard", [
    (2, False, False, "insufficient_finite_finalists"),
    (3, True, True, None),
    (3, False, False, None),
])
def test_rank_transfer_distinguishes_scientific_equality_from_runtime_guard(short, monkeypatch, finalists, change, warning, guard):
    from leo.analysis.localization_v3 import discovery
    from tools.pipeline_eval.variants import v5_core
    import proof_global_rank

    labels = np.arange(1, 13)
    prepared = dict(sky=dict(bank=dict(norad=labels)), noise={})
    visits = [dict(owners={str(i): i for i in range(1, 9)})]

    def rank(scan):
        reduced = len(scan["sky"]["bank"]["norad"]) != len(labels)
        candidate = 2 if reduced and change else 1
        return [(float(i + 1), [("track", 0, candidate, i)]) for i in range(finalists)]

    monkeypatch.setattr(discovery, "signature", lambda candidate: candidate)
    monkeypatch.setattr(v5_core, "scan_context", lambda scan, *_: scan)
    monkeypatch.setattr(v5_core, "ranked_initial_nodes", rank)
    monkeypatch.setattr(proof_global_rank, "ranked_scores", nullcontext)
    observed = short.ranked_transfer(prepared, None, None, visits, dict(cpu_s=0., elapsed_s=0.),
                                     lambda _: nullcontext({}), first="reduced")
    assert observed["activated"] and observed["pool_in_order"] == list(range(1, 9))
    assert (observed["ranks"]["original"] == observed["ranks"]["reduced"]) is not change
    assert observed["fallback"] == guard
    assert observed["changed_without_deployable_warning"] is warning
    assert observed["passes_rank_transfer"] is (finalists == 3 and not change)


def test_sealed_far_withholds_before_cold_rank_on_the_same_short_input(short):
    result = short.saved_far()
    assert result["rank_invocations"] == 0 and result["route"] == "withheld_early"
    assert result["proof"]["result"]["exterior_separation_km"] == 0
    assert result["proof"]["result"]["probes_evaluated"] == 96
    assert result["projector"] == "released dense geographic projector"
