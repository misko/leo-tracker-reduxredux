from __future__ import annotations

import json
from dataclasses import dataclass, replace
from enum import IntEnum
from types import SimpleNamespace

import numpy as np
import pytest

from leo.acquisition import short_window_ppu as module
from leo.scanner.short_window import (
    CounterAuthority,
    ShortWindowConfiguration,
    ShortWindowTarget,
    ValidityAuthority,
    classify_window,
)


class Result(IntEnum):
    COMPLETE = 1
    INVALID_GAP = 4


@dataclass
class Record:
    target: int = 1
    profile: int = 1
    generation: int = 4
    frequency_hz: int = 1_810_000_000
    valid_start: int = 80_000
    valid_end: int = 130_000
    transition_before: int = 0
    transition_after: int = 30_000
    missing_samples_before: int = 0
    result: Result = Result.COMPLETE


def config() -> ShortWindowConfiguration:
    return ShortWindowConfiguration(
        targets=(ShortWindowTarget("a", 1_800_000_000), ShortWindowTarget("b", 1_810_000_000)),
        duration_seconds=1,
        policy_id="firmware-weighted-20ms-v1",
    )


def visit(record: Record | None = None, count: int = 50_000) -> SimpleNamespace:
    return SimpleNamespace(
        record=record or Record(),
        iq=np.full((count, 2, 2), 1000, dtype="<i2").tobytes(),
    )


def test_actual_firmware_order_and_counter_guard_are_preserved(monkeypatch) -> None:
    def campaign(source, configuration):
        source._on_session(SimpleNamespace(close=lambda: None))
        source._on_visit(visit())
        source._on_visit(visit(replace(Record(), target=0, frequency_hz=1_800_000_000)))
        return "restored"

    monkeypatch.setattr(module, "_run_ppu_campaign", campaign)
    source = module.PpuShortWindowSource("192.168.1.15", expected_serial="serial")
    source.configure_once(config())
    first, acquisition = source.next_capture()
    second, _ = source.next_capture()
    assert (first.target_id, second.target_id) == ("b", "a")
    assert acquisition.sample_start == 80_000
    assert acquisition.sample_end == 130_000
    assert acquisition.counter_authority is CounterAuthority.HARDWARE
    assert acquisition.validity_authority is ValidityAuthority.PROVIDER_ATTESTED
    assert acquisition.validity_includes_guard
    assert acquisition.guard_ms == 0
    assert acquisition.discarded_samples == 80_000
    assert acquisition.sample_start_utc_ns is None
    assert all(p.decision == "active" for p in classify_window(acquisition, config()))
    with pytest.raises(StopIteration):
        source.next_capture()
    source.close()
    assert source.receipt == "restored"


def test_invalid_empty_visit_is_retained_as_unknown(monkeypatch) -> None:
    def campaign(source, configuration):
        source._on_session(SimpleNamespace(close=lambda: None))
        source._on_visit(visit(replace(Record(), result=Result.INVALID_GAP), count=0))

    monkeypatch.setattr(module, "_run_ppu_campaign", campaign)
    source = module.PpuShortWindowSource("192.168.1.15", expected_serial="serial")
    source.configure_once(config())
    _, acquisition = source.next_capture()
    assert acquisition.sample_count == 0
    assert all(p.decision == "unknown" for p in classify_window(acquisition, config()))
    with pytest.raises(StopIteration):
        source.next_capture()
    source.close()


def test_overflow_retains_admitted_window_then_reports_failure(monkeypatch) -> None:
    def campaign(source, configuration):
        source._on_session(SimpleNamespace(close=lambda: None))
        source._on_visit(visit())
        source._on_visit(visit())

    monkeypatch.setattr(module, "_run_ppu_campaign", campaign)
    source = module.PpuShortWindowSource(
        "192.168.1.15",
        expected_serial="serial",
        queue_windows=1,
    )
    source.configure_once(config())
    assert source._done.wait(1)
    source.next_capture()
    with pytest.raises(RuntimeError, match="capture or restoration"):
        source.next_capture()
    with pytest.raises(RuntimeError, match="capture or restoration"):
        source.close()


