from tools.benchmark_position_ablations import factorial_models


def test_factorial_changes_all_four_factors_independently():
    models = factorial_models()
    assert len(models) == len({m["name"] for m in models}) == 16
    settings = [m["formal_orbit_config"] for m in models]
    for key in settings[0]:
        assert len({x[key] for x in settings}) == 2
    full = next(m for m in models if m["name"] == "orbit1-correlation1-robust1-scale1")
    assert full["formal_orbit_config"] == {
        "phase_rate_bound_s_h": 0.25,
        "ar1_rho": 0.65,
        "gaussian_noise": False,
        "infer_measurement_sigma": True,
    }
    assert all(set(m) == {"name", "formal_orbit_config"} for m in models)


def test_failed_accurate_estimate_is_not_counted_as_a_success():
    from tools.report_position_ablations import groups

    base = {
        "model": "formal-orbit-correction-v6",
        "method": "density",
        "fraction": 1 / 32,
        "actual_fitting_count": 399,
        "evaluation_rms_hz": 10,
        "supported_evaluation_observations": 100,
    }
    rows = [
        {**base, "status": "nonconverged", "horizontal_error_m": 1},
        {**base, "status": "converged", "horizontal_error_m": 2000},
    ]
    result = groups(rows)[0]
    assert result["converged"] == 1 and result["total"] == 2
    assert result["subkm_all_attempts"] == 0
    assert result["error_m"] == [2000, 2000, 2000]


def test_new_factorial_model_name_can_render_summary(tmp_path):
    from tools.benchmark_position_subsets import _plot_summary

    path = tmp_path / "plot.png"
    _plot_summary(
        [
            {
                "model": "orbit0-correlation0-robust0-scale0",
                "method": "density",
                "status": "converged",
                "horizontal_error_m": 100,
                "evaluation_rms_hz": 20,
                "actual_fraction": 1,
                "actual_fitting_count": 100,
            }
        ],
        path,
    )
    assert path.read_bytes().startswith(b"\x89PNG")
