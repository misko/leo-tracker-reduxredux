"""Build the frozen TG11 diagnostic IQ without evaluating a detector."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import signal
import sys
import time
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
REPOSITORY = HERE.parents[3]
sys.path.insert(0, str(REPOSITORY / "src"))

from leo.analysis.starlink.templates import qin_edge_pilot_frame, template_sha256  # noqa: E402

DESIGN_PATH = HERE / "design.json"
LOCK_PATH = HERE / "source_lock.json"
PLAN_PATH = REPORT / "DATASET_PLAN.md"
TEMPLATE_SOURCE = REPOSITORY / "src/leo/analysis/starlink/templates.py"
DWELL_MS = 120
FRACTIONAL_SHIFT_GUARD = 64


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def verify_source_lock() -> dict:
    lock = load_json(LOCK_PATH)
    paths = {
        "design.json": DESIGN_PATH,
        "build_dataset.py": Path(__file__),
        "test_tg11_diagnostic_dataset.py": HERE / "test_tg11_diagnostic_dataset.py",
        "../DATASET_PLAN.md": PLAN_PATH,
        "src/leo/analysis/starlink/templates.py": TEMPLATE_SOURCE,
    }
    actual = {name: sha256_file(path) for name, path in paths.items()}
    if lock.get("files") != actual:
        raise ValueError(f"source lock mismatch: expected {lock.get('files')!r}, got {actual!r}")
    return lock


def nearest_integer(value: Fraction) -> int:
    return math.floor(value + Fraction(1, 2))


def signed_epoch(value: Fraction) -> tuple[int, float]:
    integer = nearest_integer(value)
    return integer, float(value - integer)


def cycles(value: Fraction | float | str) -> Fraction:
    return Fraction(str(value)) % 1


def advance_phase(phase: Fraction, cfo_hz: float, count: int, rate: int) -> Fraction:
    return (phase + Fraction(str(cfo_hz)) * count / rate) % 1


def oscillator(count: int, rate: int, frequency_hz: float, phase_at_start: float) -> np.ndarray:
    relative = np.arange(count, dtype=np.float64) * (frequency_hz / rate)
    return np.exp(2j * np.pi * (phase_at_start + relative))


def fractional_shift(template: np.ndarray, delay_samples: Fraction) -> np.ndarray:
    delay = float(delay_samples)
    if delay == 0.0:
        return np.asarray(template, dtype=np.complex128)
    required = len(template) + 2 * FRACTIONAL_SHIFT_GUARD
    fft_length = 1 << (required - 1).bit_length()
    padded = np.zeros(fft_length, dtype=np.complex128)
    start = FRACTIONAL_SHIFT_GUARD
    padded[start : start + len(template)] = template
    shifted = np.fft.ifft(
        np.fft.fft(padded) * np.exp(-2j * np.pi * np.fft.fftfreq(fft_length) * delay)
    )
    return shifted[start : start + len(template)]


@lru_cache(maxsize=None)
def canonical_template(rate: int, edge: str, region: str) -> np.ndarray:
    template = np.asarray(qin_edge_pilot_frame(rate, edge), dtype=np.complex128).copy()
    if region != "full":
        start_symbol, stop_symbol = (2, 66) if region == "early" else (152, 216)
        begin = round(start_symbol * rate * 4.4e-6)
        end = round(stop_symbol * rate * 4.4e-6)
        masked = np.zeros_like(template)
        masked[begin:min(end, len(template))] = template[begin:min(end, len(template))]
        template = masked
    template.flags.writeable = False
    return template


def pilot_geometry(
    count: int, rate: int, edge: str, epoch: Fraction, region: str, *, build: bool
) -> tuple[np.ndarray | None, dict, float]:
    template = canonical_template(rate, edge, region)
    full_template = canonical_template(rate, edge, "full")
    period = Fraction(rate, 750)
    # A rounded 5 MS/s lattice can overlap adjacent fixed-length templates by
    # one sample. Form the temporary unit train even for metadata so analytic
    # power includes that exact cross term; validation dual-RX IQ/noise is still
    # neither generated nor persisted.
    working = np.zeros(count, dtype=np.complex128)
    delays: dict[Fraction, np.ndarray] = {}
    coordinates: list[dict] = []
    frame_limit = math.ceil(count / float(period)) + 3
    for frame_index in range(-2, frame_limit):
        physical = epoch + frame_index * period
        insertion = nearest_integer(physical)
        delay = physical - insertion
        source_begin = max(0, -insertion)
        source_end = min(len(template), count - insertion)
        if source_end <= source_begin:
            continue
        if delay not in delays:
            delays[delay] = fractional_shift(template, delay)
        shifted = delays[delay]
        target_begin = insertion + source_begin
        target_end = insertion + source_end
        segment = shifted[source_begin:source_end]
        working[target_begin:target_end] += segment
        coordinates.append(
            {
                "frame_index": frame_index,
                "physical_start_samples": float(physical),
                "nearest_sample": insertion,
                "fractional_delay_samples": float(delay),
            }
        )
    integer, fraction = signed_epoch(epoch)
    metadata = {
        "epoch_origin": "relative to source_start_counter at frame_index=0",
        "epoch_relative_samples": float(epoch),
        "integer_epoch_samples": integer,
        "fractional_epoch_samples": fraction,
        "frame_period_samples": float(period),
        "frame_coordinates": coordinates,
        "symbol_region": region,
        "supported_symbol_range": [2, 302] if region == "full" else (
            [2, 66] if region == "early" else [152, 216]
        ),
        "template_sha256": "sha256:" + template_sha256(full_template),
        "masked_template_sha256": "sha256:" + template_sha256(template),
        "template_samples": len(template),
    }
    power = float(np.vdot(working, working).real) / count
    return working if build else None, metadata, power


def region_mask(count: int, rate: int, epoch: Fraction, region: str) -> tuple[np.ndarray, list[list[int]]]:
    start_symbol, stop_symbol = (2, 66) if region == "early" else (152, 216)
    period = Fraction(rate, 750)
    begin_offset = round(start_symbol * rate * 4.4e-6)
    stop_offset = round(stop_symbol * rate * 4.4e-6)
    mask = np.zeros(count, dtype=bool)
    intervals = []
    for frame in range(-2, math.ceil(count / float(period)) + 3):
        insertion = nearest_integer(epoch + frame * period)
        begin = max(0, insertion + begin_offset)
        stop = min(count, insertion + stop_offset)
        if stop > begin:
            mask[begin:stop] = True
            intervals.append([begin, stop])
    return mask, intervals


def pilot_component(
    trajectory: str,
    target_db: float,
    cfo: float,
    epoch: float,
    phase: float,
    *,
    region: str = "full",
) -> dict:
    return {
        "type": "pilot",
        "trajectory_id": trajectory,
        "target_power_over_noise_db": target_db,
        "cfo_hz": cfo,
        "epoch_samples": epoch,
        "phase_cycles_at_visit_start": float(cycles(phase)),
        "symbol_region": region,
    }


def tone_component(
    trajectory: str,
    target_db: float,
    frequencies: list[float],
    phases: list[float],
    weights: list[float],
    *,
    region: str = "full",
    epoch: float | None = None,
) -> dict:
    return {
        "type": "tone" if len(frequencies) == 1 else "multitone",
        "trajectory_id": trajectory,
        "target_power_over_noise_db": target_db,
        "frequencies_hz": frequencies,
        "phase_cycles_at_visit_start": [float(cycles(value)) for value in phases],
        "relative_amplitudes": weights,
        "symbol_region": region,
        "epoch_samples": epoch,
    }


def enumerate_specs(design: dict) -> list[dict]:
    specs: list[dict] = []
    stationary = design["stationary"]
    sequence = design["sequence"]
    sigma = float(design["noise_component_sigma"])
    del sigma  # The exact value remains in each receiver specification below.
    for split_index, split in enumerate(design["splits"]):
        for rate in design["rates_hz"]:
            count = rate * DWELL_MS // 1000
            base = int(design["source_counter_base"][f"{split}:{rate}"])
            rate_index = int(design["rate_index"][str(rate)])
            seed_base = int(design["split_seed_base"][split]) + rate_index * 100000
            ladder = design["ladder"][f"{split}:{rate}"]

            def case(ordinal: int, cohort: str, edge: str, receivers: list[dict], *, sequence_id=None):
                case_id = f"tg11diag-{'dev' if split == 'development' else 'val'}-r{rate}-{cohort}-{ordinal:02d}"
                specs.append(
                    {
                        "case_id": case_id,
                        "split": split,
                        "cohort": cohort,
                        "rate_hz": rate,
                        "edge": edge,
                        "channel": int(sequence["channel"]),
                        "source_start_counter": base + ordinal * count,
                        "session_id": (
                            f"tg11diag:{split}:r{rate}:sequence" if sequence_id else f"tg11diag:{case_id}"
                        ),
                        "tuning_identity": (
                            f"tg11diag:{split}:r{rate}:sequence:{edge}:ch{sequence['channel']}"
                            if sequence_id else f"tg11diag:{case_id}:{edge}:ch{sequence['channel']}"
                        ),
                        "sequence_id": sequence_id,
                        "sequence_index": ordinal - 9 if sequence_id else None,
                        "receivers": receivers,
                    }
                )

            for ordinal, targets in enumerate(design["ladder_target_power_over_noise_db_by_receiver"]):
                receivers = []
                for receiver, target in enumerate(targets):
                    receivers.append(
                        {
                            "noise_model": "white",
                            "noise_seed": seed_base + ordinal * 10 + receiver,
                            "noise_component_sigma": design["noise_component_sigma"],
                            "components": [
                                pilot_component(
                                    "pilot", float(target), float(ladder["cfo_hz"][ordinal]),
                                    float(ladder["epoch_samples"][ordinal]),
                                    float(ladder["phase_cycles_at_visit_start"][ordinal]) + receiver / 16,
                                )
                            ],
                        }
                    )
                case(ordinal, "ladder", "lower" if ordinal % 2 == 0 else "upper", receivers)

            period = rate / 750.0
            pilot_epoch = period * float(stationary["pilot_epoch_fraction_of_period"])
            split_sign = 1.0 if split == "development" else -1.0
            rate_sign = 1.0 if rate == 2_500_000 else -1.0
            phase_offset = 0.0 if split == "development" else float(
                stationary["validation_phase_offset_cycles"]
            )
            pilot_cfo = split_sign * rate_sign * float(stationary["pilot_cfo_hz"])
            tone_phase = float(cycles(
                float(stationary["tone_phase_cycles_at_visit_start"]) + phase_offset
            ))
            multi_freqs = [float(value) for value in stationary["multitone_frequencies_hz"]]
            multi_weights = [float(value) for value in stationary["multitone_relative_amplitudes"]]
            multi_phases = [tone_phase + index * float(stationary["multitone_phase_step_cycles"])
                            for index in range(len(multi_freqs))]

            negative_receivers = [
                {"noise_model": "white", "noise_seed": seed_base + 40,
                 "noise_component_sigma": design["noise_component_sigma"], "components": []},
                {"noise_model": "colored_ar1", "noise_seed": seed_base + 41,
                 "noise_component_sigma": design["noise_component_sigma"], "components": []},
            ]
            case(4, "negative-noise", "lower", negative_receivers)

            nuisance_receivers = [
                {"noise_model": "white", "noise_seed": seed_base + 50,
                 "noise_component_sigma": design["noise_component_sigma"],
                 "components": [tone_component("tone", stationary["nuisance_power_over_noise_db"],
                    [stationary["single_tone_frequency_hz"]], [tone_phase], [1.0])]},
                {"noise_model": "white", "noise_seed": seed_base + 51,
                 "noise_component_sigma": design["noise_component_sigma"],
                 "components": [tone_component("multitone", stationary["nuisance_power_over_noise_db"],
                    multi_freqs, multi_phases, multi_weights)]},
            ]
            case(5, "negative-nuisance", "upper", nuisance_receivers)

            ambiguity_receivers = [
                {"noise_model": "white", "noise_seed": seed_base + 60,
                 "noise_component_sigma": design["noise_component_sigma"], "components": [
                    pilot_component("pilot-a", stationary["two_pilot_power_over_noise_db_each"],
                                    -145250.25 * split_sign, pilot_epoch, 0.078125 + phase_offset),
                    pilot_component("pilot-b", stationary["two_pilot_power_over_noise_db_each"],
                                    stationary["second_pilot_cfo_hz"] * split_sign,
                                    pilot_epoch + rate * stationary["second_pilot_epoch_offset_seconds"],
                                    stationary["second_pilot_phase_cycles_at_visit_start"] + phase_offset),
                 ]},
                {"noise_model": "white", "noise_seed": seed_base + 61,
                 "noise_component_sigma": design["noise_component_sigma"], "components": [
                    pilot_component("pilot", stationary["pilot_power_over_noise_db"], pilot_cfo,
                                    pilot_epoch, stationary["pilot_phase_cycles_at_visit_start"] + phase_offset),
                    tone_component("multitone", stationary["nuisance_power_over_noise_db"],
                                   multi_freqs, multi_phases, multi_weights),
                 ]},
            ]
            case(6, "multiple-hypothesis", "lower", ambiguity_receivers)

            region_receivers = [
                {"noise_model": "white", "noise_seed": seed_base + 70,
                 "noise_component_sigma": design["noise_component_sigma"], "components": [
                    pilot_component("early-pilot", stationary["pilot_power_over_noise_db"],
                                    pilot_cfo, pilot_epoch, 0.1484375 + phase_offset,
                                    region="early")
                 ]},
                {"noise_model": "white", "noise_seed": seed_base + 71,
                 "noise_component_sigma": design["noise_component_sigma"], "components": [
                    pilot_component("late-pilot", stationary["pilot_power_over_noise_db"],
                                    pilot_cfo, pilot_epoch, -0.203125 + phase_offset,
                                    region="late")
                 ]},
            ]
            case(7, "symbol-region-support", "upper", region_receivers)

            burst_receivers = [
                {"noise_model": "white", "noise_seed": seed_base + 80,
                 "noise_component_sigma": design["noise_component_sigma"], "components": [
                    pilot_component("pilot", stationary["pilot_power_over_noise_db"], pilot_cfo,
                                    pilot_epoch, 0.2265625 + phase_offset),
                    tone_component("early-burst", stationary["nuisance_power_over_noise_db"],
                                   [stationary["single_tone_frequency_hz"]], [tone_phase], [1.0],
                                   region="early", epoch=pilot_epoch),
                 ]},
                {"noise_model": "white", "noise_seed": seed_base + 81,
                 "noise_component_sigma": design["noise_component_sigma"], "components": [
                    pilot_component("pilot", stationary["pilot_power_over_noise_db"], pilot_cfo,
                                    pilot_epoch, -0.2421875 + phase_offset),
                    tone_component("late-burst", stationary["nuisance_power_over_noise_db"],
                                   multi_freqs, multi_phases, multi_weights,
                                   region="late", epoch=pilot_epoch),
                 ]},
            ]
            case(8, "symbol-region-interference", "lower", burst_receivers)

            seq_edge = design["sequence"]["edge_by_cell"][f"{split}:{rate}"]
            rx0_epoch = period * float(sequence["rx0_initial_epoch_fraction_of_period"][split])
            rx1_epoch = period * float(sequence["rx1_initial_epoch_fraction_of_period"][split])
            rx0_cfo = split_sign * float(sequence["rx0_initial_cfo_hz"])
            rx1_cfo = split_sign * float(sequence["rx1_initial_cfo_hz"])
            rx0_phase0 = cycles(sequence["rx0_initial_phase_cycles_at_visit_start"][split])
            rx0_phase1 = advance_phase(rx0_phase0, rx0_cfo, count, rate)
            rx1_cfo1 = rx1_cfo + split_sign * float(sequence["rx1_per_visit_cfo_drift_hz"])
            rx1_phase0 = cycles(sequence["rx1_initial_phase_cycles_at_visit_start"][split])
            rx1_phase1 = advance_phase(rx1_phase0, rx1_cfo, count, rate)
            rx1_cfo2 = rx1_cfo + split_sign * float(sequence["rx1_replacement_cfo_jump_hz"])
            rx1_phase2_b = cycles(sequence["rx1_replacement_phase_cycles_at_visit_start"][split])
            rx1_phase3_b = advance_phase(rx1_phase2_b, rx1_cfo2, count, rate)
            rx1_cfo3_a = rx1_cfo + 3 * split_sign * float(sequence["rx1_per_visit_cfo_drift_hz"])
            rx1_phase3_a = advance_phase(
                advance_phase(rx1_phase1, rx1_cfo1, count, rate),
                rx1_cfo + 2 * split_sign * float(sequence["rx1_per_visit_cfo_drift_hz"]),
                count, rate,
            )
            jump_rx0 = rate * float(sequence["rx0_replacement_timing_jump_s"])
            jump_rx1 = rate * float(sequence["rx1_replacement_timing_jump_s"])
            drift = rate * float(sequence["rx1_per_visit_timing_drift_s"])
            rx0_b_cfo = rx0_cfo + split_sign * float(sequence["rx0_replacement_cfo_jump_hz"])
            rx1_b_epoch = rx1_epoch + jump_rx1
            seq_rx = [
                [
                    {"noise_model": "white", "noise_seed": seed_base + 90,
                     "noise_component_sigma": design["noise_component_sigma"], "components": [
                        pilot_component("pilot-a", sequence["strong_pilot_power_over_noise_db"],
                                        rx0_cfo, rx0_epoch, float(rx0_phase0))]},
                    {"noise_model": "white", "noise_seed": seed_base + 91,
                     "noise_component_sigma": design["noise_component_sigma"], "components": [
                        pilot_component("pilot-a", sequence["strong_pilot_power_over_noise_db"],
                                        rx1_cfo, rx1_epoch, float(rx1_phase0))]},
                ],
                [
                    {"noise_model": "white", "noise_seed": seed_base + 100,
                     "noise_component_sigma": design["noise_component_sigma"], "components": [
                        pilot_component("pilot-a", sequence["faded_pilot_power_over_noise_db"],
                                        rx0_cfo, rx0_epoch, float(rx0_phase1))]},
                    {"noise_model": "white", "noise_seed": seed_base + 101,
                     "noise_component_sigma": design["noise_component_sigma"], "components": [
                        pilot_component("pilot-a", sequence["strong_pilot_power_over_noise_db"],
                                        rx1_cfo1, rx1_epoch + drift, float(rx1_phase1))]},
                ],
                [
                    {"noise_model": "colored_ar1", "noise_seed": seed_base + 110,
                     "noise_component_sigma": design["noise_component_sigma"], "components": [
                        tone_component("dropout-multitone", stationary["nuisance_power_over_noise_db"],
                                       multi_freqs, multi_phases, multi_weights)]},
                    {"noise_model": "white", "noise_seed": seed_base + 111,
                     "noise_component_sigma": design["noise_component_sigma"], "components": [
                        pilot_component("pilot-b", sequence["strong_pilot_power_over_noise_db"],
                                        rx1_cfo2, rx1_b_epoch, float(rx1_phase2_b))]},
                ],
                [
                    {"noise_model": "white", "noise_seed": seed_base + 120,
                     "noise_component_sigma": design["noise_component_sigma"], "components": [
                        pilot_component("pilot-b", sequence["strong_pilot_power_over_noise_db"],
                                        rx0_b_cfo, rx0_epoch + jump_rx0,
                                        sequence["rx0_replacement_phase_cycles_at_visit_start"][split])]},
                    {"noise_model": "white", "noise_seed": seed_base + 121,
                     "noise_component_sigma": design["noise_component_sigma"], "components": [
                        pilot_component("pilot-a", sequence["ambiguous_pilot_power_over_noise_db_each"],
                                        rx1_cfo3_a, rx1_epoch + 3 * drift, float(rx1_phase3_a)),
                        pilot_component("pilot-b", sequence["ambiguous_pilot_power_over_noise_db_each"],
                                        rx1_cfo2, rx1_b_epoch, float(rx1_phase3_b)),
                     ]},
                ],
            ]
            for step, receivers in enumerate(seq_rx):
                case(9 + step, "causal-sequence", seq_edge, receivers,
                     sequence_id=f"{split}-r{rate}-causal")
    return specs


def white_noise(rng: np.random.Generator, count: int, sigma: float) -> np.ndarray:
    return sigma * (rng.normal(size=count) + 1j * rng.normal(size=count))


def colored_noise(rng: np.random.Generator, count: int, sigma: float, coefficient: float) -> np.ndarray:
    innovation = sigma * math.sqrt(1 - coefficient**2)
    real_in = rng.normal(scale=innovation, size=count)
    imag_in = rng.normal(scale=innovation, size=count)
    real = np.empty(count, dtype=np.float64)
    imag = np.empty(count, dtype=np.float64)
    real[0] = rng.normal(scale=sigma)
    imag[0] = rng.normal(scale=sigma)
    for index in range(1, count):
        real[index] = coefficient * real[index - 1] + real_in[index]
        imag[index] = coefficient * imag[index - 1] + imag_in[index]
    return real + 1j * imag


def component_metadata(component: dict, case: dict, receiver: int, design: dict) -> tuple[dict, float]:
    rate = case["rate_hz"]
    count = rate * DWELL_MS // 1000
    noise_power = 2 * float(design["noise_component_sigma"]) ** 2
    channel_phase = float(design["receiver_channel_phase_cycles"][receiver])
    if component["type"] == "pilot":
        epoch = Fraction(str(component["epoch_samples"]))
        _, geometry, unit_power = pilot_geometry(
            count, rate, case["edge"], epoch, component["symbol_region"], build=False
        )
        target_power = noise_power * 10 ** (component["target_power_over_noise_db"] / 10)
        amplitude = math.sqrt(target_power / unit_power)
        return ({
            **component,
            **geometry,
            "amplitude_before_channel": amplitude,
            "channel_phase_cycles": channel_phase,
            "nominal_mean_power_before_quantization": target_power,
            "nominal_power_over_noise_db": component["target_power_over_noise_db"],
        }, amplitude)
    weights = np.asarray(component["relative_amplitudes"], dtype=np.float64)
    target_active_power = noise_power * 10 ** (component["target_power_over_noise_db"] / 10)
    scale = math.sqrt(target_active_power / float(np.sum(weights**2)))
    intervals = None
    if component["symbol_region"] != "full":
        epoch = Fraction(str(component["epoch_samples"]))
        _, intervals = region_mask(count, rate, epoch, component["symbol_region"])
    return ({
        **component,
        "amplitudes_before_channel": [float(scale * value) for value in weights],
        "channel_phase_cycles": channel_phase,
        "nominal_active_mean_power_before_quantization": target_active_power,
        "nominal_active_power_over_noise_db": component["target_power_over_noise_db"],
        "active_sample_intervals": intervals,
    }, scale)


def build_receiver(case: dict, receiver: int, design: dict, *, materialize: bool) -> tuple[np.ndarray | None, dict]:
    spec = case["receivers"][receiver]
    rate = case["rate_hz"]
    count = rate * DWELL_MS // 1000
    sigma = float(spec["noise_component_sigma"])
    nominal_noise_power = 2 * sigma**2
    component_truth = []
    values = None
    measured_noise_power = None
    if materialize:
        rng = np.random.default_rng(int(spec["noise_seed"]))
        if spec["noise_model"] == "white":
            values = white_noise(rng, count, sigma)
        elif spec["noise_model"] == "colored_ar1":
            values = colored_noise(rng, count, sigma, float(design["colored_noise_ar1"]))
        else:
            raise ValueError("unknown noise model")
        measured_noise_power = float(np.mean(np.abs(values) ** 2))
    channel = np.exp(2j * np.pi * float(design["receiver_channel_phase_cycles"][receiver]))
    for component in spec["components"]:
        truth, amplitude = component_metadata(component, case, receiver, design)
        contribution = None
        if materialize:
            if component["type"] == "pilot":
                train, _, _ = pilot_geometry(
                    count, rate, case["edge"], Fraction(str(component["epoch_samples"])),
                    component["symbol_region"], build=True,
                )
                assert train is not None
                contribution = amplitude * channel * train * oscillator(
                    count, rate, component["cfo_hz"], component["phase_cycles_at_visit_start"]
                )
            else:
                contribution = np.zeros(count, dtype=np.complex128)
                for frequency, phase, weight in zip(
                    component["frequencies_hz"], component["phase_cycles_at_visit_start"],
                    component["relative_amplitudes"], strict=True,
                ):
                    contribution += amplitude * weight * oscillator(count, rate, frequency, phase)
                if component["symbol_region"] != "full":
                    mask, _ = region_mask(
                        count, rate, Fraction(str(component["epoch_samples"])),
                        component["symbol_region"],
                    )
                    contribution *= mask
                contribution *= channel
            assert values is not None
            values += contribution
            measured = float(np.mean(np.abs(contribution) ** 2))
            truth["measured_mean_power_before_quantization"] = measured
            truth["measured_power_over_nominal_noise_db"] = 10 * math.log10(measured / nominal_noise_power)
        component_truth.append(truth)
    receiver_truth = {
        "receiver": receiver,
        "noise_seed": int(spec["noise_seed"]),
        "noise_model": spec["noise_model"],
        "noise_component_sigma": sigma,
        "nominal_noise_complex_mean_power": nominal_noise_power,
        "colored_noise_ar1": (
            float(design["colored_noise_ar1"]) if spec["noise_model"] == "colored_ar1" else None
        ),
        "channel": {"model": "flat_unit_complex", "amplitude": 1.0,
                    "phase_cycles": float(design["receiver_channel_phase_cycles"][receiver])},
        "components": component_truth,
        "constructed_negative": not any(item["type"] == "pilot" for item in component_truth),
        "ambiguity": (
            "invalid" if not any(item["type"] == "pilot" for item in component_truth)
            else "either" if sum(item["type"] == "pilot" for item in component_truth) > 1
            else "single"
        ),
        "materialized": materialize,
    }
    if not materialize:
        return None, receiver_truth
    assert values is not None
    components = np.rint(np.column_stack((values.real, values.imag)))
    clipped = int(np.count_nonzero((components < -32768) | (components > 32767)))
    receiver_truth["measured_noise_complex_mean_power"] = measured_noise_power
    receiver_truth["prequantization_peak_component"] = float(np.max(np.abs(components)))
    receiver_truth["clipped_components"] = clipped
    if clipped:
        raise ValueError(f"CI16 clipping in {case['case_id']} RX{receiver}")
    quantized = np.clip(components, -32768, 32767).astype("<i2")
    return quantized, receiver_truth


def save_npy(path: Path, values: np.ndarray) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".npy.tmp")
    with temporary.open("wb") as stream:
        np.save(stream, values, allow_pickle=False)
    digest = sha256_file(temporary)
    if path.exists() and sha256_file(path) != digest:
        temporary.unlink()
        raise ValueError(f"existing IQ differs from frozen construction: {path}")
    if path.exists():
        temporary.unlink()
    else:
        os.replace(temporary, path)
    return {
        "path": path.relative_to(HERE).as_posix(), "dtype": values.dtype.str,
        "shape": list(values.shape), "sha256": digest, "bytes": path.stat().st_size,
        "materialized": True,
    }


def membership_sha256(specs: list[dict]) -> str:
    selected = [{key: case[key] for key in (
        "case_id", "split", "cohort", "rate_hz", "edge", "channel",
        "source_start_counter", "session_id", "tuning_identity", "sequence_id",
        "sequence_index", "receivers",
    )} for case in specs]
    encoded = json.dumps(selected, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def build() -> dict:
    started = time.monotonic()
    design = load_json(DESIGN_PATH)
    lock = verify_source_lock()
    specs = enumerate_specs(design)
    cases = []
    materialized_bytes = 0
    deadline = started + float(design["bounded"]["maximum_generation_seconds"])
    for spec in specs:
        if time.monotonic() >= deadline:
            raise TimeoutError("dataset generation exceeded its frozen wall-time bound")
        materialize = spec["split"] in design["materialize_splits"]
        built = [build_receiver(spec, receiver, design, materialize=materialize)
                 for receiver in range(2)]
        truths = [item[1] for item in built]
        count = spec["rate_hz"] * DWELL_MS // 1000
        path = HERE / "iq" / f"{spec['case_id']}.npy"
        if materialize:
            iq = np.stack([item[0] for item in built], axis=1)
            raw = save_npy(path, iq)
            materialized_bytes += raw["bytes"]
        else:
            raw = {
                "path": path.relative_to(HERE).as_posix(), "dtype": "<i2",
                "shape": [count, 2, 2], "sha256": None, "bytes": None,
                "materialized": False,
                "status": "reserved_until_candidate_freeze",
            }
        cases.append({
            **{key: spec[key] for key in (
                "case_id", "split", "cohort", "rate_hz", "edge", "channel",
                "source_start_counter", "session_id", "tuning_identity",
                "sequence_id", "sequence_index",
            )},
            "source_end_counter_exclusive": spec["source_start_counter"] + count,
            "dwell_ms": DWELL_MS,
            "origin": "constructed_tg11_diagnostic",
            "truth_status": "constructed_signal_components",
            "receivers": truths,
            "raw_npy": raw,
        })
        if time.monotonic() >= deadline:
            raise TimeoutError("dataset generation exceeded its frozen wall-time bound")
    elapsed = time.monotonic() - started
    if len(cases) != design["bounded"]["physical_cases"]:
        raise ValueError("case count changed")
    if materialized_bytes > design["bounded"]["maximum_materialized_bytes"]:
        raise ValueError("materialized size bound exceeded")
    if elapsed > design["bounded"]["maximum_generation_seconds"]:
        raise ValueError("generation duration bound exceeded")
    return {
        "schema": "org.leo.research.tg11-diagnostic-cases/v1",
        "status": "frozen_no_detector_outcomes_development_materialized_validation_reserved",
        "design_sha256": lock["files"]["design.json"],
        "generator_sha256": lock["files"]["build_dataset.py"],
        "source_lock_sha256": sha256_file(LOCK_PATH),
        "template_source_sha256": lock["files"]["src/leo/analysis/starlink/templates.py"],
        "membership_sha256": membership_sha256(specs),
        "array_layout": design["array_layout"],
        "dtype": design["dtype"],
        "case_count": len(cases),
        "receiver_case_count": 2 * len(cases),
        "materialized_splits": design["materialize_splits"],
        "validation_iq_opened": False,
        "materialized_case_count": sum(case["raw_npy"]["materialized"] for case in cases),
        "materialized_iq_bytes": materialized_bytes,
        "detector_outcomes_present": False,
        "limitations": [
            "Constructed truth does not establish field prevalence or adjudicate the recorded phase-one additional decision.",
            "Pilot fixtures contain canonical known-pilot samples but no unknown payload/QAM subcarriers.",
            "Validation membership and truth are frozen, but validation IQ is intentionally unmaterialized until candidate freeze.",
            "Partial early/late pilot regions are deliberate diagnostic controls, not complete Starlink downlink models."
        ],
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=HERE / "cases.json")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.parent != HERE:
        raise ValueError("output must remain in the dataset directory")
    if output.exists():
        raise FileExistsError(f"refusing to replace frozen manifest: {output}")
    if (HERE / "build_receipt.json").exists():
        raise FileExistsError("refusing to replace build receipt")
    limit = int(load_json(DESIGN_PATH)["bounded"]["maximum_generation_seconds"])

    def timeout_handler(_signum, _frame):
        raise TimeoutError("dataset generation exceeded its frozen wall-time bound")

    started = time.monotonic()
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(limit)
    try:
        payload = build()
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        os.replace(temporary, output)
        receipt = {
            "schema": "org.leo.research.tg11-diagnostic-build-receipt/v1",
            "status": "complete",
            "cases_sha256": sha256_file(output),
            "source_lock_sha256": sha256_file(LOCK_PATH),
            "case_count": payload["case_count"],
            "materialized_case_count": payload["materialized_case_count"],
            "materialized_iq_bytes": payload["materialized_iq_bytes"],
            "elapsed_seconds": time.monotonic() - started,
            "detector_evaluated": False,
            "validation_iq_opened": False,
        }
        receipt_path = HERE / "build_receipt.json"
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        print(json.dumps(receipt, sort_keys=True))
    except Exception as error:
        failure = {
            "schema": "org.leo.research.tg11-diagnostic-build-failure/v1",
            "status": "failed",
            "error_type": type(error).__name__,
            "error": str(error),
            "elapsed_seconds": time.monotonic() - started,
            "detector_evaluated": False,
            "validation_iq_opened": False,
        }
        (HERE / "build_failure.json").write_text(
            json.dumps(failure, indent=2, sort_keys=True) + "\n"
        )
        raise
    finally:
        signal.alarm(0)


if __name__ == "__main__":
    main()
