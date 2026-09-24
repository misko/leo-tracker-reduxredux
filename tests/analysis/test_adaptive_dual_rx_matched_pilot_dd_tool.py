from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np


def _load_tool():
    path = Path(__file__).parents[2] / "tools" / "report_adaptive_dual_rx_matched_pilot_dd.py"
    spec = importlib.util.spec_from_file_location("matched_pilot_dd_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


subject = _load_tool()


def _correlated_design(
    rng: np.random.Generator,
    *,
    count: int = 128,
    coherence: float = 0.7,
) -> np.ndarray:
    first = rng.normal(size=count) + 1j * rng.normal(size=count)
    first /= np.linalg.norm(first)
    orthogonal = rng.normal(size=count) + 1j * rng.normal(size=count)
    orthogonal -= first * np.vdot(first, orthogonal)
    orthogonal /= np.linalg.norm(orthogonal)
    second = coherence * first + np.sqrt(1.0 - coherence**2) * orthogonal
    return np.column_stack((first, second)) * np.sqrt(count)


def _phase_error_deg(actual: complex, expected: complex) -> float:
    return abs(float(np.degrees(np.angle(actual * np.conj(expected)))))


def test_covariance_correction_removes_independent_receiver_noise_bias() -> None:
    rng = np.random.default_rng(20260921)
    design = _correlated_design(rng, coherence=0.8)
    naive: list[complex] = []
    corrected: list[complex] = []
    for _ in range(1_500):
        fits = [
            subject.joint_complex_fit(
                rng.normal(size=len(design)) + 1j * rng.normal(size=len(design)),
                design,
            )
            for _receiver in range(2)
        ]
        result = subject.covariance_corrected_dd(fits[0], fits[1])
        naive.append(result["naive_phasor"])
        corrected.append(result["corrected_phasor"])

    naive_mean = complex(np.mean(naive))
    corrected_mean = complex(np.mean(corrected))
    assert naive_mean.real > 0.0008
    assert abs(corrected_mean) < 0.10 * abs(naive_mean)


def test_missing_second_source_has_low_coefficient_snr() -> None:
    rng = np.random.default_rng(5)
    design = _correlated_design(rng)
    values = 4.0 * design[:, 0] + (rng.normal(size=len(design)) + 1j * rng.normal(size=len(design)))
    fit = subject.joint_complex_fit(values, design)
    assert fit.coefficient_snr[0] > 100.0
    assert fit.coefficient_snr[1] < subject.MINIMUM_COEFFICIENT_SNR


def test_two_source_nonzero_dd_is_recovered_with_unequal_amplitudes() -> None:
    rng = np.random.default_rng(9911)
    design0 = _correlated_design(rng, count=160, coherence=0.65)
    sample = np.arange(len(design0))
    design1 = design0 * np.exp(2j * np.pi * 0.07 * sample / len(sample))[:, None]
    beta0 = np.asarray((4.0 * np.exp(0.2j), 1.8 * np.exp(-0.7j)))
    beta1 = np.asarray((2.5 * np.exp(0.9j), 5.0 * np.exp(1.4j)))
    expected = (beta1[1] * np.conj(beta1[0])) * np.conj(beta0[1] * np.conj(beta0[0]))
    recovered: list[complex] = []
    for _ in range(600):
        noise0 = 1.2 * (rng.normal(size=len(sample)) + 1j * rng.normal(size=len(sample)))
        noise1 = 0.7 * (rng.normal(size=len(sample)) + 1j * rng.normal(size=len(sample)))
        fit0 = subject.joint_complex_fit(design0 @ beta0 + noise0, design0)
        fit1 = subject.joint_complex_fit(design1 @ beta1 + noise1, design1)
        recovered.append(subject.covariance_corrected_dd(fit0, fit1)["corrected_phasor"])

    assert _phase_error_deg(complex(np.sum(recovered)), expected) < 2.0


def test_correlated_receiver_residual_is_exposed_by_diagnostic() -> None:
    rng = np.random.default_rng(41)
    count = 512
    common = rng.normal(size=count) + 1j * rng.normal(size=count)
    residual0 = common + 0.2 * (rng.normal(size=count) + 1j * rng.normal(size=count))
    residual1 = 0.8 * common + 0.2 * (rng.normal(size=count) + 1j * rng.normal(size=count))
    dummy = subject.ComplexFit(
        coefficients=(0j, 0j),
        coefficient_covariance=np.eye(2, dtype=np.complex128),
        residual=residual0,
        residual_variance=1.0,
        explained_power=0.0,
        residual_power=float(np.vdot(residual0, residual0).real),
        coefficient_snr=(0.0, 0.0),
    )
    paired = subject.ComplexFit(
        coefficients=(0j, 0j),
        coefficient_covariance=np.eye(2, dtype=np.complex128),
        residual=residual1,
        residual_variance=1.0,
        explained_power=0.0,
        residual_power=float(np.vdot(residual1, residual1).real),
        coefficient_snr=(0.0, 0.0),
    )
    coherence = subject._residual_cross_receiver_coherence(
        dummy,
        paired,
        np.arange(count),
        receiver_offset_hz=0.0,
        sample_rate_hz=1.0,
        reference_sample=0.0,
    )
    assert coherence > 0.8
    assert coherence > subject.MAXIMUM_CROSS_RECEIVER_RESIDUAL_COHERENCE


def test_correlated_receiver_noise_is_not_removed_by_within_receiver_correction() -> None:
    rng = np.random.default_rng(123)
    design = _correlated_design(rng, coherence=0.5)
    corrected: list[complex] = []
    for _ in range(1_000):
        noise0 = rng.normal(size=len(design)) + 1j * rng.normal(size=len(design))
        independent = rng.normal(size=len(design)) + 1j * rng.normal(size=len(design))
        noise1 = 0.7 * noise0 + np.sqrt(1.0 - 0.7**2) * independent
        fit0 = subject.joint_complex_fit(noise0, design)
        fit1 = subject.joint_complex_fit(noise1, design)
        corrected.append(subject.covariance_corrected_dd(fit0, fit1)["corrected_phasor"])

    assert complex(np.mean(corrected)).real > 0.0001


def test_bootstrap_reports_error_interval_relative_to_nominal_phase() -> None:
    rng = np.random.default_rng(55)
    phasors = np.exp(1j * (0.7 + rng.normal(scale=0.08, size=20)))
    result = subject._paired_frame_bootstrap(phasors, seed=9, draws=500)
    low, high = result["conditional_iid_frame_95_error_interval_deg"]
    assert low < 0 < high
    assert result["conditional_iid_frame_phase_standard_error_deg"] < 3.0
    adjacent_low, adjacent_high = result["conditional_adjacent_pair_95_error_interval_deg"]
    assert adjacent_low < 0 < adjacent_high


def _qin_fixture() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rate = 2_500_000.0
    exact = np.asarray(subject.qin_edge_pilot_frame(int(rate), "lower"), np.complex128)
    control = np.asarray(
        subject.qin_edge_pilot_frame(int(rate), "lower", symbol_roll=subject.CONTROL_SYMBOL_ROLL),
        np.complex128,
    )
    starts = (1_200, 1_420)
    frequencies = (385_250.0, 420_000.0)
    receiver_offset = -676_500.0
    samples, design0, design1 = subject.common_designs(
        (exact, exact),
        starts,
        frequencies,
        receiver_offset,
        rate,
        common_reference_sample=8_000.0,
    )
    _, control0, control1 = subject.common_designs(
        (control, control),
        starts,
        frequencies,
        receiver_offset,
        rate,
        common_reference_sample=8_000.0,
    )
    return samples, design0, design1, control0, control1


def test_qin_common_support_recovers_nonzero_dd_and_rejects_symbol_roll() -> None:
    rng = np.random.default_rng(73)
    samples, design0, design1, control0, control1 = _qin_fixture()
    beta0 = np.asarray((3.0 * np.exp(0.2j), 2.0 * np.exp(-0.5j)))
    beta1 = np.asarray((2.5 * np.exp(0.8j), 3.5 * np.exp(1.1j)))
    expected = (beta1[1] * np.conj(beta1[0])) * np.conj(beta0[1] * np.conj(beta0[0]))
    iq = np.zeros((int(samples[-1] + 2), 2), np.complex128)
    iq[samples, 0] = design0 @ beta0 + 0.3 * (
        rng.normal(size=len(samples)) + 1j * rng.normal(size=len(samples))
    )
    iq[samples, 1] = design1 @ beta1 + 0.3 * (
        rng.normal(size=len(samples)) + 1j * rng.normal(size=len(samples))
    )
    row = subject.analyze_frame(
        iq,
        samples,
        (design0, design1),
        (control0, control1),
        receiver_offset_hz=-676_500.0,
        sample_rate_hz=2_500_000.0,
        common_reference_sample=8_000.0,
    )
    assert row["qualified"] is True
    assert _phase_error_deg(np.exp(1j * np.radians(row["corrected_phase_deg"])), expected) < 1.0
    assert row["exact_to_control_explained_ratio"] > 100.0


def test_qin_one_source_only_does_not_qualify() -> None:
    rng = np.random.default_rng(91)
    samples, design0, design1, control0, control1 = _qin_fixture()
    iq = np.zeros((int(samples[-1] + 2), 2), np.complex128)
    iq[samples, 0] = 4.0 * design0[:, 0] + 0.8 * (
        rng.normal(size=len(samples)) + 1j * rng.normal(size=len(samples))
    )
    iq[samples, 1] = 3.0 * design1[:, 0] + 0.8 * (
        rng.normal(size=len(samples)) + 1j * rng.normal(size=len(samples))
    )
    row = subject.analyze_frame(
        iq,
        samples,
        (design0, design1),
        (control0, control1),
        receiver_offset_hz=-676_500.0,
        sample_rate_hz=2_500_000.0,
        common_reference_sample=8_000.0,
    )
    assert row["qualified"] is False
    assert row["minimum_coefficient_snr"] < subject.MINIMUM_COEFFICIENT_SNR
