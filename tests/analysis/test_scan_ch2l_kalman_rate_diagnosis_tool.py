from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

from leo.scanner.analysis_models import ScannerPilotDopplerConfigV1
from tools.report_scan_ch2l_kalman_rate_diagnosis import (
    _glrt_windows,
    _quadratic_summary,
    render,
    variant_configs,
)


def test_variant_configs_preserve_explicit_controls() -> None:
    variants = variant_configs(ScannerPilotDopplerConfigV1())

    assert variants["default_full"].phase_innovation_gate_rad == 1.2
    assert variants["phase_disabled_after_initialization"].phase_innovation_gate_rad == 1e-12
    assert variants["phase_sigma_fixed_0p5_rad"].minimum_phase_measurement_sigma_rad == 0.5
    assert variants["phase_sigma_fixed_0p5_rad"].maximum_phase_measurement_sigma_rad == 0.5
    assert variants["bootstrap_disabled"].rate_bootstrap_supported_frames == 100


def test_quadratic_summary_recovers_declared_endpoint_rate() -> None:
    times_s = np.linspace(0.001, 0.074, 56)
    reference_s = float(np.mean(times_s))
    centered = times_s - reference_s
    values_hz = 100_000.0 - 3_500.0 * centered + 4_000.0 * centered**2
    values_hz += 0.2 * np.sin(np.arange(times_s.size))

    result = _quadratic_summary(times_s, values_hz)

    expected_endpoint = -3_500.0 + 8_000.0 * (times_s[-1] - reference_s)
    assert np.isclose(result["endpoint_rate_hz_s"], expected_endpoint, atol=5.0)
    assert np.isclose(result["acceleration_hz_s2"], 8_000.0, atol=100.0)


def test_glrt_windows_keep_only_fully_contained_rank_zero_candidates() -> None:
    probes = []
    for probe_index, probe_start_ms in enumerate(range(0, 80, 10)):
        candidate = SimpleNamespace(
            candidate_rank=0,
            epoch_sample=140,
            tracking_cfo_hz=395_600.0 - 35.0 * probe_index,
            exact_score=0.7,
            control_score=0.1,
            margin=0.6,
            passed_margin_gate=True,
        )
        probes.append(
            SimpleNamespace(
                receiver_id=0,
                probe_index=probe_index,
                probe_start_ms=probe_start_ms,
                candidates=(candidate,),
            )
        )
    metrics = SimpleNamespace(
        configuration=SimpleNamespace(probe_ms=20),
        frames=(SimpleNamespace(target_index=2, probes=tuple(probes)),),
    )
    segment = SimpleNamespace(
        target_index=2,
        receiver_id=0,
        window_start_s=0.0,
        window_end_s=0.075,
        source_probe_index=0,
        source_candidate_rank=0,
        confirmation_probe_index=2,
        confirmation_candidate_rank=0,
    )

    windows = _glrt_windows(metrics, segment)

    assert [item["probe_start_ms"] for item in windows] == [0, 10, 20, 30, 40, 50]
    assert [item["segment_binding"] for item in windows] == [
        "source",
        None,
        "confirmation",
        None,
        None,
        None,
    ]


def _receiver(receiver_id: int, reference_hz: float, qualified: bool) -> dict[str, object]:
    times_s = [0.001 + index / 750.0 for index in range(12)]
    measured_hz = [reference_hz - 3_600.0 * (time_s - 0.008) for time_s in times_s]
    frames = []
    for index, (time_s, measurement_hz) in enumerate(zip(times_s, measured_hz, strict=True)):
        frames.append(
            {
                "frame_index": index,
                "time_since_retune_s": time_s,
                "absolute_cfo_measurement_hz": measurement_hz,
                "default_tracked_cfo_post_update_hz": measurement_hz - 8.0,
                "default_tracked_rate_post_update_hz_s": -3_000.0 - 20.0 * index,
                "phase_disabled_tracked_cfo_post_update_hz": measurement_hz - 1.0,
                "phase_disabled_tracked_rate_post_update_hz_s": -3_450.0,
            }
        )
    return {
        "receiver_id": receiver_id,
        "glrt_windows": [
            {
                "probe_start_ms": 0,
                "probe_end_ms": 20,
                "tracking_cfo_hz": reference_hz + 30.0,
                "segment_binding": "source",
            },
            {
                "probe_start_ms": 10,
                "probe_end_ms": 30,
                "tracking_cfo_hz": reference_hz + 5.0,
                "segment_binding": None,
            },
            {
                "probe_start_ms": 20,
                "probe_end_ms": 40,
                "tracking_cfo_hz": reference_hz - 20.0,
                "segment_binding": "confirmation",
            },
        ],
        "frames": frames,
        "direct": {
            "reference_time_s": 0.008,
            "cfo_at_reference_hz": reference_hz,
            "rate_hz_s": -3_600.0,
            "conditional_rate_sigma_hz_s": 120.0,
        },
        "variants": {"default_full": {"rate_bootstrap_frame_index": 5}},
        "published": {"qualified": qualified},
    }


def test_render_ch2l_comparison(tmp_path: Path) -> None:
    receipt = {
        "scan_id": "scan-burst-2b2a98cc0de846b8-03",
        "receivers": [
            _receiver(0, 395_000.0, True),
            _receiver(1, -150_000.0, False),
        ],
    }
    destination = tmp_path / "ch2l-comparison.png"
    repeat_destination = tmp_path / "ch2l-comparison-repeat.png"

    render(receipt, destination)
    render(receipt, repeat_destination)

    with Image.open(destination) as image:
        assert image.format == "PNG"
        assert image.width >= 2000
        assert image.height >= 1400
    assert destination.read_bytes() == repeat_destination.read_bytes()
