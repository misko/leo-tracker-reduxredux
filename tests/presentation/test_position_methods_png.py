from leo.cli.scan_position_methods import REFERENCE, evaluated_result
from leo.presentation.position_methods import render_position_method


def test_position_png_reports_estimate_and_explicit_insufficiency():
    for method, payload in (
        (
            "expanded-doppler",
            dict(
                state="complete",
                latitude_deg=37.8,
                longitude_deg=-122.4,
                training_residual_hz=[2.0, -1.0],
                evaluation_residual_hz=[3.0, -2.0],
            ),
        ),
        ("orbit-corrected", dict(state="insufficient", reasons=["too-few-sources"])),
        ("identity-mixture", dict(state="failed", reasons=["optimizer-not-converged"])),
    ):
        result = evaluated_result(method, payload)
        png = render_position_method(
            result, session_id="scan-fw-test", reference_position=REFERENCE
        )
        assert png.startswith(b"\x89PNG\r\n\x1a\n")
        assert len(png) > 10_000
