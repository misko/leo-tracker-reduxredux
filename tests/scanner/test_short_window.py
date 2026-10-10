from __future__ import annotations

import json
import math
from dataclasses import asdict, replace

import numpy as np
import pytest

from leo.scanner.short_window import (
    WINDOW_SAMPLES,
    ActivityDecision,
    CounterAuthority,
    RfMappingAuthority,
    RoundRobinScheduler,
    ShortWindowAcquisition,
    ShortWindowAssembler,
    ShortWindowConfiguration,
    ShortWindowTarget,
    ValidityAuthority,
    classify_window,
)


def configuration(target_count: int = 4, **changes: object) -> ShortWindowConfiguration:
    config = ShortWindowConfiguration(
        targets=tuple(
            ShortWindowTarget(
                target_id=f"if-{index}", if_center_hz=1_000_000_000 + index * 1_000_000
            )
            for index in range(target_count)
        )
    )
    return replace(config, **changes)


def acquisition(samples: np.ndarray, **changes: object) -> ShortWindowAcquisition:
    result = ShortWindowAcquisition(
        samples=samples,
        requested_if_center_hz=1_000_000_000,
        actual_if_center_hz=1_000_000_000,
        generation=4,
        sample_start=120_000,
        counter_authority=CounterAuthority.HARDWARE,
        validity_authority=ValidityAuthority.PROVIDER_ATTESTED,
        host_request_utc_ns=(100, 120),
        host_request_monotonic_ns=(50, 60),
        host_final_sample_monotonic_ns=1000,
    )
    return replace(result, **changes)


def test_geometry_is_exact_and_json_metadata_keeps_rf_unknown() -> None:
    config = configuration()
    assert config.window_samples == 50_000
    assert config.window_bytes == 400_000
    metadata = json.loads(json.dumps(asdict(config)))
    assert metadata["targets"][0]["rf_center_hz"] is None
    assert metadata["targets"][0]["rf_mapping_authority"] == "unknown"
    assert metadata["physical_receiver_labels"] == ["RX1", "RX2"]
    mono = replace(
        config, receiver_ids=(1,), physical_receiver_labels=("RX2",), scheduling_receiver_id=1
    )
    assert mono.window_bytes == 200_000


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"sample_rate_hz": 2_000_000}, "2.5 MS/s"),
        ({"window_ms": 120}, "20 ms"),
        ({"targets": ()}, "one to eight"),
        ({"receiver_ids": (0, 0)}, "unique"),
        ({"scheduling_receiver_id": 2}, "scheduling receiver"),
        ({"physical_receiver_labels": ("RX1",)}, "map every"),
        ({"duration_seconds": 1800.01}, "30 minutes"),
        ({"duration_seconds": math.nan}, "30 minutes"),
        ({"max_visits": 0}, "positive"),
        ({"max_visits": 0.5}, "integer"),
        ({"threshold_dbfs": math.inf}, "finite"),
        ({"gain_db": math.nan}, "finite"),
        ({"transition_budget_ms": 0}, "transition budget"),
        ({"transition_budget_ms": 101}, "transition budget"),
        ({"transition_budget_ms": True}, "transition budget"),
        ({"transition_budget_ms": 20.5}, "transition budget"),
    ],
)
def test_configuration_rejects_unbounded_or_unsupported_capture(changes, message) -> None:
    with pytest.raises(ValueError, match=message):
        configuration(**changes)


def test_rf_labels_require_explicit_consistent_mapping() -> None:
    with pytest.raises(ValueError, match="requires RF and LNB LO"):
        ShortWindowTarget("bad", 1_000_000_000, rf_mapping_authority="known")
    with pytest.raises(ValueError, match="disagrees"):
        ShortWindowTarget("bad", 1_000_000_000, 11_000_000_001, 10_000_000_000)
    target = ShortWindowTarget(
        "hypothesis",
        1_000_000_000,
        11_000_000_000,
        10_000_000_000,
        rf_mapping_authority=RfMappingAuthority.HYPOTHESIS,
    )
    assert target.rf_mapping_authority is RfMappingAuthority.HYPOTHESIS


def test_power_normalization_and_receiver_mapping_use_exact_iq() -> None:
    samples = np.empty((WINDOW_SAMPLES, 2, 2), dtype="<i2")
    samples[:, 0, :] = (1000, -2000)
    samples[:, 1, :] = (100, -200)
    powers = classify_window(acquisition(samples), configuration())
    assert powers[0].energy_sum == WINDOW_SAMPLES * 5_000_000
    assert powers[0].mean_component_power == 2_500_000
    assert powers[0].power_dbfs == pytest.approx(10 * math.log10(2_500_000 / 32768**2))
    assert (powers[0].mean_i, powers[0].mean_q) == (1000, -2000)
    assert powers[0].decision is ActivityDecision.ACTIVE
    assert powers[1].decision is ActivityDecision.QUIET
    assert powers[0].physical_receiver_label == "RX1"
    assert powers[1].physical_receiver_label == "RX2"


