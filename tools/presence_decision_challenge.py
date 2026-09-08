"""Frozen, bounded whole-dwell detector challenges; no radio or runtime policy."""

from __future__ import annotations

import argparse
import hashlib
import json
from contextlib import ExitStack
from functools import lru_cache
from pathlib import Path

import numpy as np

from leo.analysis.starlink.templates import (
    CYCLIC_PREFIX_DURATION_S,
    FRAME_RATE_HZ,
    OFDM_SYMBOL_DURATION_S,
    edge_frequencies_hz,
    qin_edge_pilot_symbols,
)
from tools.native_presence import ROOT, build_dwell_presence
from tools.presence_dwell import NativeDwell, unpack
from tools.presence_fftw import fftw_identity, fftw_options
from tools.qualify_native_presence import digest, write_json

PROTOCOL = ROOT / "config/analysis/arm-presence-decision-challenge-v1.json"


@lru_cache(maxsize=4)
def continuous_pilot(rate: int, edge: str, epoch: float, roll: int = 0):
    """Evaluate the published symbol model at fractional frame-relative time.

    No per-frame integer rounding and no interpolation of the detector's own
    sampled template. All floating time here is local to a 120 ms synthetic
    dwell, never a uint64 device epoch. This is a pilot-only baseband model,
    not a receiver analog-filter or satellite propagation simulation.
    """
    if rate not in (2500000, 5000000) or edge not in ("lower", "upper"):
        raise ValueError("unsupported geometry")
    if not np.isfinite(epoch) or not 0 <= epoch < rate / FRAME_RATE_HZ:
        raise ValueError("epoch must be finite and within one frame")
    time = np.remainder((np.arange(rate * 120 // 1000) - epoch) / rate, 1 / FRAME_RATE_HZ)
    symbols = np.floor(time / OFDM_SYMBOL_DURATION_S).astype(int)
    use = (symbols >= 2) & (symbols < 302)
    local = time[use] - symbols[use] * OFDM_SYMBOL_DURATION_S - CYCLIC_PREFIX_DURATION_S
    states = qin_edge_pilot_symbols(edge, symbol_roll=roll)
    values = np.zeros(time.size, dtype=np.complex128)
    for column, frequency in enumerate(edge_frequencies_hz(edge)):
        values[use] += states[symbols[use] - 2, column] * np.exp(2j * np.pi * frequency * local)
    values /= np.sqrt(8)
    values.flags.writeable = False
    return values


def cases(protocol):
    for rate in protocol["rates_hz"]:
        for edge in protocol["edges"]:
            base = {"rate_hz": rate, "edge": edge}
            for seed in protocol["control_seeds"]:
                for kind in protocol["negative_kinds"]:
                    yield dict(base, seed=seed, kind=kind, start_ms=0.0, duration_ms=120.0)
            for seed in protocol["positive_seeds"]:
                for window in protocol["positive_windows"]:
                    for snr in protocol["positive_snr_db"]:
                        yield dict(base, seed=seed, kind="pilot", start_ms=window * 20.0,
                                   duration_ms=20.0, snr_db=snr)
                    yield dict(base, seed=seed, kind="pilot_plus_tone", start_ms=window * 20.0,
                               duration_ms=20.0, snr_db=protocol["pilot_plus_tone_snr_db"])
                for boundary in range(1, 6):
                    for snr in protocol["boundary_snr_db"]:
                        duration = protocol["boundary_burst_ms"]
                        yield dict(base, seed=seed, kind="boundary_pilot",
                                   start_ms=boundary * 20.0 - duration / 2,
                                   duration_ms=duration, snr_db=snr)


def generate(spec):
    rate, edge, seed = spec["rate_hz"], spec["edge"], spec["seed"]
    if rate not in (2500000, 5000000) or edge not in ("lower", "upper"):
        raise ValueError("unsupported geometry")
    count = rate * 120 // 1000
    start = round(spec["start_ms"] * rate / 1000)
    end = start + round(spec["duration_ms"] * rate / 1000)
    if not 0 <= start < end <= count:
        raise ValueError("signal interval outside dwell")
    kind = spec["kind"]
    positive = kind in ("pilot", "pilot_plus_tone", "boundary_pilot")
    known = {"white_noise", "colored_noise", "tone", "two_tones", "pulsed_tone",
             "chirp", "clipped_tones", "wrong_pilot"}
    if not positive and kind not in known:
        raise ValueError("unknown control")
    rng = np.random.default_rng(seed)
    time = np.arange(count) / rate
    sigma = 800.0
    values = sigma * (rng.normal(size=count) + 1j * rng.normal(size=count))
    frequency = rng.uniform(-420000, 420000)
    second = rng.uniform(-420000, 420000)
    phase = rng.uniform(-np.pi, np.pi)
    epoch = rng.uniform(128, 1000)
    if kind == "colored_noise":
        coefficients = np.hanning(17)
        coefficients /= np.linalg.norm(coefficients)
        values = np.convolve(values, coefficients, mode="same")
    if kind in ("tone", "two_tones", "pulsed_tone", "clipped_tones", "pilot_plus_tone"):
        envelope = (np.remainder(time * rng.uniform(600, 1100), 1) < rng.uniform(0.1, 0.9))
        if kind != "pulsed_tone":
            envelope = 1
        amplitude = 48000 if kind == "clipped_tones" else 8000
        values += amplitude * envelope * np.exp(1j * (2 * np.pi * frequency * time + phase))
    if kind in ("two_tones", "clipped_tones"):
        values += 6000 * np.exp(-2j * np.pi * second * time)
    if kind == "chirp":
        slope = rng.uniform(-2000000, 2000000)
        values += 8000 * np.exp(2j * np.pi * (frequency * time + 0.5 * slope * time**2))
    if positive or kind == "wrong_pilot":
        snr = spec.get("snr_db", 12.0)
        if not np.isfinite(snr) or not -30 <= snr <= 20:
            raise ValueError("SNR outside bounded challenge")
        pilot = continuous_pilot(rate, edge, epoch, 17 if kind == "wrong_pilot" else 0)[start:end]
        amplitude = np.sqrt(2 * sigma**2 * 10 ** (snr / 10) / np.mean(np.abs(pilot)**2))
        values[start:end] += amplitude * pilot * np.exp(2j * np.pi * frequency * time[start:end])
    components = np.rint(np.column_stack((values.real, values.imag)))
    truth = dict(spec, starlink_model_present=positive, epoch_samples=epoch, cfo_hz=frequency,
                 clipped_components=int(np.count_nonzero(
                     (components < -32768) | (components > 32767))))
    return np.clip(components, -32768, 32767).astype(np.int16), truth


def passing(candidates, policy):
    return [c for c in candidates if c["fractional_complete"]
            and c["exact_score"] >= policy["minimum_exact_score"]
            and c["margin"] >= policy["minimum_margin"]]


def associated(candidate, truth, window, limits):
    if not truth["starlink_model_present"]:
        return False
    rate = truth["rate_hz"]
    start, end = window * 20, (window + 1) * 20
    if end <= truth["start_ms"] or start >= truth["start_ms"] + truth["duration_ms"]:
        return False
    epoch = window * rate // 50 + candidate["epoch"] + candidate["fractional_offset_samples"]
    period = rate / FRAME_RATE_HZ
    difference = abs((epoch - truth["epoch_samples"] + period / 2) % period - period / 2)
    return (difference / rate * 1e6 <= limits["maximum_circular_epoch_difference_us"]
            and abs(candidate["tracking_cfo_hz"] - truth["cfo_hz"])
            <= limits["maximum_cfo_difference_hz"])


def summarize(rows, protocol):
    result = {}
    for name in protocol["policies"]:
        groups = {}
        for row in rows:
            truth = row["truth"]
            key = f"{truth['rate_hz']}:{truth['kind']}:{truth.get('snr_db', 'none')}"
            group = groups.setdefault(key, {"cases": 0, "flagged": 0, "associated": 0})
            group["cases"] += 1
            group["flagged"] += int(row["decisions"][name]["flagged"])
            group["associated"] += int(row["decisions"][name]["associated"])
        negative = [r for r in rows if not r["truth"]["starlink_model_present"]]
        positive = [r for r in rows if r["truth"]["kind"] in ("pilot", "pilot_plus_tone")
                    and r["truth"]["snr_db"] >= 0]
        false_flags = sum(r["decisions"][name]["flagged"] for r in negative)
        flag_fraction = sum(r["decisions"][name]["flagged"] for r in positive) / len(positive)
        association = sum(r["decisions"][name]["associated"] for r in positive) / len(positive)
        gate = protocol["experiment_gate"]
        result[name] = {
            "groups": groups, "negative_cases": len(negative), "false_flags": false_flags,
            "primary_positive_cases": len(positive), "primary_flag_fraction": flag_fraction,
            "primary_associated_fraction": association,
            "bounded_challenge_pass": (
                false_flags <= gate["negative_false_flags"]
                and flag_fraction >= gate["minimum_positive_flag_fraction_at_snr_ge_0"]
                and association >= gate["minimum_associated_fraction_at_snr_ge_0"]
            ),
        }
    return result


def audit_control_labels(rows, protocol):
    """Retain the original failed gate while documenting its invalid label.

    Rolling the known pilot by 17 symbols creates a timing ambiguity in a
    detector that searches unknown epochs. It is not independent nonpilot
    interference. Never turn this post-hoc correction into a holdout pass.
    """
    result = {}
    for name in protocol["policies"]:
        hard = [r for r in rows if not r["truth"]["starlink_model_present"]
                and r["truth"]["kind"] != "wrong_pilot"]
        ambiguous = [r for r in rows if r["truth"]["kind"] == "wrong_pilot"]
        errors = []
        for row in ambiguous:
            truth = row["truth"]
            rate, period = truth["rate_hz"], truth["rate_hz"] / FRAME_RATE_HZ
            expected = truth["epoch_samples"] + 17 * OFDM_SYMBOL_DURATION_S * rate
            for candidate in passing(row["candidates"], protocol["policies"][name]):
                epoch = (row["selected_window"] * rate // 50 + candidate["epoch"]
                         + candidate["fractional_offset_samples"])
                errors.append((epoch - expected + period / 2) % period - period / 2)
        result[name] = {
            "scope": "post-hoc control-label audit, not qualification or operational FAR",
            "original_gate_preserved": True, "qualified": False,
            "nonpilot_control_cases": len(hard),
            "flags_in_nonpilot_controls": sum(r["decisions"][name]["flagged"] for r in hard),
            "timing_ambiguous_controls": len(ambiguous),
            "flags_in_timing_ambiguous_controls": sum(
                r["decisions"][name]["flagged"] for r in ambiguous),
            "predicted_shift_us": 17 * OFDM_SYMBOL_DURATION_S * 1e6,
            "accepted_candidate_timing_residual_samples": errors,
        }
    return result


def prepare(output, prefix, *, amplitude=False):
    output = output.resolve()
    if any(output.is_relative_to(Path(p)) for p in ("/mnt/qnap01", "/srv/bulk/leo")):
        raise ValueError("output cannot be beneath archive storage")
    protocol = json.loads(PROTOCOL.read_text())
    if (protocol["receiver"] != 1 or protocol["maximum_confirmations"] != 1
            or protocol["screen_bins"] != 512 or protocol["seeded"]):
        raise ValueError("unreviewed detector geometry")
    output.mkdir(parents=True, exist_ok=False)
    options = fftw_options(prefix)
    detector_path = ROOT / protocol["detector_protocol"]
    detector = json.loads(detector_path.read_text())
    flags = tuple(detector["common_flags"]) + tuple(
        f"-DLEO_PRESENCE_{key}={value}" for key, value in detector["variants"][0]["defines"].items()
    ) + ("-DLEO_PRESENCE_DIFFERENTIAL_CI16=1", "-DLEO_PRESENCE_RANK_HYBRID_PROJECTION=1")
    if amplitude:
        flags += ("-DLEO_PRESENCE_RANK_AMPLITUDE_WEIGHTED=1",)
    write_json(output / "freeze.json", {
        "protocol": protocol, "protocol_sha256": digest(PROTOCOL),
        "detector_protocol_sha256": digest(detector_path), "tool_sha256": digest(Path(__file__)),
        "fft_backend": fftw_identity(options), "state": "frozen_before_generation_or_scoring",
        "rank_weighting": "amplitude_development_variant" if amplitude else "normalized_baseline",
    })
    library = build_dwell_presence(output / "detector.so", cflags=flags + options["cflags"],
                                   ldflags=options["ldflags"], dependencies=options["dependencies"])
    return protocol, library


def run_controls(output, prefix, *, amplitude=False):
    protocol, library = prepare(output, prefix, amplitude=amplitude)
    rows = []
    with ExitStack() as stack, (output / "results.jsonl").open("x") as stream:
        engines = {}
        for spec in cases(protocol):
            key = spec["rate_hz"], spec["edge"]
            if key not in engines:
                engines[key] = stack.enter_context(NativeDwell(library, *key, 512))
            iq, truth = generate(spec)
            result = unpack(engines[key].run(iq, maximum=1, seeded=False))
            window = result["rank"]["order"][0]
            confirmation = result["confirmations"][0]
            candidates = confirmation["candidates"][:confirmation["candidate_count"]]
            decisions = {}
            for name, policy in protocol["policies"].items():
                accepted = passing(candidates, policy)
                decisions[name] = {"flagged": bool(accepted), "associated": any(
                    associated(c, truth, window, protocol["association"]) for c in accepted)}
            row = {"truth": truth, "iq_sha256": hashlib.sha256(iq.tobytes()).hexdigest(),
                   "selected_window": window, "candidates": candidates, "decisions": decisions,
                   "cpu_ms": result["total_cpu_ms"], "wall_ms": result["total_wall_ms"]}
            rows.append(row)
            stream.write(json.dumps(row, allow_nan=False) + "\n")
            if len(rows) % 32 == 0:
                print(f"{len(rows)} frozen controls evaluated", flush=True)
    result = {"scope": "bounded synthetic challenge, not operational specificity or absence",
              "cases": len(rows), "binary_sha256": digest(library),
              "results": summarize(rows, protocol),
              "control_label_audit": audit_control_labels(rows, protocol)}
    write_json(output / "summary.json", result)
    print(json.dumps({k: {a: b for a, b in v.items() if a != "groups"}
                      for k, v in result["results"].items()}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--fftw-prefix", type=Path, required=True)
    parser.add_argument("--rank-amplitude", action="store_true",
                        help="Development variant, not untouched challenge qualification")
    args = parser.parse_args()
    run_controls(args.output, args.fftw_prefix, amplitude=args.rank_amplitude)
