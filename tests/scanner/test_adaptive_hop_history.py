"""Pure adaptive read-model boundaries; no storage, hardware or IQ dependencies."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from leo.scanner.adaptive_hop_history import (
    AdaptiveHopHistoryItemV1,
    AdaptiveHopHistoryPageV1,
    AdaptiveHopSessionDetailV1,
    AdaptiveHopVisitViewV1,
)
from leo.scanner.persistent_hop import compile_persistent_hop_plan_v1


def detail_fixture():
    origin = 2**53 + 17
    geometry = compile_persistent_hop_plan_v1(sample_rate_hz=2_500_000)
    capture = AdaptiveHopHistoryItemV1(
        session_id="read-model",
        input_manifest_sha256="sha256:" + "a" * 64,
        radio_id="synthetic",
        mode="shadow",
        policy_generation=71,
        recorded_at=datetime(2026, 9, 9, tzinfo=UTC),
        finalized_at=datetime(2026, 9, 9, tzinfo=UTC),
        captured_at=None,
        utc_qualified=False,
        utc_bracket_width_ms=None,
        sample_rate_hz=2_500_000,
        bandwidth_hz=2_500_000,
        started_visits=1,
        retained_visits=0,
        source_span_attested=True,
        source_span_seconds=0.01,
        valid_duty_ppm=0,
        capture_qualified=False,
        terminal_state="cancelled",
        fallback_choices=0,
        target_coverage=tuple(
            dict(
                target_index=i,
                target=p.target,
                retained_visits=0,
                valid_seconds=0,
                allocation_ppm=None,
                maximum_revisit_seconds=None,
                maximum_unobserved_seconds=0.01,
            )
            for i, p in enumerate(geometry.profiles)
        ),
    )
    visit = AdaptiveHopVisitViewV1(
        visit_index=0,
        target_index=0,
        retained=False,
        invalid_start_seconds=0,
        valid_start_seconds=0.04,
        valid_end_seconds=None,
        valid_start_counter=origin + 100000,
        valid_end_counter=None,
        decision_counter=origin,
        basis_visit=None,
        proposed_target_index=3,
        reason="warmup",
        active_mask=0,
        quiet_mask=0,
        consecutive_misses=0,
        cooldown_remaining_seconds=0,
    )
    return AdaptiveHopSessionDetailV1(
        capture=capture, source_origin_counter=origin, visits=(visit,)
    )


def test_exact_json_roundtrip_and_cancel_before_valid_boundary():
    detail = detail_fixture()
    assert AdaptiveHopSessionDetailV1.model_validate_json(detail.model_dump_json()) == detail
    assert detail.visits[0].valid_start_seconds > detail.capture.source_span_seconds
    assert detail.model_dump(mode="json")["source_origin_counter"] == str(2**53 + 17)


@pytest.mark.parametrize(
    "fault",
    [
        "origin",
        "valid_time",
        "inventory",
        "active_masks",
        "actual_target",
        "retained_end",
        "future_basis",
        "fractional_counter",
    ],
)
def test_read_model_rejects_invented_or_inconsistent_evidence(fault):
    value = detail_fixture().model_dump()
    row = value["visits"][0]
    if fault == "origin":
        value["source_origin_counter"] += 1
    if fault == "valid_time":
        row["valid_start_seconds"] = 0
    if fault == "inventory":
        value["visits"] = ()
    if fault == "active_masks":
        row.update(active_mask=1, quiet_mask=1)
    if fault == "actual_target":
        row["target_index"] = 3
    if fault == "retained_end":
        row["valid_end_counter"] = row["valid_start_counter"] + 300000
    if fault == "future_basis":
        row["basis_visit"] = 0
    if fault == "fractional_counter":
        row["valid_start_counter"] = float(row["valid_start_counter"])
    with pytest.raises(ValidationError):
        AdaptiveHopSessionDetailV1.model_validate(value)


@pytest.mark.parametrize(
    "fault",
    [
        "fake_duty",
        "zero_generation",
        "fake_revisit",
        "fake_allocation",
        "fake_capture_qualification",
        "wrong_edge",
        "fake_span",
    ],
)
def test_summary_does_not_invent_measurements(fault):
    value = detail_fixture().capture.model_dump()
    if fault == "fake_duty":
        value["valid_duty_ppm"] = None
    if fault == "zero_generation":
        value["policy_generation"] = 0
    if fault == "fake_revisit":
        value["target_coverage"][0]["maximum_revisit_seconds"] = 0
    if fault == "fake_allocation":
        value["target_coverage"][0]["allocation_ppm"] = 0
    if fault == "fake_capture_qualification":
        value["capture_qualified"] = True
    if fault == "wrong_edge":
        value["target_coverage"][0]["target"]["edge"] = "upper"
    if fault == "fake_span":
        value["source_span_attested"] = False
    with pytest.raises(ValidationError):
        AdaptiveHopHistoryItemV1.model_validate(value)


def test_page_requires_bounded_complete_inventory_and_next_cursor():
    item = detail_fixture().capture
    page = AdaptiveHopHistoryPageV1(cursor=0, limit=1, total=2, next_cursor=1, items=(item,))
    for update in ({"next_cursor": None}, {"items": ()}, {"cursor": True}, {"limit": 21}):
        with pytest.raises(ValidationError):
            AdaptiveHopHistoryPageV1.model_validate({**page.model_dump(), **update})
