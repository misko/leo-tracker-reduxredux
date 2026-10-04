"""History descendants retain the sparse, variable-dwell V8 semantics."""

import pytest

from leo.scanner.adaptive_hop_history import (
    FourRateVariableDwellHistoryItemV9,
    FourRateVariableDwellSessionDetailV9,
    NativeLowRateHistoryItemV10,
    NativeLowRateSessionDetailV10,
    VariableDwellHistoryItemV8,
    VariableDwellSessionDetailV8,
)
from tests.storage.test_adaptive_hop_history import _variable_dwell_summary

CASES = [
    (VariableDwellHistoryItemV8, VariableDwellSessionDetailV8, 8, 2_500_000),
    (FourRateVariableDwellHistoryItemV9, FourRateVariableDwellSessionDetailV9, 9, 5_000_000),
    (NativeLowRateHistoryItemV10, NativeLowRateSessionDetailV10, 10, 1_250_000),
]


@pytest.mark.parametrize("item_type,detail_type,version,rate", CASES)
@pytest.mark.parametrize("duration_ms", [120, 360])
def test_sparse_completed_history_and_detail_preserve_counts(
    item_type, detail_type, version, rate, duration_ms
):
    payload = _variable_dwell_summary().model_dump()
    payload.update(
        schema_version=version,
        sample_rate_hz=rate,
        bandwidth_hz=rate,
        terminal_state="completed",
        capture_qualified=False,
    )
    payload["target_coverage"][0]["valid_seconds"] = duration_ms / 1000
    capture = item_type.model_validate(payload)
    visits = []
    start = 0
    for index in range(3):
        retained = index != 1
        duration = duration_ms if index == 0 else 120
        end = start + rate * duration // 1000
        visits.append(
            dict(
                visit_index=index,
                target_index=index,
                retained=retained,
                invalid_start_seconds=start / rate,
                valid_start_seconds=start / rate,
                valid_end_seconds=end / rate if retained else None,
                valid_start_counter=start,
                valid_end_counter=end if retained else None,
                decision_counter=start,
                basis_visit=None,
                proposed_target_index=index,
                reason="warmup",
                active_mask=0,
                quiet_mask=0,
                consecutive_misses=0,
                cooldown_remaining_seconds=0,
            )
        )
        start = end
    detail = detail_type(capture=capture, source_origin_counter=0, visits=visits)
    assert detail.capture.started_visits == 3
    assert detail.capture.retained_visits == 2
    assert not detail.capture.capture_qualified
    assert [v.retained for v in detail.visits] == [True, False, True]
    assert detail_type.model_validate_json(detail.model_dump_json()) == detail
    invalid = detail.model_dump()
    invalid["visits"][1]["retained"] = True
    with pytest.raises(ValueError):
        detail_type.model_validate(invalid)
    invalid = capture.model_dump()
    invalid["target_coverage"][0]["valid_seconds"] = 0.24
    with pytest.raises(ValueError, match="coverage disagrees"):
        item_type.model_validate(invalid)
    invalid = capture.model_dump()
    invalid["retained_visits"] = 4
    with pytest.raises(ValueError, match="summary disagrees"):
        item_type.model_validate(invalid)
