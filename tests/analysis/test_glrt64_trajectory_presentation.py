from __future__ import annotations

import struct

from leo.analysis.starlink.glrt64_presentation import render_glrt64_trajectory_png


def test_full_dwell_glrt64_png_contains_baseline_correction_and_all_model_orders() -> None:
    detections = {
        "detections": [
            {
                "time_s": time_s,
                "scores": [
                    {
                        "method": "glrt64",
                        "margin": 0.1 + time_s / 100,
                        "tracking_cfo_hz": 300_000 - 1_000 * time_s,
                    }
                ],
            }
            for time_s in (0.0, 10.0, 20.0, 30.0, 59.95)
        ]
    }
    redetection = {
        "results": [
            {
                "family_id": "sha256:" + "a" * 64,
                "time_s": time_s,
                "detector_method": "glrt64",
                "corrected_margin": 0.7,
            }
            for time_s in (10.0, 10.05, 10.1)
        ]
    }
    table = {
        "trajectories": [
            {
                "trajectory_id": f"trajectory-{degree}",
                "family_id": "sha256:" + str(degree) * 64,
                "model": model,
                "polynomial_degree": degree,
                "reference_time_s": 15.0,
                "coefficients_hz": [0.0] * degree + [300_000.0],
                "start_s": 5.0 * degree,
                "end_s": 5.0 * degree + 10.0,
                "residual_rms_hz": 100.0,
                "fit_matches_well": True,
                "selected_for_correction": degree == 2,
            }
            for degree, model in ((1, "linear"), (2, "quadratic"), (3, "cubic"))
        ]
    }

    payload = render_glrt64_trajectory_png("run-a", detections, redetection, table)

    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", payload[16:24])
    assert width == 2_560
    assert height == 1_440
    assert len(payload) < 8 * 1024 * 1024
