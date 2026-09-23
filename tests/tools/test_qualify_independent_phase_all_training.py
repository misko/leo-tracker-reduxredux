import numpy as np

from tools.research.qualify_independent_phase_all_training import (
    FOLD_PERIOD_HZ,
    even_summary,
    modulo_difference,
    signed_fold_remainder,
)


def frame(group, cfo, *, supported=True, boundary=False, margin=0.2):
    return {
        "group_id": group,
        "frame": {
            "training_supported": supported,
            "even": {
                "absolute_cfo_hz": cfo,
                "search_boundary": boundary,
                "coherence_margin": margin,
            },
        },
    }


def test_modulo_difference_identifies_fold_period_without_branch_selection():
    reference = even_summary([frame(0, 50.0), frame(3, 60.0), frame(5, 70.0)])
    shifted = even_summary(
        [
            frame(0, 50.0 + FOLD_PERIOD_HZ),
            frame(3, 60.0 + FOLD_PERIOD_HZ),
            frame(5, 70.0 + FOLD_PERIOD_HZ),
        ]
    )
    result = modulo_difference(shifted, reference)
    assert result["comparable"]
    assert result["maximum_absolute_modulo_difference_hz"] == 0.0
    assert np.allclose(signed_fold_remainder([FOLD_PERIOD_HZ, -FOLD_PERIOD_HZ]), 0.0)


def test_support_population_difference_is_reported_not_dropped():
    reference = even_summary([frame(0, 50.0), frame(3, 60.0), frame(5, 70.0)])
    changed = even_summary([frame(0, 50.0), frame(3, 60.0, supported=False), frame(5, 70.0)])
    assert modulo_difference(changed, reference) == {
        "comparable": False,
        "reason": "different_usable_even_support_mask",
    }
