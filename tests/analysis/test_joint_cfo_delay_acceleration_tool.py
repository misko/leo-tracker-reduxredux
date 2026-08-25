from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parents[2]
MODULE_PATH = ROOT / "tools" / "prototype_joint_cfo_delay_acceleration.py"
REPORT = ROOT / "reports" / "2026_08_25_joint_cfo_delay_acceleration_prototype.md"
FIGURE_ROOT = ROOT / "reports" / "figures" / "2026_08_25_joint_cfo_delay_acceleration"
SPEC = importlib.util.spec_from_file_location("joint_prototype", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
prototype = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = prototype
SPEC.loader.exec_module(prototype)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def test_factorial_basis_exposes_derivatives_at_frozen_origin() -> None:
    basis = prototype.factorial_basis(
        np.asarray([prototype.REFERENCE_TIME_S, prototype.REFERENCE_TIME_S + 2.0]),
        3,
    )
    np.testing.assert_allclose(basis[0], [1.0, 0.0, 0.0, 0.0])
    np.testing.assert_allclose(basis[1], [1.0, 2.0, 2.0, 8.0 / 6.0])


def test_rational_lattice_preserves_integer_epoch_and_third_sample_teeth() -> None:
    reference = 94_002_005
    frame_indexes = np.asarray([-3, -2, -1, 0, 1, 2, 3], dtype=np.int64)
    nominal_thirds = 3 * reference + 10_000 * frame_indexes
    delay = np.asarray([-0.4, 0.2, 0.4, 0.0, -0.2, 0.45, -0.45])
    observed = prototype.quantize_delay(nominal_thirds, delay)
    recovered, recovered_nominal, center, lower, upper = prototype.rational_lattice(
        observed, reference
    )
    np.testing.assert_array_equal(recovered, frame_indexes)
    np.testing.assert_array_equal(recovered_nominal, nominal_thirds)
    np.testing.assert_allclose(upper - lower, 1.0)
    np.testing.assert_allclose(3.0 * center, np.rint(3.0 * center))
    np.testing.assert_array_equal(prototype.quantize_delay(recovered_nominal, center), observed)


def test_glrt64_cfo_timestamp_uses_supported_symbol_correlation_centroid() -> None:
    centroid, frame_count = prototype.glrt64_correlation_centroid_local_sample(1171)
    assert frame_count == 15
    assert centroid == 24_877.833333333332

    late_centroid, late_frame_count = prototype.glrt64_correlation_centroid_local_sample(3000)
    assert late_frame_count == 14
    assert late_centroid == 25_040.14285714286


def test_interval_em_recovers_quantized_quadratic() -> None:
    generator = np.random.default_rng(1234)
    times = np.linspace(38.0, 51.0, 500)
    truth = np.asarray([20.0, 1.25, -0.55])
    latent = prototype.predict_polynomial(times, truth)
    latent += generator.normal(0.0, 0.1, size=times.size)
    reference = 94_002_005
    frame_indexes = np.arange(times.size, dtype=np.int64) * 20
    nominal_thirds = 3 * reference + 10_000 * frame_indexes
    observed = prototype.quantize_delay(nominal_thirds, latent)
    _, _, _, lower, upper = prototype.rational_lattice(observed, reference)
    fit = prototype.fit_interval_timing(times, lower, upper, 2)
    assert fit["converged"]
    assert not fit["sigma_at_bound"]
    np.testing.assert_allclose(fit["coefficients"], truth, atol=0.02)


def test_rolling_origin_never_uses_current_or_future_block() -> None:
    blocks = np.asarray([41, 42, 43, 44, 45])
    splits = prototype.split_masks(blocks, "rolling_origin_next_calendar_block")
    assert [item[0] for item in splits] == [43, 44, 45]
    for block, training, validation, _partial in splits:
        assert np.all(blocks[training] < block)
        assert np.all(blocks[validation] == block)


def test_bounded_synthetic_algorithm_check_passes() -> None:
    assert prototype.synthetic_check()["accepted"]


def test_report_figure_links_resolve() -> None:
    report = REPORT.read_text(encoding="utf-8")
    links = re.findall(r"\]\((figures/[^)]+)\)", report)
    assert links == [
        ("figures/2026_08_25_joint_cfo_delay_acceleration/joint-cfo-delay-acceleration.png"),
        ("figures/2026_08_25_joint_cfo_delay_acceleration/frame-cfo-diagnostic.png"),
    ]
    assert all((REPORT.parent / link).is_file() for link in links)


def test_frozen_report_bundle_matches_manifest_and_declared_bytes() -> None:
    manifest_path = FIGURE_ROOT / "manifest.json"
    expected = {
        MODULE_PATH: "d9c04371a9c69670a7c266ff4e42e4b22e65e86449e6297da60fde5f6498d6ed",
        FIGURE_ROOT / "joint-cfo-delay-acceleration-evidence.json": (
            "45d31ac36f71d45bb792c5dd4be84b36b71cee97865ed0c33b073f90e3f64208"
        ),
        FIGURE_ROOT / "joint-model-rows.jsonl": (
            "05f33a0b492b84cda166bc7982c5554778c747f065ed93b4386eda60b3ff582c"
        ),
        FIGURE_ROOT / "joint-cfo-delay-acceleration.png": (
            "45e975929798d55668e7fc298f9ac31fa15b040c89991b5845ccd8c1b63f54ee"
        ),
        FIGURE_ROOT / "frame-cfo-diagnostic.png": (
            "33569f9991d398be654b6df0f3c95c173a022fbf0ffc61ae29b9deb52b33240f"
        ),
        manifest_path: "f05cccee8ee91123267dce29bb3f13405714d14b6a046dcd50e071ee9ae3f589",
    }
    assert {path: _sha256(path) for path in expected} == expected

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == ("org.leo.research.joint-cfo-delay-acceleration-manifest/v1")
    for artifact in manifest["artifacts"].values():
        artifact_path = ROOT / artifact["path"]
        assert artifact_path.is_file()
        assert _sha256(artifact_path) == artifact["sha256"]


def test_frozen_evidence_has_exact_temporal_denominators_and_fail_closed_gates() -> None:
    evidence = json.loads(
        (FIGURE_ROOT / "joint-cfo-delay-acceleration-evidence.json").read_text(encoding="utf-8")
    )
    assert evidence["input"]["detection_count"] == 550
    support = evidence["measurement_time_support"]["direct_cfo"]
    assert support["selected_symbols_inclusive"] == [2, 65]
    assert support["supported_frame_count"] == {"minimum": 14, "maximum": 15}
    np.testing.assert_allclose(
        [
            support["offset_from_probe_time_s"]["minimum"],
            support["offset_from_probe_time_s"]["median"],
            support["offset_from_probe_time_s"]["maximum"],
        ],
        [0.009617933333331052, 0.009964733333326592, 0.010299933333335787],
    )

    held_timing = evidence["temporal_validation"]["timing"]["held_calendar_1s_block"]
    rolling_timing = evidence["temporal_validation"]["timing"]["rolling_origin_next_calendar_block"]
    assert held_timing["1"]["aggregate"]["count"] == 550
    assert held_timing["1"]["aggregate"]["exact_integer_epoch_fraction"] == 25 / 550
    assert held_timing["2"]["aggregate"]["count"] == 550
    assert held_timing["2"]["aggregate"]["exact_integer_epoch_fraction"] == 520 / 550
    assert rolling_timing["1"]["aggregate"]["count"] == 336
    assert rolling_timing["1"]["aggregate"]["exact_integer_epoch_fraction"] == 0.0
    assert rolling_timing["2"]["aggregate"]["count"] == 336
    assert rolling_timing["2"]["aggregate"]["exact_integer_epoch_fraction"] == (318 / 336)

    held_cfo = evidence["temporal_validation"]["cfo"]["held_calendar_1s_block"]
    rolling_cfo = evidence["temporal_validation"]["cfo"]["rolling_origin_next_calendar_block"]
    np.testing.assert_allclose(
        [held_cfo[str(degree)]["aggregate"]["rms_hz"] for degree in (1, 2, 3)],
        [95.94255579182007, 64.94384971703147, 59.37673125711046],
    )
    np.testing.assert_allclose(
        [rolling_cfo[str(degree)]["aggregate"]["rms_hz"] for degree in (1, 2, 3)],
        [112.3342017344333, 77.45229260260646, 74.84928478592369],
    )

    frame = evidence["frame_rate_cfo_diagnostic"]
    assert not frame["used_for_model_fit_or_selection"]
    assert frame["accounting"]["total_rows"] == 10_369
    assert frame["even"]["count"] == frame["odd"]["count"] == 9_708
    np.testing.assert_allclose(
        [frame["even"]["residual_median_hz"], frame["odd"]["residual_median_hz"]],
        [1.02912205317989, 0.29761809844058007],
    )

    diagnostic = evidence["doppler_equivalent_rate_diagnostic"]
    assert not diagnostic["used_for_fit_or_selection"]
    np.testing.assert_allclose(
        [
            diagnostic["timing_acceleration_same_sign_cfo_rate_hz_s"],
            diagnostic["direct_cfo_rate_at_reference_hz_s"],
            diagnostic["same_sign_rate_difference_hz_s"],
        ],
        [-3591.770728409897, -3578.0778915273368, 13.692836882560186],
    )

    gates = evidence["gates"]
    assert gates["true_rolling_origin_reported"]
    assert gates["rational_lattice_and_interval_censoring_used"]
    assert gates["cfo_and_timing_cross_update_disabled"]
    assert not gates["fresh_heldout_rolled_qin_null_available"]
    assert not gates["cross_edge_or_receiver_channel_stability_available"]
    assert not gates["absolute_timing_or_physical_doppler_promotable"]
