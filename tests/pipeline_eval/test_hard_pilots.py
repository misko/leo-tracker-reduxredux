import numpy as np

from tools.pipeline_eval.qualification import hard_pilots_eval as audit
from tools.pipeline_eval.variants.hard_pilots import RepresentativeTime, representative_peaks


def target(epoch, cfo, *, passing=True, rank=0):
    return {
        "integer_epoch_sample": epoch,
        "fractional_epoch_offset_samples": 0.0,
        audit.CFO: cfo,
        audit.GATE: passing,
        "candidate_rank": rank,
        "fractional_margin": 0.05 if passing else 0.01,
    }


def test_physical_and_aliased_gates_share_circular_epoch_but_not_signed_frequency():
    reference = target(0, -700_000)
    folded = target(13_332, -700_000 + audit.ALIAS_HZ)
    detail = audit.classify(reference, [folded])
    assert detail["category"] == "alias_only"
    assert detail["actual_winner_alias"] and not detail["actual_winner_matches"]
    exact = target(13_332, -700_001, passing=False, rank=1)
    assert audit.classify(reference, [folded, exact])["category"] == "physical_below_gate"
    assert audit.classify(reference, [target(30, -700_001)])["category"] == "absent_phase"


def test_half_selection_compares_standardized_not_raw_peak_strength_and_ties_use_first():
    first = np.full(13_333, 3.0)
    first[400] = 12
    second = np.full_like(first, 1.0)
    second[700] = 8
    assert representative_peaks(first, second) == (700, 1)
    first[400] = 24
    assert representative_peaks(first, second) == (400, 0)
    zeros = np.zeros_like(first)
    assert representative_peaks(zeros, zeros) == (None, None)


def test_time_partition_masks_other_half_without_moving_the_samples():
    class Scout:
        def __init__(self):
            self.count = 0

        def surface(self, samples):
            mid = len(samples) // 2
            if not self.count:
                assert np.all(samples[:mid] == 5) and not np.any(samples[mid:])
            else:
                assert not np.any(samples[:mid]) and np.all(samples[mid:] == 9)
            self.count += 1
            return np.zeros((2, 13_333))

    raw = np.full((200_000, 2, 2), 5, dtype="<i2")
    raw[100_000:] = 9
    run = RepresentativeTime(Scout())
    assert run(raw) == ((None, None), (None, None))
    assert raw[0, 0, 0] == 5 and raw[-1, 1, 1] == 9