def test_preparation_failure_surfaces_without_hanging(monkeypatch) -> None:
    def campaign(source, configuration):
        raise RuntimeError("serial mismatch")

    monkeypatch.setattr(module, "_run_ppu_campaign", campaign)
    source = module.PpuShortWindowSource("192.168.1.15", expected_serial="serial")
    with pytest.raises(RuntimeError, match="preparation failed") as caught:
        source.configure_once(config())
    assert "serial mismatch" in str(caught.value.__cause__)


def test_cancel_never_hides_restoration_failure(monkeypatch) -> None:
    def campaign(source, configuration):
        source._on_session(SimpleNamespace(close=lambda: None))
        source._cancelled.wait(1)
        raise RuntimeError("receiver restoration failed")

    monkeypatch.setattr(module, "_run_ppu_campaign", campaign)
    source = module.PpuShortWindowSource("192.168.1.15", expected_serial="serial")
    source.configure_once(config())
    source.cancel()
    with pytest.raises(RuntimeError, match="restoration failed"):
        source.close()


def test_gap_evidence_prevents_activity_claims(monkeypatch) -> None:
    def campaign(source, configuration):
        source._on_session(SimpleNamespace(close=lambda: None))
        source._on_visit(visit(replace(Record(), missing_samples_before=8)))

    monkeypatch.setattr(module, "_run_ppu_campaign", campaign)
    source = module.PpuShortWindowSource("192.168.1.15", expected_serial="serial")
    source.configure_once(config())
    _, acquisition = source.next_capture()
    assert "provider_missing_samples" in acquisition.quality_flags
    assert all(p.decision == "unknown" for p in classify_window(acquisition, config()))
    assert source._done.wait(1)
    source.close()


def test_adc12_saturation_is_not_missed_by_ci16_container_rails(monkeypatch) -> None:
    def campaign(source, configuration):
        source._on_session(SimpleNamespace(close=lambda: None))
        values = np.full((50_000, 2, 2), 1000, dtype="<i2")
        values[0, 1, 0] = 2047
        source._on_visit(SimpleNamespace(record=Record(), iq=values.tobytes()))

    monkeypatch.setattr(module, "_run_ppu_campaign", campaign)
    source = module.PpuShortWindowSource("192.168.1.15", expected_serial="serial")
    source.configure_once(config())
    _, acquisition = source.next_capture()
    assert "adc12_clipping" in acquisition.quality_flags
    assert json.loads(acquisition.retune_receipt)["adc12_clipping_components"] == [0, 1]
    assert all(p.decision == "unknown" for p in classify_window(acquisition, config()))
    assert source._done.wait(1)
    source.close()


def test_repeated_profile_is_marked_as_skipped_recall(monkeypatch) -> None:
    def campaign(source, configuration):
        source._on_session(SimpleNamespace(close=lambda: None))
        source._on_visit(visit())
        source._on_visit(
            visit(
                replace(
                    Record(),
                    transition_before=130_000,
                    transition_after=130_000,
                    valid_start=130_000,
                    valid_end=180_000,
                )
            )
        )

    monkeypatch.setattr(module, "_run_ppu_campaign", campaign)
    source = module.PpuShortWindowSource("192.168.1.15", expected_serial="serial")
    source.configure_once(config())
    _, first = source.next_capture()
    _, second = source.next_capture()
    assert not first.recall_skipped
    assert second.recall_skipped
    assert second.contiguous_with_previous
    assert source._done.wait(1)
    source.close()


@pytest.mark.parametrize(
    "changes",
    [{"policy_id": "fixed-round-robin-20ms-v1"}, {"duration_seconds": 301}],
)
def test_rejects_inaccurate_policy_or_unbounded_campaign(changes) -> None:
    source = module.PpuShortWindowSource("192.168.1.15", expected_serial="serial")
    with pytest.raises(ValueError):
        source.configure_once(replace(config(), **changes))


@pytest.mark.parametrize(
    "changes",
    [{"error": -5}, {"skipped": 1}, {"invalid": 1}, {"cancelled": 1}],
)
def test_terminal_integrity_failure_cannot_publish_success(changes) -> None:
    values = dict(
        state=SimpleNamespace(name="COMPLETED"),
        error=0,
        skipped=0,
        invalid=0,
        cancelled=0,
    )
    values.update(changes)
    with pytest.raises(RuntimeError, match="incomplete hardware accounting"):
        module._validate_terminal(SimpleNamespace(**values))
