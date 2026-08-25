from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parents[2]
MODULE_PATH = ROOT / "tools" / "compare_visible_starlink_tle_fit.py"
REPORT = ROOT / "reports" / "2026_08_25_150802_visible_starlink_tle_fit.md"
FIGURE_ROOT = ROOT / "reports" / "figures" / "2026_08_25_150802_visible_starlink_tle_fit"
SPEC = importlib.util.spec_from_file_location("visible_starlink_fit", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
fit_tool = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = fit_tool
SPEC.loader.exec_module(fit_tool)


def test_shift_and_constant_offset_recover_nonlinear_curve() -> None:
    model_time = np.linspace(-2.0, 12.0, 2801)
    model = 200.0 * model_time + 11.0 * model_time**2 + 0.4 * model_time**3
    observation_time = np.linspace(0.0, 10.0, 401)
    true_shift = 0.35
    true_offset = -12_345.0
    observed = np.interp(observation_time + true_shift, model_time, model) + true_offset
    shifts = np.arange(-1.0, 1.0001, 0.005)

    forward, reverse, full, curve = fit_tool.fit_candidate(
        model_time, model, observation_time, observed, shifts
    )

    np.testing.assert_allclose(
        [forward.shift_s, reverse.shift_s, full.shift_s], true_shift, atol=1e-12
    )
    assert abs(full.offset_hz - true_offset) < 1e-9
    assert forward.evaluation_rms_hz < 1e-9
    assert reverse.evaluation_rms_hz < 1e-9
    np.testing.assert_allclose(curve, observed, atol=1e-9)


def test_fit_selection_never_uses_evaluation_rows() -> None:
    observed = np.asarray([1.0, 1.0, 101.0, 101.0])
    shifts = np.asarray([-1.0, 1.0])
    prediction = np.asarray(
        [
            [0.0, 0.0, 100.0, 100.0],
            [0.0, 0.0, 0.0, 0.0],
        ]
    )
    training = np.asarray([True, True, False, False])
    evaluation = ~training

    fit, selected = fit_tool.fit_shift_offset_from_prediction_matrix(
        prediction, observed, shifts, training, evaluation
    )

    assert selected == 0
    assert fit.shift_s == -1.0
    assert fit.offset_hz == 1.0
    assert fit.training_rms_hz == 0.0
    assert fit.evaluation_rms_hz == 0.0


def test_single_fixed_shift_is_not_reported_as_a_search_boundary() -> None:
    prediction = np.asarray([[0.0, 1.0, 2.0]])
    observed = np.asarray([10.0, 11.0, 12.0])
    support = np.asarray([True, True, True])
    fit, selected = fit_tool.fit_shift_offset_from_prediction_matrix(
        prediction, observed, np.asarray([0.0]), support, support
    )
    assert selected == 0
    assert fit.shift_s == 0.0
    assert fit.offset_hz == 10.0
    assert not fit.shift_at_boundary


def test_sampling_grid_includes_exact_endpoints() -> None:
    grid = fit_tool.sampling_grid(1_000_000_000, 2_000_000_000, 0.1)
    assert grid.utc_ns[0] == 1_000_000_000
    assert grid.utc_ns[-1] == 2_000_000_000
    assert np.all(np.diff(grid.utc_ns) > 0)


def test_report_figure_links_resolve() -> None:
    report = REPORT.read_text(encoding="utf-8")
    links = re.findall(r"\]\((figures/[^)]+)\)", report)
    assert links == [
        "figures/2026_08_25_150802_visible_starlink_tle_fit/all-visible-satellite-fits.png",
        "figures/2026_08_25_150802_visible_starlink_tle_fit/all-visible-sky-geometry.png",
    ]
    assert all((REPORT.parent / link).is_file() for link in links)


def test_frozen_evidence_accounts_for_every_visible_candidate() -> None:
    evidence = json.loads(
        (FIGURE_ROOT / "visible-starlink-tle-fit-evidence.json").read_text(encoding="utf-8")
    )
    assert evidence["schema"] == "org.leo.research.visible-starlink-tle-fit/v1"
    assert evidence["candidate_only"]
    assert evidence["input"]["cfo_measurement_count"] == 550
    assert evidence["accounting"]["catalogue_count"] == 10_972
    assert evidence["accounting"]["excluded_below_120_km_count"] == 2
    assert evidence["accounting"]["geometric_horizon_union_count"] == 561
    assert evidence["accounting"]["ten_degree_union_count"] == 250
    assert len(evidence["candidates"]) == 561
    assert len({row["norad_id"] for row in evidence["candidates"]}) == 561

    best = evidence["headline"]["primary_best"]
    assert best["norad_id"] == 59_748
    np.testing.assert_allclose(
        [
            best["bidirectional_holdout_rms_hz"],
            best["zero_shift_bidirectional_holdout_rms_hz"],
            best["full_fit"]["shift_s"],
            best["full_fit"]["offset_hz"],
            best["full_fit"]["full_rms_hz"],
        ],
        [68.35579518932292, 54.45116861028307, -0.155, -133022.09772832983, 55.890749120857414],
    )
    assert evidence["headline"]["wide_holdout_best"]["norad_id"] == 58_219
    assert evidence["adjacent_prior_tle_sensitivity"]["changed_element_norad_ids"] == [47_657]
    assert not evidence["adjacent_prior_tle_sensitivity"][
        "changed_elements_intersect_visible_population"
    ]

    assert evidence["input"]["analysis_tool_sha256"] == fit_tool.sha256_file(MODULE_PATH)
    for artifact in evidence["artifacts"].values():
        artifact_path = FIGURE_ROOT / artifact["path"]
        assert fit_tool.sha256_file(artifact_path) == artifact["sha256"]