def test_activity_threshold_is_inclusive() -> None:
    samples = np.full((WINDOW_SAMPLES, 2, 2), 100, dtype="<i2")
    record = acquisition(samples)
    exact_dbfs = 10 * math.log10(100**2 / 32768**2)
    assert classify_window(record, configuration(threshold_dbfs=exact_dbfs))[0].decision == "active"
    assert (
        classify_window(record, configuration(threshold_dbfs=exact_dbfs + 1e-6))[0].decision
        == "quiet"
    )


def test_zero_power_is_explicit_quiet_and_json_finite() -> None:
    record = acquisition(np.zeros((WINDOW_SAMPLES, 2, 2), dtype="<i2"))
    powers = classify_window(record, configuration())
    assert all(power.zero_power for power in powers)
    assert all(power.energy_sum == 0 and power.power_dbfs is None for power in powers)
    assert all(power.decision is ActivityDecision.QUIET for power in powers)
    json.dumps([asdict(power) for power in powers], allow_nan=False)


def test_mixed_signed_energy_matches_unbounded_integer_oracle() -> None:
    samples = np.random.default_rng(17).integers(
        -32768, 32768, size=(WINDOW_SAMPLES, 2, 2), dtype=np.int16
    )
    powers = classify_window(acquisition(samples), configuration())
    for receiver, power in enumerate(powers):
        components = samples[:, receiver, :].reshape(-1).tolist()
        assert power.energy_sum == sum(value * value for value in components)
        assert power.mean_i == sum(components[::2]) / WINDOW_SAMPLES
        assert power.mean_q == sum(components[1::2]) / WINDOW_SAMPLES


def test_full_scale_energy_never_overflows_and_saturation_is_per_receiver() -> None:
    samples = np.zeros((WINDOW_SAMPLES, 2, 2), dtype="<i2")
    samples[:, 0, :] = -32768
    powers = classify_window(acquisition(samples), configuration())
    assert powers[0].energy_sum == 107_374_182_400_000
    assert powers[0].mean_component_power == 32768**2
    assert powers[0].power_dbfs == 0.0
    assert powers[0].clipping_count == 100_000
    assert powers[0].decision is ActivityDecision.UNKNOWN
    assert powers[0].quality_flags == ("clipping",)
    assert powers[1].decision is ActivityDecision.QUIET


@pytest.mark.parametrize(
    "changes, expected_flag",
    [
        ({"validity_authority": ValidityAuthority.DIAGNOSTIC_HOST_GUARD}, "unattested_validity"),
        ({"quality_flags": ("overflow",)}, "overflow"),
        ({"quality_flags": ("unsettled",)}, "unsettled"),
        ({"actual_if_center_hz": None}, "unknown_actual_if"),
    ],
)
def test_invalid_support_retains_power_and_cannot_claim_active(changes, expected_flag) -> None:
    record = acquisition(np.full((WINDOW_SAMPLES, 2, 2), 1000, dtype="<i2"), **changes)
    powers = classify_window(record, configuration())
    assert all(power.energy_sum == 100_000_000_000 for power in powers)
    assert all(power.decision is ActivityDecision.UNKNOWN for power in powers)
    assert all(expected_flag in power.quality_flags for power in powers)


@pytest.mark.parametrize("count", [0, 1, 49_999])
def test_partial_payload_is_not_padded_or_admitted_as_complete(count) -> None:
    record = acquisition(np.full((count, 2, 2), 1000, dtype="<i2"))
    assert record.samples.shape == (count, 2, 2)
    assert not record.complete
    powers = classify_window(record, configuration())
    assert all(power.sample_count == count for power in powers)
    assert all(power.decision is ActivityDecision.UNKNOWN for power in powers)
    assert all("partial_window" in power.quality_flags for power in powers)
    if count == 0:
        assert all(power.mean_component_power is None and not power.zero_power for power in powers)


def test_acquisition_owns_borrowed_iq_and_keeps_sample_time_separate_from_arrival() -> None:
    borrowed = np.ones((WINDOW_SAMPLES, 2, 2), dtype="<i2")
    record = acquisition(borrowed, counter_authority=CounterAuthority.SOFTWARE_DELIVERY_ORDINAL)
    borrowed[:] = 99
    assert np.all(record.samples == 1)
    assert not record.samples.flags.writeable
    assert record.sample_end == 170_000
    assert record.sample_start_utc_ns is None
    assert record.counter_authority is CounterAuthority.SOFTWARE_DELIVERY_ORDINAL


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"sample_start": None}, "hardware counter"),
        ({"host_request_utc_ns": (100, 99)}, "UTC request"),
        ({"host_request_monotonic_ns": (60, 50)}, "monotonic request"),
        ({"host_final_sample_monotonic_ns": 59}, "precedes"),
        ({"sample_start_utc_ns": (30, 20)}, "sample UTC"),
        ({"guard_ms": 20, "validity_includes_guard": True}, "applied again"),
    ],
)
def test_invalid_time_authority_or_double_guard_is_rejected(changes, message) -> None:
    with pytest.raises(ValueError, match=message):
        acquisition(np.zeros((WINDOW_SAMPLES, 2, 2), dtype="<i2"), **changes)


