"""Materialize the frozen lag-3 proposal challenge set without detector evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[2]
sys.path.insert(0, str(REPOSITORY / "src"))

from leo.analysis.starlink.templates import qin_edge_pilot_frame, template_sha256  # noqa: E402

DESIGN_PATH = HERE / "design.json"
LOCK_PATH = HERE / "source_lock.json"
DWELL_MS = 120
NOISE_COMPONENT_SIGMA = 520.0
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
    actual = {
        "design.json": sha256_file(DESIGN_PATH),
        "build_controls.py": sha256_file(Path(__file__)),
        "src/leo/analysis/starlink/templates.py": sha256_file(
            REPOSITORY / "src/leo/analysis/starlink/templates.py"
        ),
    }
    if lock.get("files") != actual:
        raise ValueError(f"source lock mismatch: expected {lock.get('files')!r}, got {actual!r}")
    return lock


def nearest_integer(value: Fraction) -> int:
    """Round to nearest integer with halves away from negative infinity."""

    return math.floor(value + Fraction(1, 2))


def signed_epoch(value: Fraction) -> tuple[int, float]:
    integer = nearest_integer(value)
    return integer, float(value - integer)


def absolute_oscillator(
    count: int,
    rate_hz: int,
    frequency_hz: float,
    source_start_counter: int,
    phase_cycles_at_counter_zero: float,
) -> np.ndarray:
    """Generate a continuous oscillator after reducing its large absolute phase."""

    start_cycles = np.remainder(
        np.longdouble(str(phase_cycles_at_counter_zero))
        + np.longdouble(str(frequency_hz))
        * np.longdouble(source_start_counter)
        / np.longdouble(rate_hz),
        np.longdouble(1.0),
    )
    relative = np.arange(count, dtype=np.float64) * (frequency_hz / rate_hz)
    return np.exp(2j * np.pi * (float(start_cycles) + relative))


def fractional_shift(template: np.ndarray, delay_samples: Fraction) -> np.ndarray:
    """Bandlimited shift of a zero-guarded canonical frame."""

    delay = float(delay_samples)
    if delay == 0.0:
        return np.asarray(template, dtype=np.complex128)
    required = len(template) + 2 * FRACTIONAL_SHIFT_GUARD
    fft_length = 1 << (required - 1).bit_length()
    padded = np.zeros(fft_length, dtype=np.complex128)
    start = FRACTIONAL_SHIFT_GUARD
    padded[start : start + len(template)] = template
    shifted = np.fft.ifft(
        np.fft.fft(padded)
        * np.exp(-2j * np.pi * np.fft.fftfreq(fft_length) * delay)
    )
    return shifted[start : start + len(template)]


def pilot_train(
    count: int,
    rate_hz: int,
    edge: str,
    epoch_relative: Fraction,
) -> tuple[np.ndarray, dict]:
    template = np.asarray(qin_edge_pilot_frame(rate_hz, edge), dtype=np.complex128)
    period = Fraction(rate_hz, 750)
    output = np.zeros(count, dtype=np.complex128)
    delays: dict[Fraction, np.ndarray] = {}
    frame_coordinates: list[dict] = []
    frame_limit = math.ceil(count / float(period)) + 3
    for frame_index in range(-2, frame_limit):
        physical_start = epoch_relative + frame_index * period
        insertion = nearest_integer(physical_start)
        delay = physical_start - insertion
        source_begin = max(0, -insertion)
        source_end = min(len(template), count - insertion)
        if source_end <= source_begin:
            continue
        shifted = delays.setdefault(delay, fractional_shift(template, delay))
        output[insertion + source_begin : insertion + source_end] += shifted[
            source_begin:source_end
        ]
        frame_coordinates.append(
            {
                "frame_index": frame_index,
                "physical_start_samples": float(physical_start),
                "nearest_sample": insertion,
                "fractional_delay_samples": float(delay),
            }
        )
    return output, {
        "template_sha256": "sha256:" + template_sha256(template),
        "template_samples": len(template),
        "frame_period_samples": float(period),
        "frame_coordinates": frame_coordinates,
    }


def expected_for_kind(kind: str) -> dict:
    if kind == "pilot":
        proposal, ambiguity, alias_free = True, "single", True
    elif kind in {"noise", "tone"}:
        proposal, ambiguity, alias_free = False, "invalid", False
    elif kind == "two_pilot":
        proposal, ambiguity, alias_free = None, "either", False
    elif kind == "pilot_tone":
        proposal, ambiguity, alias_free = None, "invalid", False
    else:
        raise ValueError(f"unknown kind {kind}")
    return {
        "expected_proposal_present": proposal,
        "ambiguity": ambiguity,
        "cfo_alias_free": alias_free,
        "cfo_tolerance_hz": 8000,
        "circular_timing_tolerance_s": 0.000002,
        "detector_positive_required": False,
    }


def build_receiver(spec: dict, receiver_model: dict, receiver: int) -> tuple[np.ndarray, dict]:
    rate = spec["rate_hz"]
    count = rate * DWELL_MS // 1000
    source_start = spec["source_start_counter"]
    seed = spec["seed"] + 1009 * receiver
    rng = np.random.default_rng(seed)
    noise_sigma = NOISE_COMPONENT_SIGMA * receiver_model["noise_scale"]
    values = noise_sigma * (
        rng.normal(size=count) + 1j * rng.normal(size=count)
    )
    channel = receiver_model["channel_amplitude"] * np.exp(
        2j * np.pi * receiver_model["channel_phase_cycles"]
    )
    truth_components: list[dict] = []
    component_powers: list[float] = []
    for component in spec["components"]:
        if component["type"] == "pilot":
            epoch = Fraction(str(spec["epoch_relative_samples"])) + Fraction(
                str(component.get("epoch_offset_samples", 0.0))
            )
            integer_epoch, fractional_epoch = signed_epoch(epoch)
            train, frame_meta = pilot_train(count, rate, spec["edge"], epoch)
            oscillator = absolute_oscillator(
                count,
                rate,
                component["cfo_hz"],
                source_start,
                component["phase_cycles_at_counter_zero"],
            )
            contribution = component["amplitude"] * channel * train * oscillator
            component_truth = {
                "type": "pilot",
                "trajectory_id": component.get("trajectory_id", "pilot"),
                "edge": spec["edge"],
                "cfo_hz": component["cfo_hz"],
                "epoch_origin": "relative to source_start_counter at frame_index=0",
                "epoch_relative_samples": float(epoch),
                "integer_epoch_samples": integer_epoch,
                "fractional_epoch_samples": fractional_epoch,
                "amplitude_before_channel": component["amplitude"],
                "amplitude_after_channel": (
                    component["amplitude"] * receiver_model["channel_amplitude"]
                ),
                "phase_cycles_at_counter_zero": component[
                    "phase_cycles_at_counter_zero"
                ],
                **frame_meta,
            }
        elif component["type"] == "tone":
            oscillator = absolute_oscillator(
                count,
                rate,
                component["frequency_hz"],
                source_start,
                component["phase_cycles_at_counter_zero"],
            )
            contribution = component["amplitude"] * channel * oscillator
            component_truth = {
                "type": "tone",
                "trajectory_id": component.get("trajectory_id", "tone"),
                "frequency_hz": component["frequency_hz"],
                "amplitude_before_channel": component["amplitude"],
                "amplitude_after_channel": (
                    component["amplitude"] * receiver_model["channel_amplitude"]
                ),
                "phase_cycles_at_counter_zero": component[
                    "phase_cycles_at_counter_zero"
                ],
            }
        else:
            raise ValueError(f"unknown component type {component['type']}")
        values += contribution
        power = float(np.mean(np.abs(contribution) ** 2))
        component_powers.append(power)
        component_truth["mean_power_before_quantization"] = power
        component_truth["power_over_noise_db"] = 10 * math.log10(
            power / (2 * noise_sigma**2)
        )
        truth_components.append(component_truth)

    components = np.rint(np.column_stack((values.real, values.imag)))
    clipped = int(np.count_nonzero((components < -32768) | (components > 32767)))
    quantized = np.clip(components, -32768, 32767).astype("<i2")
    truth = {
        "receiver": receiver,
        "noise_seed": seed,
        "noise_component_sigma": noise_sigma,
        "noise_complex_mean_power": 2 * noise_sigma**2,
        "channel": {
            "model": "flat_complex_scalar",
            "amplitude": receiver_model["channel_amplitude"],
            "phase_cycles": receiver_model["channel_phase_cycles"],
        },
        "components": truth_components,
        "prequantization_peak_component": float(np.max(np.abs(components))),
        "clipped_components": clipped,
        "quantizer": {
            "rounding": "numpy.rint ties-to-even",
            "minimum": -32768,
            "maximum": 32767,
        },
    }
    return quantized, truth


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
        "path": path.relative_to(HERE).as_posix(),
        "dtype": values.dtype.str,
        "shape": list(values.shape),
        "sha256": digest,
        "bytes": path.stat().st_size,
    }


def build() -> dict:
    lock = verify_source_lock()
    design = load_json(DESIGN_PATH)
    models = {model["receiver"]: model for model in design["receiver_model"]}
    cases = []
    for spec in design["cases"]:
        receivers, truths = zip(
            *(
                build_receiver(spec, models[receiver], receiver)
                for receiver in range(2)
            ),
            strict=True,
        )
        iq = np.stack(receivers, axis=1)
        raw = save_npy(HERE / "iq" / f"{spec['case_id']}.npy", iq)
        pilot_components = [
            component
            for receiver_truth in truths
            for component in receiver_truth["components"]
            if component["type"] == "pilot"
        ]
        cases.append(
            {
                "case_id": spec["case_id"],
                "origin": "synthetic_proposal_control",
                "split": "control",
                "cohort": "lag3_adversarial_v1",
                "rate_hz": spec["rate_hz"],
                "dwell_ms": DWELL_MS,
                "edge": spec["edge"],
                "channel": 1,
                "session_id": None,
                "visit_index": None,
                "source_start_counter": spec["source_start_counter"],
                "source_end_counter_exclusive": (
                    spec["source_start_counter"] + spec["rate_hz"] * DWELL_MS // 1000
                ),
                "truth_status": "constructed_proposal_control",
                "injected": {
                    "kind": spec["kind"],
                    "pilot_present": bool(pilot_components),
                    "receivers": list(truths),
                },
                "expected": expected_for_kind(spec["kind"]),
                "raw_npy": raw,
                "source": {
                    "generator": "build_controls.py/v1",
                    "design_sha256": lock["files"]["design.json"],
                    "generator_sha256": lock["files"]["build_controls.py"],
                    "template_source_sha256": lock["files"][
                        "src/leo/analysis/starlink/templates.py"
                    ],
                    "seed_base": spec["seed"],
                },
            }
        )
    total_bytes = sum(case["raw_npy"]["bytes"] for case in cases)
    if len(cases) > 24 or total_bytes > 100_000_000:
        raise ValueError("bounded challenge-set size exceeded")
    return {
        "schema": "org.leo.research.lag3-proposal-controls/v1",
        "status": "frozen_no_detector_outcomes",
        "design_sha256": lock["files"]["design.json"],
        "generator_sha256": lock["files"]["build_controls.py"],
        "template_source_sha256": lock["files"][
            "src/leo/analysis/starlink/templates.py"
        ],
        "layout": "sample_receiver_iq",
        "dtype": "<i2",
        "case_count": len(cases),
        "receiver_case_count": 2 * len(cases),
        "iq_bytes": total_bytes,
        "limitations": [
            "Pilot controls contain the published Qin edge pilots but no unknown QAM/data subcarriers.",
            "Receiver channels are flat complex scalars; frequency-selective and time-varying channels are absent.",
            "Truth describes injected proposal hypotheses and does not require a detector-positive decision at any SNR.",
            "The pilot-plus-tone case has no required dominant identity; the two-pilot case accepts either injected trajectory.",
        ],
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=HERE / "cases.json")
    args = parser.parse_args()
    payload = build()
    output = args.output.resolve()
    if output.parent != HERE:
        raise ValueError("output must remain in the lag3_controls directory")
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, output)
    print(
        json.dumps(
            {
                "cases": payload["case_count"],
                "iq_bytes": payload["iq_bytes"],
                "cases_sha256": sha256_file(output),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
