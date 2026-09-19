from pathlib import Path

from PIL import Image

from tools.report_scanner_tle_polynomial_rms import _render_track_plots


def test_track_renderer_emits_separate_linear_scale_figure(tmp_path: Path) -> None:
    candidates = []
    for rank in range(1, 6):
        candidate = {
            "standard_rank": rank,
            "catalog_number": 60_000 + rank,
            "offset_only_training_rms_hz": float(rank),
            "offset_only_heldout_rms_hz": float(rank * 2),
            "polynomial_residual_fits": {
                str(degree): {
                    "training_rms_hz": float(rank * degree),
                    "heldout_rms_hz": float(rank * degree * 2),
                }
                for degree in (1, 2, 3)
            },
        }
        if rank <= 2:
            candidate["plot_evidence"] = {
                "time_s": [10.0, 11.0, 12.0, 13.0],
                    "training_mask": [True, False, True, False],
                "measured_cfo_hz": [100.0, 90.0, 80.0, 70.0],
                "tle_cfo_hz": [96.0, 87.0, 78.0, 69.0],
                "raw_tle_residual_hz": [4.0, 3.0, 2.0, 1.0],
                "fitted_cfo_hz": {
                    str(degree): [100.0, 90.0, 80.0, 70.0] for degree in (1, 2, 3)
                },
                "postfit_residual_hz": {
                    str(degree): [0.0, 0.0, 0.0, 0.0] for degree in (1, 2, 3)
                },
            }
        candidates.append(candidate)
    tracks = [
        {
            "channel": 2,
            "edge": "upper",
            "start_s": 10.0,
            "end_s": 30.0,
            "observation_count": 20,
            "training_count": 12,
            "heldout_count": 8,
            "candidates": candidates,
        }
    ]

    names = _render_track_plots("scan-fw-example", tracks, tmp_path)

    assert names == ["scan-fw-example-track-01-ch2-upper-top5-tle-review.png"]
    with Image.open(tmp_path / names[0]) as image:
        assert image.size == (2250, 2100)
