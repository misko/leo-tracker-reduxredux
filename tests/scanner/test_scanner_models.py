from __future__ import annotations

import pytest

from leo.scanner import (
    ScannerConfiguration,
    ScannerConfigurationV2,
    ScannerConfigurationV3,
    current_low_band_targets,
    scheduled_low_band_targets,
)


def test_current_low_band_plan_has_all_edges_in_ascending_if_order() -> None:
    targets = current_low_band_targets()
    configuration = ScannerConfiguration(targets=targets)

    assert [(item.channel, item.edge.value, item.if_center_hz) for item in targets] == [
        (1, "lower", 959_687_500),
        (1, "upper", 1_190_312_500),
        (2, "lower", 1_209_687_500),
        (2, "upper", 1_440_312_500),
        (3, "lower", 1_459_687_500),
        (3, "upper", 1_690_312_500),
        (4, "lower", 1_709_687_500),
        (4, "upper", 1_940_312_500),
    ]
    assert configuration.dwell_ms == 120
    assert configuration.dwell_samples == 300_000
    assert configuration.dwell_ms * len(configuration.targets) == 960
    assert configuration.probe_samples == 50_000
    assert configuration.probe_stride_ms == 10
    assert configuration.probe_stride_samples == 25_000
    assert configuration.scheduled_probe_count == 11
    assert configuration.kernel_buffers == 1


def test_dwell_can_be_tripled_without_changing_probe_geometry() -> None:
    configuration = ScannerConfiguration(dwell_ms=240, targets=current_low_band_targets())

    assert configuration.dwell_samples == 600_000
    assert configuration.scheduled_probe_count == 23


def test_v2_live_scanner_defaults_to_reset_bounded_metadata_and_eight_buffers() -> None:
    configuration = ScannerConfigurationV2(targets=current_low_band_targets())

    assert configuration.schema_version == 2
    assert configuration.kernel_buffers == 8
    assert configuration.tuning_settle_us == 250
    assert configuration.require_device_metadata is True
    assert configuration.reset_receive_buffer_before_each_target is True

    with pytest.raises(ValueError, match="greater than or equal to 2"):
        ScannerConfigurationV2(kernel_buffers=1, targets=current_low_band_targets())


def test_dwell_can_cover_long_per_edge_experiments() -> None:
    configuration = ScannerConfiguration(dwell_ms=1_500, targets=current_low_band_targets())

    assert configuration.dwell_samples == 3_750_000
    assert configuration.scheduled_probe_count == 149


def test_plan_rejects_reordered_or_duplicate_edges() -> None:
    targets = current_low_band_targets()

    with pytest.raises(ValueError, match="increasing IF"):
        ScannerConfiguration(targets=tuple(reversed(targets)))
    with pytest.raises(ValueError, match="unique"):
        ScannerConfiguration(targets=(targets[0], targets[0]))


@pytest.mark.parametrize(
    ("sample_rate_hz", "dwell_samples"),
    ((2_500_000, 300_000), (5_000_000, 600_000)),
)
def test_v3_run_plan_is_lower_then_upper_at_maximum_bandwidth(
    sample_rate_hz: int,
    dwell_samples: int,
) -> None:
    targets = scheduled_low_band_targets(bandwidth_hz=sample_rate_hz)
    configuration = ScannerConfigurationV3(
        sample_rate_hz=sample_rate_hz,
        bandwidth_hz=sample_rate_hz,
        targets=targets,
    )

    assert [(item.channel, item.edge.value, item.if_center_hz) for item in targets] == [
        (1, "lower", 959_687_500),
        (2, "lower", 1_209_687_500),
        (3, "lower", 1_459_687_500),
        (4, "lower", 1_709_687_500),
        (1, "upper", 1_190_312_500),
        (2, "upper", 1_440_312_500),
        (3, "upper", 1_690_312_500),
        (4, "upper", 1_940_312_500),
    ]
    assert configuration.dwell_samples == dwell_samples
    assert configuration.bandwidth_hz == configuration.sample_rate_hz


def test_v3_run_plan_rejects_old_if_sorted_order() -> None:
    with pytest.raises(ValueError, match="CH1L..CH4L"):
        ScannerConfigurationV3(targets=current_low_band_targets())


def test_v3_run_plan_rejects_bandwidth_narrower_than_the_sample_rate() -> None:
    with pytest.raises(ValueError, match="bandwidth must equal sample rate"):
        ScannerConfigurationV3(
            sample_rate_hz=5_000_000,
            bandwidth_hz=2_500_000,
            targets=scheduled_low_band_targets(bandwidth_hz=2_500_000),
        )


def test_v3_maximum_coverage_if_moves_inward_for_a_wider_native_rate() -> None:
    targets = scheduled_low_band_targets(bandwidth_hz=10_000_000)

    configuration = ScannerConfigurationV3(
        sample_rate_hz=10_000_000,
        bandwidth_hz=10_000_000,
        targets=targets,
    )

    assert [item.if_center_hz for item in configuration.targets] == [
        960_000_000,
        1_210_000_000,
        1_460_000_000,
        1_710_000_000,
        1_190_000_000,
        1_440_000_000,
        1_690_000_000,
        1_940_000_000,
    ]