def test_block_assembler_clips_uneven_dma_blocks_and_copies_before_release() -> None:
    assembler = ShortWindowAssembler(receiver_count=2, generation=3, sample_start=100)
    expected = np.arange(60_000 * 4, dtype=np.int64).astype("<i2").reshape(60_000, 2, 2)
    start = 0
    for count in (7, 16_384, 9, 32_768, 10_832):
        borrowed = expected[start : start + count].copy()
        admitted = assembler.append(borrowed, generation=3, sample_start=100 + start)
        assert admitted == min(count, 50_000 - start)
        borrowed[:] = 0
        start += admitted
    assert assembler.complete
    assert assembler.sample_count == WINDOW_SAMPLES
    assert assembler.samples.tobytes() == expected[:WINDOW_SAMPLES].tobytes()
    with pytest.raises(ValueError, match="sealed"):
        assembler.append(expected[:1], generation=3, sample_start=50_100)


@pytest.mark.parametrize(
    "generation, sample_start, flags, expected",
    [
        (2, 110, (), "generation_changed"),
        (1, 111, (), "sample_discontinuity"),
        (1, 109, (), "sample_discontinuity"),
        (1, 110, ("stale_samples",), "stale_samples"),
        (1, 110, ("overflow",), "overflow"),
    ],
)
def test_assembler_seals_partial_at_gap_retune_stale_or_overflow(
    generation,
    sample_start,
    flags,
    expected,
) -> None:
    assembler = ShortWindowAssembler(2, 1, 100)
    block = np.ones((10, 2, 2), dtype="<i2")
    assert assembler.append(block, generation=1, sample_start=100) == 10
    assert (
        assembler.append(
            block, generation=generation, sample_start=sample_start, quality_flags=flags
        )
        == 0
    )
    assert not assembler.complete
    assert assembler.sample_count == 10
    assert assembler.samples.shape == (10, 2, 2)
    assert expected in assembler.quality_flags
    with pytest.raises(ValueError, match="sealed"):
        assembler.append(block, generation=1, sample_start=110)


def test_cancellation_preserves_partial_samples() -> None:
    assembler = ShortWindowAssembler(2, 1, 0)
    assembler.append(np.ones((123, 2, 2), dtype="<i2"), generation=1, sample_start=0)
    assembler.fail("cancelled")
    assert assembler.samples.shape == (123, 2, 2)
    assert assembler.quality_flags == ("cancelled",)
    assert not assembler.complete


@pytest.mark.parametrize("target_count", [4, 8])
def test_round_robin_preserves_first_sweep_then_repeats_with_visit_limit(target_count) -> None:
    config = configuration(target_count, max_visits=target_count * 2 + 1)
    scheduler = RoundRobinScheduler(config)
    visits = [scheduler.next_target(index * 0.020) for index in range(config.max_visits)]
    assert visits[:target_count] == list(config.targets)
    assert visits[target_count : 2 * target_count] == list(config.targets)
    assert visits[-1] == config.targets[0]
    assert scheduler.next_target(2) is None
    assert scheduler.stop_reason == "max_visits"


def test_duration_and_terminal_failures_stop_admission() -> None:
    scheduler = RoundRobinScheduler(configuration(duration_seconds=0.05))
    assert scheduler.next_target(0) is not None
    assert scheduler.next_target(0.02) is not None
    assert scheduler.next_target(0.05) is None
    assert scheduler.stop_reason == "duration"
    failed = RoundRobinScheduler(configuration())
    failed.stop("writer_overload")
    assert failed.next_target(0) is None
    assert failed.stop_reason == "writer_overload"


def test_custom_threshold_does_not_claim_minus38_comparison_policy() -> None:
    assert configuration().threshold_policy_id == "mean-component-ci16-minus38-comparison-v1"
    assert configuration(threshold_dbfs=-75).threshold_policy_id == (
        "mean-component-ci16-configured-threshold-v1"
    )
    assert (
        configuration(
            threshold_dbfs=-75, threshold_policy_id="calibrated-loopback-v1"
        ).threshold_policy_id
        == "calibrated-loopback-v1"
    )
