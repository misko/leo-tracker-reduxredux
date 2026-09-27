"""Cost and coverage accounting must not turn missing work into successful hits."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import replay  # noqa: E402


def row(cost, baseline, *, processed=True, blind=False):
    return {
        'baseline_times': [{'cpu_ms': baseline, 'wall_ms': baseline}] * 3,
        'candidate_times': [{'cpu_ms': cost, 'wall_ms': cost}] * 3,
        'rate_hz': 2500000, 'reason': 'cache_hit' if processed else 'unprocessed_outage',
        'used_blind': blind, 'attempted_cache': processed and not blind,
        'processed': processed, 'reference_positive': True,
        'matched_reference': processed, 'candidate_positive': processed,
        'observation': object() if processed else None,
    }


def test_ratio_of_summed_costs_and_outage_is_unknown_not_a_cache_hit():
    result = replay.summarize([row(1, 2), row(2, 10), row(.01, 5, processed=False)])
    assert result['all_visits']['cpu_speedup'] == pytest.approx(17 / 3.01)
    assert result['all_visits']['unprocessed_cases'] == 1
    assert result['all_visits']['lost_reference_positives'] == 0
    assert result['all_visits']['unprocessed_reference_positives'] == 1
    assert not result['all_visits']['full_coverage_speedup_eligible']
    assert result['processed_only']['cpu_speedup'] == 4
    assert result['accepted_cache_only']['receiver_visits'] == 2


def test_repeated_dsp_measurement_does_not_hide_nondeterminism():
    values = iter([(1, {}), (2, {})])
    with pytest.raises(ValueError, match='changed'):
        replay.timed(lambda: next(values), 3)
