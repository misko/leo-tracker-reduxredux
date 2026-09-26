"""Regression tests for reversible phase recovery bookkeeping."""
import importlib.util
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "reports/2026_09_26_scan_fw_32a202b6e55630ec_phase_replay/single-track/recovery/reversible/replay.py"
SPEC = importlib.util.spec_from_file_location("reversible_replay", PATH)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def test_known_geometry_survives_derotation_and_exact_addback():
    time = np.arange(200) * 0.00075
    geometry_cycles = 0.17 + 8.0 * time + 13.0 * time**2
    instrument_cycles = -0.31 + 23.0 * time
    measured = np.exp(1j * M.TAU * (geometry_cycles + instrument_cycles))
    residual, reconstructed, _ = M.reversible_derotate(measured, instrument_cycles)
    np.testing.assert_allclose(residual, np.exp(1j * M.TAU * geometry_cycles), atol=2e-15)
    np.testing.assert_allclose(reconstructed, measured, atol=2e-15)
    # Keeping only the residual loses the removed coordinate.
    assert np.sqrt(np.mean(M.wrap_radians(np.angle(residual) - np.angle(measured))**2)) > 0.3


def test_tracker_removal_is_also_reversible_and_causal():
    time = np.arange(40) * 0.00075
    phase = 0.2 + M.TAU * (5 * time + 80 * time**2)
    observed = np.exp(1j * phase)
    prediction_cycles, _ = M.causal_previous_increment(time, observed)
    supported = np.isfinite(prediction_cycles)
    residual, reconstructed, _ = M.reversible_derotate(observed[supported], prediction_cycles[supported])
    np.testing.assert_allclose(reconstructed, observed[supported], atol=1e-15)
    altered = observed.copy(); altered[20:] *= np.exp(1.3j)
    altered_prediction, _ = M.causal_previous_increment(time, altered)
    np.testing.assert_allclose(altered_prediction[:21], prediction_cycles[:21], equal_nan=True)


def test_gaps_reset_tracker_and_relative_phase_without_cycle_inference():
    time = np.arange(12) * 0.00075
    time[6:] += 0.02
    observed = np.exp(1j * (0.4 + 3.0 * time))
    prediction, segment = M.causal_previous_increment(time, observed)
    relative, relative_segment = M.contiguous_relative_phase(time, observed)
    assert np.isnan(prediction[6:8]).all()
    assert segment[6] == segment[5] + 1
    assert relative_segment[6] == relative_segment[5] + 1
    assert abs(relative[6]) < 1e-14


def test_missing_frame_breaks_segment_without_unwrapping_across_it():
    time = np.arange(10) * 0.00075
    observed = np.exp(1j * (0.2 + 4.0 * time))
    observed[5] = np.nan + 1j * np.nan
    prediction, segment = M.causal_previous_increment(time, observed)
    relative, relative_segment = M.contiguous_relative_phase(time, observed)
    assert segment[5] == -1 and relative_segment[5] == -1
    assert segment[6] == segment[4] + 1
    assert np.isnan(prediction[5:8]).all()
    assert abs(relative[6]) < 1e-14


def test_large_declared_cycle_count_is_reduced_before_phasor_conversion():
    cycles = np.array([682434.861324057, 682434.861324057 + 10**9])
    phasor = M.unit_phase(cycles)
    np.testing.assert_allclose(phasor[0], phasor[1], atol=1e-6)


def test_frozen_five_dwell_cache_reconstructs_all_supported_frame_phasors():
    cache_path = ROOT / "reports/2026_09_26_scan_fw_32a202b6e55630ec_phase_replay/single-track/improvements/pilot-cache.npz"
    cache = np.load(cache_path)
    cached = M.weighted_unit_mean(cache["products"], cache["weights"])
    declared = cached * M.unit_phase(cache["correction_cycles"])
    for visit in np.unique(cache["frame_visit_index"]):
        selected = cache["frame_visit_index"] == visit
        prediction, _ = M.causal_previous_increment(cache["frame_time_in_dwell_s"][selected], cached[selected])
        supported = np.isfinite(prediction)
        _, reconstructed, _ = M.reversible_derotate(
            declared[selected][supported], cache["correction_cycles"][selected][supported] + prediction[supported]
        )
        np.testing.assert_allclose(reconstructed, declared[selected][supported], atol=3e-16)
