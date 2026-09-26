from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parents[2]
PATH = ROOT / (
    "reports/2026_09_26_scan_fw_32a202b6e55630ec_phase_replay/"
    "single-track/recovery/validation/observability.py"
)
SPEC = importlib.util.spec_from_file_location("recovery_observability", PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

REFERENCE_PATH = PATH.parents[1] / "reference/run.py"
REFERENCE_SPEC = importlib.util.spec_from_file_location(
    "recovery_reference_under_validation", REFERENCE_PATH
)
assert REFERENCE_SPEC is not None and REFERENCE_SPEC.loader is not None
REFERENCE = importlib.util.module_from_spec(REFERENCE_SPEC)
REFERENCE_SPEC.loader.exec_module(REFERENCE)


def test_arbitrary_smooth_phase_can_move_between_geometry_and_instrument() -> None:
    time_s = np.linspace(0.0, 0.6, 601)
    geometry = 0.3 + 1.7 * time_s + 0.2 * time_s**2
    instrument = -0.8 + 0.4 * np.sin(2 * np.pi * 1.3 * time_s)
    arbitrary_q = 1.1 * np.sin(2 * np.pi * 0.37 * time_s) + 0.9 * time_s**3
    moved_geometry, moved_instrument = MODULE.equivalent_decomposition(
        geometry, instrument, arbitrary_q
    )
    np.testing.assert_allclose(moved_geometry + moved_instrument, geometry + instrument)
    assert np.max(np.abs(moved_geometry - geometry)) > 0.5


def test_stable_instrument_preserves_geometry_change_but_not_absolute_phase() -> None:
    geometry = np.array([1.0, 1.4, 2.1, 3.0])
    measured_a = geometry + 0.37
    measured_b = geometry - 2.22
    np.testing.assert_allclose(
        MODULE.relative_to_first(measured_a), MODULE.relative_to_first(geometry)
    )
    np.testing.assert_allclose(
        MODULE.relative_to_first(measured_b), MODULE.relative_to_first(geometry)
    )
    assert not np.allclose(measured_a, measured_b)


def test_known_reference_geometry_breaks_time_varying_ambiguity() -> None:
    time_s = np.linspace(0.0, 0.6, 601)
    geometry = 0.2 + 2.3 * time_s - 0.7 * time_s**2
    instrument = -0.5 + 0.9 * np.sin(2 * np.pi * 0.8 * time_s)
    reference_geometry = 0.4 - 0.1 * time_s
    result = MODULE.recover_with_reference(
        geometry + instrument, reference_geometry + instrument, reference_geometry
    )
    np.testing.assert_allclose(result.phase, geometry, atol=1e-12)


def test_unknown_injection_path_remains_as_recovery_bias() -> None:
    time_s = np.linspace(0.0, 0.6, 601)
    geometry = 0.6 + 1.2 * time_s
    instrument = 0.4 * np.sin(2 * np.pi * time_s)
    injection_path = 0.27 + 0.08 * time_s
    known_reference_geometry = np.zeros_like(time_s)
    result = MODULE.recover_with_reference(
        geometry + instrument,
        known_reference_geometry + instrument + injection_path,
        known_reference_geometry,
    )
    np.testing.assert_allclose(result.phase, geometry - injection_path, atol=1e-12)
    assert not np.allclose(result.phase, geometry)


@pytest.mark.parametrize(
    "reference,known",
    [
        (np.array([0.0, np.nan, 0.2]), np.zeros(3)),
        (np.array([0.0, 0.1]), np.zeros(2)),
        (np.array([0.0, 0.1, 0.2]), np.array([0.0, np.inf, 0.0])),
    ],
)
def test_corrupt_or_mismatched_reference_is_rejected(
    reference: np.ndarray, known: np.ndarray
) -> None:
    with pytest.raises(ValueError):
        MODULE.recover_with_reference(np.zeros(3), reference, known)


def test_calibration_is_target_blind() -> None:
    instrument = np.array([0.2, 0.4, 0.1, -0.1])
    known_reference_geometry = np.array([0.0, 0.1, 0.2, 0.3])
    reference = known_reference_geometry + instrument
    target_a = np.array([0.3, 0.5, 0.8, 1.2])
    target_b = np.array([-1.0, -0.4, 0.7, 2.4])
    recovered_a = MODULE.recover_with_reference(
        target_a + instrument, reference, known_reference_geometry
    )
    recovered_b = MODULE.recover_with_reference(
        target_b + instrument, reference, known_reference_geometry
    )
    np.testing.assert_array_equal(
        recovered_a.reference_instrument, recovered_b.reference_instrument
    )
    np.testing.assert_allclose(recovered_a.phase, target_a)
    np.testing.assert_allclose(recovered_b.phase, target_b)


def test_noncommon_multipath_survives_reference_subtraction() -> None:
    geometry = np.array([0.0, 0.2, 0.5, 0.9])
    instrument = np.array([0.1, 0.3, 0.2, 0.4])
    target_multipath = np.array([0.0, -0.2, 0.1, 0.3])
    zeros = np.zeros(4)
    recovered = MODULE.recover_with_reference(
        geometry + instrument + target_multipath, instrument, zeros
    )
    np.testing.assert_allclose(recovered.phase, geometry + target_multipath)


def test_wrapped_samples_do_not_identify_unwrap_across_a_gap() -> None:
    before_gap = 0.9 * np.pi
    after_gap_candidates = np.array([-0.9 * np.pi, 1.1 * np.pi, 3.1 * np.pi])
    wrapped = MODULE.wrap_rad(after_gap_candidates)
    np.testing.assert_allclose(wrapped, wrapped[0])
    assert len(np.unique(after_gap_candidates - before_gap)) == 3


def test_reference_prototype_rejects_or_masks_corrupt_inputs() -> None:
    data = REFERENCE.simulate(seed=91, n=80, tones=4, delay_samples=1)
    train = np.arange(80) < 20
    zero_reference = data["reference"].copy()
    zero_reference[11] = 0
    result = REFERENCE.recover(
        data["satellite"], zero_reference, data["injection"], 1, train
    )
    assert not result["valid"][10]
    missing_satellite = data["satellite"].copy()
    missing_satellite[30] = np.nan + 1j * np.nan
    result = REFERENCE.recover(
        missing_satellite, data["reference"], data["injection"], 1, train
    )
    assert not result["valid"][30]
    with pytest.raises(ValueError, match="finite and nonzero"):
        REFERENCE.recover(
            data["satellite"], data["reference"], np.zeros(4), 1, train
        )


def test_reference_prototype_is_target_blind_and_uses_no_truth_argument() -> None:
    data = REFERENCE.simulate(seed=92, n=80, tones=4, delay_samples=0)
    train = np.arange(80) < 20
    base = REFERENCE.recover(
        data["satellite"], data["reference"], data["injection"], 0, train
    )
    target_change = np.exp(0.63j)
    changed = REFERENCE.recover(
        data["satellite"] * target_change,
        data["reference"],
        data["injection"],
        0,
        train,
    )
    valid = base["valid"] & changed["valid"]
    np.testing.assert_allclose(
        REFERENCE.wrap(changed["phase_rad"][valid] - base["phase_rad"][valid]),
        0.63,
        atol=1e-12,
    )
