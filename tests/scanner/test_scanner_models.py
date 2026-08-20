from __future__ import annotations

import pytest

from leo.scanner import ScannerConfiguration, current_low_band_targets


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
    assert configuration.dwell_samples == 200_000
    assert configuration.probe_samples == 50_000
    assert configuration.kernel_buffers == 1


def test_plan_rejects_reordered_or_duplicate_edges() -> None:
    targets = current_low_band_targets()

    with pytest.raises(ValueError, match="increasing IF"):
        ScannerConfiguration(targets=tuple(reversed(targets)))
    with pytest.raises(ValueError, match="unique"):
        ScannerConfiguration(targets=(targets[0], targets[0]))
