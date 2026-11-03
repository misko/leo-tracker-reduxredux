"""Radio-free bounds and spectral diagnostics for the opt-in loopback harness."""

import numpy as np
import pytest

from tools.qualify_short_window_loopback import _tone_evidence, parser, plan


def arguments(extra=()):
    return parser().parse_args(
        [
            "--host",
            "192.168.1.15",
            "--serial",
            "development-serial",
            "--output-root",
            "/tmp/qualification",
            "--if-hz",
            "1800000000",
            "--if-hz",
            "1810000000",
            "--tx-if-hz",
            "1800000000",
            *extra,
        ]
    )


def test_dry_run_has_no_rf_opt_in_and_exact_dual_rx_geometry():
    args = arguments()
    assert not args.execute
    config = plan(args)
    assert config.window_samples == 50_000
    assert config.window_bytes == 400_000
    assert config.policy_id == "firmware-weighted-20ms-v1"
    assert config.receiver_ids == (0, 1)


@pytest.mark.parametrize(
    "extra",
    [
        ("--duration-seconds", "121"),
        ("--max-visits", "513"),
        ("--tx-gain-db", "-20"),
        ("--tone-hz", "0"),
        ("--if-hz", "1800000000"),
        ("--tx-if-hz", "1820000000"),
    ],
)
def test_loopback_rejects_unbounded_or_ambiguous_plan(extra):
    with pytest.raises(ValueError):
        plan(arguments(extra))


def test_tone_metrics_use_whole_window_and_detect_adc12_clipping():
    count = 50_000
    tone = 100_000
    phase = np.arange(count) * (2 * np.pi * tone / 2_500_000)
    signal = np.rint(np.stack((np.cos(phase), np.sin(phase)), axis=1) * 1000)
    values = np.stack((signal, signal), axis=1).astype("<i2")
    metrics = _tone_evidence(values, tone)
    assert metrics[0]["observed_peak_hz"] == tone
    assert metrics[1]["clipped_adc12_components"] == 0
    values[0, 1, 0] = 2047
    assert _tone_evidence(values, tone)[1]["clipped_adc12_components"] == 1
