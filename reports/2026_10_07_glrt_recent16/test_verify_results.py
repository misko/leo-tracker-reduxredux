"""The artifact audit must reject changed hypotheses and omitted candidates."""

import copy

import numpy as np
import pytest
from evaluator import evaluate_bank
from verify_results import check_choice


def saved_case():
    rng = np.random.default_rng(99)
    pairs = [
        (
            rng.normal(size=(3, 64)) + 1j * rng.normal(size=(3, 64)),
            rng.normal(size=(3, 64)) + 1j * rng.normal(size=(3, 64)),
        )
        for _ in range(2)
    ]
    bank = [
        dict(candidate_id=i, candidate_rank=i, epoch_sample=10 * i, seed_cfo_hz=1000.0 * i)
        for i in range(2)
    ]
    result = evaluate_bank(
        bank, pairs, pairs, exact_template_energy=np.ones(64), control_template_energy=np.ones(64)
    )
    return dict(
        candidate_bank=bank,
        saved_candidate_count=3,
        available_candidate_count=2,
        unavailable_candidates=[dict(candidate_rank=2)],
        status="complete",
        evaluation=result,
    )


@pytest.mark.parametrize("mutation", ["seed", "later_cfo", "bank_omission", "margin"])
def test_detect_hypothesis_or_accounting_tampering(mutation):
    case = saved_case()
    assert check_choice(case) == 17
    changed = copy.deepcopy(case)
    if mutation == "seed":
        changed["candidate_bank"][0]["seed_cfo_hz"] += 1
    elif mutation == "later_cfo":
        changed["evaluation"]["methods"]["phase_kernel32"]["own_fixed_confirmation"][
            "total_cfo_hz"
        ] += 1
    elif mutation == "bank_omission":
        changed["unavailable_candidates"] = []
    else:
        changed["evaluation"]["methods"]["phase_kernel32"]["common_confirmation"]["gaussian"][
            "margin_difference"
        ] += 0.01
    with pytest.raises(AssertionError):
        check_choice(changed)
