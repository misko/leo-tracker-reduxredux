from __future__ import annotations

import json
import sys
from dataclasses import dataclass, replace
from enum import IntEnum
from types import SimpleNamespace

import numpy as np
import pytest

from leo.acquisition.continuous_window_ppu import PpuContinuousWindowSource
from leo.scanner.short_window import classify_window
from tests.scanner.test_continuous_recording import configuration


def test_injected_radio_factory_reaches_preparation_without_changing_window_validation(monkeypatch):
    factory = object()
    calls = []
    samples = np.zeros((50000, 2, 2), dtype="<i2")
    owner = SimpleNamespace(visits=lambda: iter([
        SimpleNamespace(record=Record(), iq=samples.tobytes())]))

    def start(uri, serial, setup, **kwargs):
        calls.append((uri, serial, setup, kwargs))
        return owner

    monkeypatch.setitem(sys.modules, "pluto_plus.continuous_scan", SimpleNamespace(
        build_continuous_setup=lambda **kwargs: kwargs))
    monkeypatch.setitem(sys.modules, "pluto_plus.continuous_scan_radio", SimpleNamespace(
        ContinuousRadioOwner=SimpleNamespace(start=start)))
    provider = PpuContinuousWindowSource(
        "192.168.1.20", expected_serial="serial", radio_factory=factory)
    provider.configure_once(configuration())
    assert calls[0][0:2] == ("ip:192.168.1.20", "serial")
    assert calls[0][3]["radio_factory"] is factory
    assert provider.next_window().acquisition.sample_count == 50000
    with pytest.raises(RuntimeError, match="only be prepared once"):
        provider.configure_once(configuration())


def test_utc_anchor_brackets_first_valid_sample_and_preserves_caller_hook(monkeypatch):
    calls = []
    samples = np.zeros((50000, 2, 2), dtype="<i2")
    owner = SimpleNamespace(visits=lambda: iter([
        SimpleNamespace(record=Record(), iq=samples.tobytes()),
        SimpleNamespace(record=replace(Record(), visit=1, target=1), iq=samples.tobytes())]))
    def start(uri, serial, setup, **kwargs):
        kwargs["before_start_hook"]("prepared")
        return owner
    monkeypatch.setitem(sys.modules, "pluto_plus.continuous_scan", SimpleNamespace(
        build_continuous_setup=lambda **kwargs: kwargs))
    monkeypatch.setitem(sys.modules, "pluto_plus.continuous_scan_radio", SimpleNamespace(
        ContinuousRadioOwner=SimpleNamespace(start=start)))
    provider = PpuContinuousWindowSource("fixture", expected_serial="serial",
                                         before_start_hook=calls.append)
    provider.configure_once(configuration())
    first = json.loads(provider.next_window().acquisition.retune_receipt)
    second = json.loads(provider.next_window().acquisition.retune_receipt)
    assert calls == ["prepared"]
    bracket = first["utc_clock_bracket"]
    assert bracket["sample_counter"] == Record().valid_start
    assert bracket["before"]["monotonic_ns"] <= bracket["after"]["monotonic_ns"]
    assert bracket["after"] == first["host_delivery_clock"]
    assert "utc_clock_bracket" not in second
    assert second["host_delivery_clock"]["monotonic_ns"] >= bracket["after"]["monotonic_ns"]


class Result(IntEnum):
    COMPLETE = 1
    CANCELLED = 5


@dataclass
class Record:
    session: int = 3
    generation: int = 4
    visit: int = 0
    target: int = 0
    profile: int = 0
    frequency_hz: int = 1_800_000_000
    valid_start: int = (1 << 32) - 25000
    valid_end: int = (1 << 32) + 25000
    missing_samples_before: int = 0
    transition_before: int = (1 << 32) - 80000
    transition_after: int = (1 << 32) - 75000
    result: Result = Result.COMPLETE


def source(samples, record=None):
    record = Record() if record is None else record
    config = configuration()
    result = PpuContinuousWindowSource("fixture", expected_serial="serial")
    result.configuration = config
    result._visits = iter([SimpleNamespace(record=record, iq=samples.tobytes())])
    return result, config


def test_adc12_rails_and_invalid_format_never_claim_activity():
    samples = np.full((50000, 2, 2), 2047, dtype="<i2")
    provider, config = source(samples)
    window = provider.next_window()
    assert window.acquisition.complete
    assert "adc12_clipping" in window.acquisition.quality_flags
    assert all(
        power.decision == "unknown"
        for power in classify_window(window.acquisition, config.power_configuration())
    )
    receipt = json.loads(window.acquisition.retune_receipt)
    assert receipt["adc12_clipping_components"] == [100000, 100000]
    assert receipt["adc12_out_of_range_components"] == [0, 0]
    assert receipt["guard_policy_id"] == "minimum-post-recall-v1"
    assert receipt["minimum_post_recall_guard_samples"] == 50000
    assert receipt["observed_post_recall_guard_samples"] == 50000
    assert receipt["post_recall_guard_satisfied"] is True
    provider, _ = source(np.full((50000, 2, 2), 5000, dtype="<i2"))
    assert "adc12_format_unqualified" in provider.next_window().acquisition.quality_flags


def test_real_partial_iq_preserved_and_rf_authority_stays_unknown():
    samples = np.zeros((20000, 2, 2), dtype="<i2")
    record = replace(Record(), valid_end=Record().valid_start + 20000, result=Result.CANCELLED)
    provider, config = source(samples, record)
    window = provider.next_window()
    assert window.acquisition.sample_count == 20000
    assert window.acquisition.sample_end == record.valid_end
    assert window.acquisition.validity_authority == "unknown"
    assert window.target.rf_mapping_authority == "unknown"
    assert window.target.band is window.target.polarization is window.target.rf_center_hz is None
    assert all(
        power.decision == "unknown"
        for power in classify_window(window.acquisition, config.power_configuration())
    )
    with pytest.raises(ValueError, match="generation changed"):
        replace(window, acquisition=replace(window.acquisition, generation=5))


@pytest.mark.parametrize("guard", [-1, 0, 1, 49999])
def test_complete_window_rejects_insufficient_post_recall_guard(guard):
    record = replace(Record(), transition_after=Record().valid_start - guard)
    provider, _ = source(np.zeros((50000, 2, 2), dtype="<i2"), record)
    with pytest.raises(ValueError, match="minimum post-recall guard"):
        provider.next_window()


def test_post_recall_guard_uses_configured_duration():
    provider, _ = source(np.zeros((50000, 2, 2), dtype="<i2"))
    provider.configuration = replace(provider.configuration, transition_budget_ms=21)
    with pytest.raises(ValueError, match="50000 < 52500"):
        provider.next_window()


def test_partial_unguarded_window_remains_diagnostic():
    record = replace(Record(), valid_end=Record().valid_start + 20000,
                     transition_after=Record().valid_start, result=Result.CANCELLED)
    provider, config = source(np.zeros((20000, 2, 2), dtype="<i2"), record)
    window = provider.next_window()
    receipt = json.loads(window.acquisition.retune_receipt)
    assert receipt["post_recall_guard_satisfied"] is False
    assert window.acquisition.validity_authority == "unknown"
    assert all(power.decision == "unknown" for power in
               classify_window(window.acquisition, config.power_configuration()))
