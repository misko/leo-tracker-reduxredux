"""Durable scheduled-result routing; source metadata is synthetic, no RF/IQ."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from leo.cli.backend import ScheduledAdaptiveHopRun
from leo.cli.runner import ContinuousAcquisitionRunner
from leo.scanner.adaptive_hop import AdaptiveHopPlanV1, AdaptiveHopPolicyV1
from leo.scanner.persistent_hop import compile_persistent_hop_plan_v1
from tests.cli.test_capture_supervisor import _AdvancingCancel, _Clock, _DurableSupervisorBackend
from tests.scanner.adaptive_hop_fixtures import receipt_fixture


@pytest.mark.parametrize("outcome", ["completed", "low_duty", "cancelled", "empty"])
def test_durable_slot_uses_adaptive_capture_health_not_detector_success(outcome, caplog):
    clock = _Clock()
    backend = _DurableSupervisorBackend(clock)
    start = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)
    plan = AdaptiveHopPlanV1(
        geometry=compile_persistent_hop_plan_v1(
            sample_rate_hz=2_500_000,
            transition_guard_us=1_000,
        ),
        policy=AdaptiveHopPolicyV1(mode="shadow", generation=7),
    )
    receipt = receipt_fixture(
        plan=plan,
        complete=outcome in ("completed", "low_duty"),
        count=0 if outcome == "empty" else 3,
        transition_samples=50_000 if outcome == "low_duty" else 20,
    )

    def capture(intent, *, cancel):
        backend.scanner_capture_times.append(clock())
        return ScheduledAdaptiveHopRun(
            intent=intent,
            published=SimpleNamespace(
                session_id=receipt.session_id, manifest=SimpleNamespace(receipt=receipt)
            ),
            classification_warning="injected detector reporting failure",
        )

    backend.capture_scheduled_scanner = capture
    summary = ContinuousAcquisitionRunner(
        backend,
        clock=clock,
        utc_now=lambda: start + timedelta(seconds=clock.now),
    ).run(
        "test-profile",
        radio_ids=("radio-a",),
        extra_tags=(),
        interval_seconds=10.0,
        maximum_captures=None,
        cancel=_AdvancingCancel(clock),
        scanner_only=True,
        maximum_scanner_runs=1,
    )
    scanner = next(item for item in backend.operations if item.kind == "scanner_sweep")
    assert scanner.state == ("succeeded" if outcome == "completed" else "failed")
    assert not backend.analyzed.is_set()
    if outcome != "completed":
        assert summary.stopped_reason == "error"
        assert scanner.retryable is False
    else:
        assert "adaptive scan" in scanner.outcome
    if outcome == "empty":
        assert "duty_ppm=unavailable" in summary.error
